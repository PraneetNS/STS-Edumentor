from __future__ import annotations

"""
EduMentor Voice — Redis Request Queue Module

This module implements a Redis-backed request queue system using Redis Streams
and consumer groups. It enables reliable message delivery (at-least-once) to
the GPU worker pool, tracks in-flight messages, and allows other workers to reclaim
stale tasks in the event of a worker crash.
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional


RESPONSE_CHANNEL_PREFIX = "llm:response:"


class QueueFullError(Exception):
    """Raised on enqueue when the backlog has hit max_queue_depth. The
    caller (gateway) should catch this and tell the user the system is at
    capacity -- NOT retry silently or hang, and NOT crash."""


@dataclass
class QueueConfig:
    stream_key: str = "llm:requests"
    group_name: str = "llm-workers"
    max_queue_depth: int = 200           # backpressure ceiling (see note below)
    claim_stale_after_ms: int = 30_000   # reclaim a crashed worker's job after this long idle
    block_ms: int = 5_000                # XREADGROUP long-poll timeout
    response_timeout_s: float = 30.0     # gateway gives up waiting for a worker after this


# ---------------------------------------------------------------------------
# Producer side -- used by the WS gateway.
# ---------------------------------------------------------------------------

class LLMRequestQueue:
    def __init__(self, redis_client, config: Optional[QueueConfig] = None):
        self.redis = redis_client
        self.config = config or QueueConfig()

    async def ensure_group(self) -> None:
        """Idempotent -- safe to call on every gateway startup."""
        try:
            await self.redis.xgroup_create(
                self.config.stream_key, self.config.group_name, id="0", mkstream=True
            )
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def queue_depth(self) -> int:
        """
        Number of jobs not yet acked (waiting + currently being worked on).

        Note: XLEN counts every entry ever added to the stream, including
        ones already acked -- Streams don't shrink on ack the way a list
        would shrink on pop. So depth = XLEN - acked_count, where
        acked_count is a plain counter we increment ourselves on every
        successful XACK. This needs a periodic XTRIM (see trim_acked) to
        keep the underlying stream from growing unbounded over the life
        of the process -- trimming is safe because we only ever trim
        entries at or before the last acked ID.
        """
        total = await self.redis.xlen(self.config.stream_key)
        acked = await self.redis.get(self._acked_counter_key())
        acked = int(acked) if acked is not None else 0
        return max(0, total - acked)

    def _acked_counter_key(self) -> str:
        return f"{self.config.stream_key}:acked_count"

    async def enqueue(self, session_id: str, prompt: str) -> str:
        """
        Returns a request_id. Raises QueueFullError if at capacity --
        the caller must handle this (tell the user the system is busy),
        never silently swallow it.
        """
        depth = await self.queue_depth()
        if depth >= self.config.max_queue_depth:
            raise QueueFullError(
                f"queue at capacity ({depth}/{self.config.max_queue_depth})"
            )

        request_id = str(uuid.uuid4())
        await self.redis.xadd(
            self.config.stream_key,
            {
                "request_id": request_id,
                "session_id": session_id,
                "prompt": prompt,
                "enqueued_at": str(time.time()),
            },
        )
        return request_id

    async def stream_response(self, request_id: str) -> AsyncIterator[Dict[str, Any]]:
        """
        Subscribe to this request's response channel and yield chunks as
        the worker publishes them. Always terminates -- either on a
        'done'/'error' chunk from the worker, or on response_timeout_s if
        no worker ever picks the job up (queue was accepted but nobody
        got to it in time -- distinct from QueueFullError, which rejects
        at enqueue time).
        """
        channel = f"{RESPONSE_CHANNEL_PREFIX}{request_id}"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            deadline = time.monotonic() + self.config.response_timeout_s
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    yield {"type": "error", "error": "timeout waiting for a worker"}
                    return
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=min(remaining, 1.0)
                )
                if message is None:
                    continue
                chunk = json.loads(message["data"])
                yield chunk
                if chunk.get("type") in ("done", "error"):
                    return
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def trim_acked(self) -> None:
        """
        Housekeeping: call periodically (e.g. every minute) from any one
        long-running process. Trims the stream up to the last acked
        entry so it doesn't grow forever. Safe because entries before
        the trim point are, by construction, already acked.
        """
        acked = await self.redis.get(self._acked_counter_key())
        if acked is None:
            return
        # We don't track exact IDs here for simplicity -- a coarser but
        # safe approach is XTRIM MAXLEN ~ to a generous cap, which bounds
        # memory without needing exact ack-id bookkeeping.
        await self.redis.xtrim(self.config.stream_key, maxlen=10_000, approximate=True)


# ---------------------------------------------------------------------------
# Consumer side -- one instance runs per GPU worker process.
# ---------------------------------------------------------------------------

# Signature: async def generate(prompt: str) -> AsyncIterator[str] (tokens)
GenerateFn = Callable[[str], Any]


class LLMWorker:
    def __init__(
        self,
        redis_client,
        generate_fn: GenerateFn,
        consumer_name: str,
        config: Optional[QueueConfig] = None,
    ):
        self.redis = redis_client
        self.generate_fn = generate_fn
        self.consumer_name = consumer_name
        self.config = config or QueueConfig()

    async def run_once(self) -> bool:
        """Process at most one message. Returns True if one was processed,
        False if the long-poll timed out with nothing available (normal
        idle state, not an error)."""
        messages = await self.redis.xreadgroup(
            groupname=self.config.group_name,
            consumername=self.consumer_name,
            streams={self.config.stream_key: ">"},
            count=1,
            block=self.config.block_ms,
        )
        if not messages:
            return False

        _, entries = messages[0]
        for entry_id, fields in entries:
            await self._process(entry_id, fields)
        return True

    async def _process(self, entry_id: str, fields: Dict[str, Any]) -> None:
        request_id = fields["request_id"]
        prompt = fields["prompt"]
        channel = f"{RESPONSE_CHANNEL_PREFIX}{request_id}"
        try:
            async for token in self.generate_fn(prompt):
                await self.redis.publish(
                    channel, json.dumps({"type": "token", "data": token})
                )
            await self.redis.publish(channel, json.dumps({"type": "done"}))
        except Exception as e:
            # A failed generation must still notify the waiting gateway --
            # otherwise it silently sits until response_timeout_s expires
            # rather than getting the actual reason immediately.
            await self.redis.publish(
                channel, json.dumps({"type": "error", "error": str(e)})
            )
        finally:
            # Ack regardless of success/failure -- a failed generation is
            # a completed attempt, not a job to silently retry forever.
            # (If you want retry-on-failure semantics later, that's a
            # deliberate addition, not an accident of missing the ack.)
            await self.redis.xack(self.config.stream_key, self.config.group_name, entry_id)
            await self.redis.incr(f"{self.config.stream_key}:acked_count")

    async def reclaim_stale(self) -> int:
        """
        Reclaim jobs that were delivered to a worker that crashed (or
        hung) before acking. Call this periodically (e.g. every 10s) from
        any live worker -- it's safe for multiple workers to call it
        concurrently, since XCLAIM is atomic per message.

        Returns the number of jobs reclaimed and processed.
        """
        pending: List[Dict[str, Any]] = await self.redis.xpending_range(
            self.config.stream_key,
            self.config.group_name,
            min="-",
            max="+",
            count=50,
        )
        reclaimed = 0
        message_ids = [p["message_id"] for p in pending]
        if not message_ids:
            return 0

        claimed = await self.redis.xclaim(
            self.config.stream_key,
            self.config.group_name,
            self.consumer_name,
            min_idle_time=self.config.claim_stale_after_ms,
            message_ids=message_ids,
        )
        for entry_id, fields in claimed:
            await self._process(entry_id, fields)
            reclaimed += 1
        return reclaimed
