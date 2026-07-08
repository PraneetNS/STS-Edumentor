from __future__ import annotations

import argparse
import asyncio
import csv
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, List, Optional

import redis.asyncio as redis

from request_queue.llm_queue import (
    LLMRequestQueue,
    LLMWorker,
    QueueConfig,
    QueueFullError,
)

@dataclass
class MockGenerationProfile:
    ttft_mean_s: float = 0.30     # mimics prefill + first-token latency
    ttft_std_s: float = 0.08
    token_interval_mean_s: float = 0.03   # ~33 tok/s decode pace
    token_interval_std_s: float = 0.01
    min_tokens: int = 20
    max_tokens: int = 150
    failure_rate: float = 0.0     # fraction of generations that raise

def make_mock_generate_fn(profile: MockGenerationProfile):
    async def generate(prompt: str) -> AsyncIterator[str]:
        if random.random() < profile.failure_rate:
            raise RuntimeError("simulated generation failure")

        ttft = max(0.02, random.gauss(profile.ttft_mean_s, profile.ttft_std_s))
        await asyncio.sleep(ttft)

        n_tokens = random.randint(profile.min_tokens, profile.max_tokens)
        for i in range(n_tokens):
            yield f"tok_{i}"
            if i < n_tokens - 1:
                gap = max(0.005, random.gauss(
                    profile.token_interval_mean_s, profile.token_interval_std_s
                ))
                await asyncio.sleep(gap)

    return generate

def real_llama_generate_fn(llm_base_url: str):
    """
    STUB -- fill this in with your actual llm_engine.py streaming client
    when you're ready to test against real hardware. Same signature as the
    mock above: async def generate(prompt: str) -> AsyncIterator[str].
    """
    raise NotImplementedError(
        "Wire this up to llm_engine.py's real streaming client before "
        "running with --use-real-llm."
    )

@dataclass
class SessionResult:
    session_id: str
    enqueue_time: float
    request_id: Optional[str] = None
    first_token_time: Optional[float] = None
    done_time: Optional[float] = None
    rejected: bool = False
    error: Optional[str] = None

    @property
    def ttft_s(self) -> Optional[float]:
        if self.first_token_time is None:
            return None
        return self.first_token_time - self.enqueue_time

    @property
    def total_latency_s(self) -> Optional[float]:
        if self.done_time is None:
            return None
        return self.done_time - self.enqueue_time

async def simulate_session(
    queue: LLMRequestQueue, session_idx: int
) -> SessionResult:
    session_id = f"loadtest-session-{session_idx}"
    result = SessionResult(session_id=session_id, enqueue_time=time.monotonic())

    try:
        result.request_id = await queue.enqueue(
            session_id, f"synthetic loadtest question #{session_idx}"
        )
    except QueueFullError as e:
        result.rejected = True
        result.error = str(e)
        return result

    async for chunk in queue.stream_response(result.request_id):
        if chunk["type"] == "token" and result.first_token_time is None:
            result.first_token_time = time.monotonic()
        elif chunk["type"] == "done":
            result.done_time = time.monotonic()
        elif chunk["type"] == "error":
            result.error = chunk.get("error")
            result.done_time = time.monotonic()

    return result

async def worker_loop(worker: LLMWorker, stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            await worker.run_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[worker {worker.consumer_name}] error: {e}", file=sys.stderr)

async def reclaim_loop(
    worker: LLMWorker, stop_event: asyncio.Event, interval_s: float, reclaim_counter: List[int]
):
    while not stop_event.is_set():
        await asyncio.sleep(interval_s)
        try:
            n = await worker.reclaim_stale()
            reclaim_counter[0] += n
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[reclaim loop] error: {e}", file=sys.stderr)
