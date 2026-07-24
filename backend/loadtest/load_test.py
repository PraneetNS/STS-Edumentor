"""
backend/loadtest/load_test.py

Load-test harness for backend/request_queue/llm_queue.py.

Runs against a REAL Redis instance (fakeredis is deliberately not used here --
queue-full behavior, XREADGROUP blocking semantics, and timing under real
concurrency are exactly the things an in-memory fake can't tell you about).

Two swappable pieces let you run this today without llama-server loaded,
then point it at real hardware later with no changes to the harness itself:

  1. generate_fn: defaults to a MOCK generator with realistic timing
     (sampled first-token latency + per-token pacing). Swap in a real
     wrapper around llm_engine.py's streaming client when you're ready to
     test against actual hardware -- see `real_llama_generate_fn` stub
     near the bottom.

  2. Everything else (queue, workers, reclaim loop, client simulation) is
     the exact same code path that will run in production, just pointed
     at a mock instead of llama-server.

Usage:
    python load_test.py --sessions 200 --arrival-rate 5 --workers 4

What it measures:
    - Time-to-first-token (TTFT) per session -- p50/p95/p99
    - Total turn latency (enqueue -> done) -- p50/p95/p99
    - Queue-full rejection rate (backpressure kicking in)
    - Worker-side error rate
    - Stale-job reclaims during a HEALTHY run (should be ~0 -- any
      nonzero count here means claim_stale_after_ms is set too
      aggressively relative to real generation duration, and a live
      job that was never lost could get double-processed)
    - Optional: simulate one worker crashing mid-test (--simulate-crash-after)
      to see whether the system recovers under load, not just at rest
"""

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


# ---------------------------------------------------------------------------
# Mock generation with realistic timing. Swap for the real thing later.
# ---------------------------------------------------------------------------

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
    Streams tokens from the real llama-server instance using LLMEngine.
    """
    from llm.llm_engine import LLMEngine
    from config import Config
    import httpx

    engine = LLMEngine()
    if llm_base_url:
        engine.base_url = llm_base_url
        engine.client = httpx.AsyncClient(
            base_url=llm_base_url,
            timeout=httpx.Timeout(connect=10.0, read=Config.LLM_TIMEOUT, write=10.0, pool=10.0),
            headers={"Content-Type": "application/json"},
        )

    async def generate(prompt: str) -> AsyncIterator[str]:
        async for token in engine.stream_tokens(prompt):
            yield token

    return generate


# ---------------------------------------------------------------------------
# Per-session result tracking
# ---------------------------------------------------------------------------

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
    enqueue_time = time.monotonic()
    result = SessionResult(session_id=session_id, enqueue_time=enqueue_time)

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
            now = time.monotonic()
            result.first_token_time = now
            ttft = now - enqueue_time
            from observability.metrics import llm_ttft_seconds
            llm_ttft_seconds.observe(ttft)
        elif chunk["type"] == "done":
            now = time.monotonic()
            result.done_time = now
            latency = now - enqueue_time
            from observability.metrics import llm_total_latency_seconds
            llm_total_latency_seconds.observe(latency)
        elif chunk["type"] == "error":
            result.error = chunk.get("error")
            result.done_time = time.monotonic()

    return result


# ---------------------------------------------------------------------------
# Worker + reclaim loops
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main harness
# ---------------------------------------------------------------------------

def _percentiles(values: List[float], pcts=(50, 95, 99)):
    if not values:
        return {f"p{p}": None for p in pcts}
    ordered = sorted(values)
    out = {}
    for p in pcts:
        idx = min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))
        out[f"p{p}"] = ordered[idx]
    return out


def summarize(results: List[SessionResult], reclaimed_during_healthy_run: int) -> None:
    total = len(results)
    rejected = [r for r in results if r.rejected]
    completed = [r for r in results if r.done_time is not None]
    errored = [r for r in completed if r.error]

    ttft_values = [r.ttft_s for r in completed if r.ttft_s is not None]
    latency_values = [r.total_latency_s for r in completed if r.total_latency_s is not None]

    print("\n=== Load test results ===")
    print(f"Total simulated sessions : {total}")
    print(f"Rejected (queue full)    : {len(rejected)} ({_pct(len(rejected), total)}%)")
    print(f"Completed                : {len(completed)} ({_pct(len(completed), total)}%)")
    print(f"Worker-side errors       : {len(errored)} ({_pct(len(errored), total)}%)")

    print(f"\nTime-to-first-token (s)  : {_fmt_percentiles(_percentiles(ttft_values))}")
    print(f"Total turn latency (s)   : {_fmt_percentiles(_percentiles(latency_values))}")

    flag = "  <-- investigate: claim_stale_after_ms may be too low" if reclaimed_during_healthy_run else ""
    print(f"\nStale-job reclaims during healthy run: {reclaimed_during_healthy_run}{flag}")


def _pct(n: int, total: int) -> str:
    return f"{(n / total * 100):.1f}" if total else "0.0"


def _fmt_percentiles(p: dict) -> str:
    return ", ".join(
        f"{k}={v:.3f}" if v is not None else f"{k}=n/a" for k, v in p.items()
    )


def write_csv(results: List[SessionResult], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["session_id", "rejected", "ttft_s", "total_latency_s", "error"]
        )
        for r in results:
            writer.writerow(
                [r.session_id, r.rejected, r.ttft_s, r.total_latency_s, r.error or ""]
            )


async def run_load_test(args: argparse.Namespace) -> List[SessionResult]:
    redis_client = redis.from_url(args.redis_url, decode_responses=True)

    queue_config = QueueConfig(
        stream_key=args.stream_key,
        group_name="loadtest-workers",
        max_queue_depth=args.max_queue_depth,
        claim_stale_after_ms=args.claim_stale_after_ms,
        block_ms=args.worker_block_ms,
        response_timeout_s=args.response_timeout_s,
    )
    queue = LLMRequestQueue(redis_client, queue_config)

    # Clean slate for repeatable runs.
    await redis_client.delete(queue_config.stream_key)
    await redis_client.delete(f"{queue_config.stream_key}:acked_count")
    await queue.ensure_group()

    if args.use_real_llm:
        generate_fn = real_llama_generate_fn(args.llm_base_url)
    else:
        profile = MockGenerationProfile(
            ttft_mean_s=args.ttft_mean,
            ttft_std_s=args.ttft_std,
            token_interval_mean_s=args.token_interval_mean,
            token_interval_std_s=args.token_interval_std,
            min_tokens=args.min_tokens,
            max_tokens=args.max_tokens,
            failure_rate=args.failure_rate,
        )
        generate_fn = make_mock_generate_fn(profile)

    workers = [
        LLMWorker(redis_client, generate_fn, f"loadtest-worker-{i}", queue_config)
        for i in range(args.workers)
    ]

    stop_event = asyncio.Event()
    reclaimed_counter = [0]

    worker_tasks = [asyncio.create_task(worker_loop(w, stop_event)) for w in workers]
    reclaim_task = asyncio.create_task(
        reclaim_loop(workers[0], stop_event, interval_s=2.0, reclaim_counter=reclaimed_counter)
    )

    crash_task = None
    if args.simulate_crash_after is not None and worker_tasks:
        async def crash_one_worker():
            await asyncio.sleep(args.simulate_crash_after)
            victim = worker_tasks[0]
            victim.cancel()
            print(
                f"\n[chaos] simulated crash: {workers[0].consumer_name} killed at "
                f"t={args.simulate_crash_after}s -- watching if reclaim recovers its work\n"
            )
        crash_task = asyncio.create_task(crash_one_worker())

    # Poisson arrivals: exponential inter-arrival times at the given rate.
    session_tasks = []
    for i in range(args.sessions):
        session_tasks.append(asyncio.create_task(simulate_session(queue, i)))
        if args.arrival_rate > 0 and i < args.sessions - 1:
            await asyncio.sleep(random.expovariate(args.arrival_rate))

    results = await asyncio.gather(*session_tasks)

    stop_event.set()
    for t in worker_tasks:
        t.cancel()
    reclaim_task.cancel()
    if crash_task:
        crash_task.cancel()
    await asyncio.gather(*worker_tasks, reclaim_task, *([crash_task] if crash_task else []), return_exceptions=True)

    await redis_client.aclose()
    return results, reclaimed_counter[0]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load test for the LLM request queue")
    p.add_argument("--redis-url", default="redis://localhost:6379")
    p.add_argument("--stream-key", default="loadtest:llm:requests")
    p.add_argument("--sessions", type=int, default=200, help="total simulated sessions")
    p.add_argument("--arrival-rate", type=float, default=5.0, help="avg sessions/sec (Poisson)")
    p.add_argument("--workers", type=int, default=4, help="simulated GPU worker processes")
    p.add_argument("--max-queue-depth", type=int, default=200)
    p.add_argument("--claim-stale-after-ms", type=int, default=30_000)
    p.add_argument("--worker-block-ms", type=int, default=5_000)
    p.add_argument("--response-timeout-s", type=float, default=30.0)

    p.add_argument("--ttft-mean", type=float, default=0.30)
    p.add_argument("--ttft-std", type=float, default=0.08)
    p.add_argument("--token-interval-mean", type=float, default=0.03)
    p.add_argument("--token-interval-std", type=float, default=0.01)
    p.add_argument("--min-tokens", type=int, default=20)
    p.add_argument("--max-tokens", type=int, default=150)
    p.add_argument("--failure-rate", type=float, default=0.0)

    p.add_argument("--simulate-crash-after", type=float, default=None,
                    help="seconds into the test to kill one worker (chaos test)")
    p.add_argument("--csv-out", default=None, help="optional path to write per-session results")
    p.add_argument("--use-real-llm", action="store_true", help="use real llama-server instead of mock")
    p.add_argument("--llm-base-url", default=None, help="base url of llama-server")

    return p.parse_args()


def main():
    args = parse_args()
    print(
        f"Running load test: {args.sessions} sessions, arrival_rate={args.arrival_rate}/s, "
        f"{args.workers} workers, max_queue_depth={args.max_queue_depth}"
    )
    results, reclaimed = asyncio.run(run_load_test(args))
    summarize(results, reclaimed)
    if args.csv_out:
        write_csv(results, args.csv_out)
        print(f"\nPer-session results written to {args.csv_out}")


if __name__ == "__main__":
    main()
