import asyncio

"""
EduMentor Voice — Request Queue Unit Test Suite

This test suite covers reliability guarantees of the Redis Request Queue, including
successful enqueues, streaming consumer group reads, backpressure limits, and worker crash recovery.
"""

import fakeredis.aioredis as fakeaioredis
from fakeredis import FakeServer
import pytest

from request_queue.llm_queue import (
    LLMRequestQueue,
    LLMWorker,
    QueueConfig,
    QueueFullError,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def redis_client():
    server = FakeServer()
    client = fakeaioredis.FakeRedis(server=server, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def config():
    return QueueConfig(
        stream_key="test:llm:requests",
        group_name="test-workers",
        max_queue_depth=3,
        claim_stale_after_ms=100,  # short, for fast tests
        block_ms=200,
        response_timeout_s=2.0,
    )


@pytest.fixture
async def queue(redis_client, config):
    q = LLMRequestQueue(redis_client, config)
    await q.ensure_group()
    return q


async def fake_generate_ok(prompt: str):
    for tok in ["hello", " ", "world"]:
        yield tok


async def fake_generate_fail(prompt: str):
    if False:
        yield  # pragma: no cover -- makes this a generator
    raise RuntimeError("llama-server exploded")


# --- Basic round trip -------------------------------------------------------

async def test_enqueue_then_worker_processes_and_streams_response(redis_client, queue, config):
    request_id = await queue.enqueue("session-1", "what's a pointer?")

    worker = LLMWorker(redis_client, fake_generate_ok, "worker-1", config)
    processed = await worker.run_once()
    assert processed is True

    chunks = [c async for c in queue.stream_response(request_id)]
    depth = await queue.queue_depth()
    assert depth == 0


async def test_streaming_receives_tokens_in_order_then_done(redis_client, queue, config):
    worker = LLMWorker(redis_client, fake_generate_ok, "worker-1", config)

    request_id = await queue.enqueue("session-1", "what's a pointer?")

    async def consume():
        return [c async for c in queue.stream_response(request_id)]

    consumer_task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)  # let the subscriber attach before publishing
    await worker.run_once()

    chunks = await consumer_task
    assert [c["type"] for c in chunks] == ["token", "token", "token", "done"]
    assert [c["data"] for c in chunks[:3]] == ["hello", " ", "world"]


async def test_failed_generation_publishes_error_not_hang(redis_client, queue, config):
    worker = LLMWorker(redis_client, fake_generate_fail, "worker-1", config)
    request_id = await queue.enqueue("session-1", "what's a pointer?")

    async def consume():
        return [c async for c in queue.stream_response(request_id)]

    consumer_task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    await worker.run_once()

    chunks = await consumer_task
    assert chunks[-1]["type"] == "error"
    assert "exploded" in chunks[-1]["error"]


# --- Backpressure -----------------------------------------------------------

async def test_enqueue_raises_when_at_capacity(queue):
    await queue.enqueue("s1", "q1")
    await queue.enqueue("s2", "q2")
    await queue.enqueue("s3", "q3")
    # max_queue_depth=3, all unacked -> 4th must be rejected
    with pytest.raises(QueueFullError):
        await queue.enqueue("s4", "q4")


async def test_queue_depth_drops_as_worker_acks(redis_client, queue, config):
    worker = LLMWorker(redis_client, fake_generate_ok, "worker-1", config)
    await queue.enqueue("s1", "q1")
    await queue.enqueue("s2", "q2")
    assert await queue.queue_depth() == 2

    await worker.run_once()
    assert await queue.queue_depth() == 1

    await worker.run_once()
    assert await queue.queue_depth() == 0


async def test_capacity_frees_up_after_processing(redis_client, queue, config):
    worker = LLMWorker(redis_client, fake_generate_ok, "worker-1", config)
    await queue.enqueue("s1", "q1")
    await queue.enqueue("s2", "q2")
    await queue.enqueue("s3", "q3")

    with pytest.raises(QueueFullError):
        await queue.enqueue("s4", "q4")

    await worker.run_once()  # frees one slot

    # Should succeed now that depth dropped below max_queue_depth.
    request_id = await queue.enqueue("s4", "q4")
    assert request_id is not None


# --- Crash recovery ----------------------------------------------------------

async def test_stale_job_is_reclaimed_and_completed_by_another_worker(redis_client, queue, config):
    crashed_worker = LLMWorker(redis_client, fake_generate_ok, "crashed-worker", config)
    rescuer = LLMWorker(redis_client, fake_generate_ok, "rescuer-worker", config)

    request_id = await queue.enqueue("s1", "what's a pointer?")

    # Simulate a crash: the message gets delivered but the worker dies
    # before ever calling _process (so it's never acked).
    messages = await redis_client.xreadgroup(
        groupname=config.group_name,
        consumername="crashed-worker",
        streams={config.stream_key: ">"},
        count=1,
    )
    assert messages  # confirm delivery happened

    # Not yet stale -- claim_stale_after_ms hasn't elapsed.
    reclaimed = await rescuer.reclaim_stale()
    assert reclaimed == 0

    await asyncio.sleep(config.claim_stale_after_ms / 1000 + 0.05)

    reclaimed = await rescuer.reclaim_stale()
    assert reclaimed == 1
    assert await queue.queue_depth() == 0  # rescuer's _process acked it


# --- No double-processing ---------------------------------------------------

async def test_two_workers_never_process_same_message(redis_client, queue, config):
    seen = []

    async def tracking_generate(prompt: str):
        seen.append(prompt)
        yield "ok"

    worker_a = LLMWorker(redis_client, tracking_generate, "worker-a", config)
    worker_b = LLMWorker(redis_client, tracking_generate, "worker-b", config)

    await queue.enqueue("s1", "only-once")

    results = await asyncio.gather(worker_a.run_once(), worker_b.run_once())
    # Exactly one of the two workers should have gotten the single message.
    assert sum(results) == 1
    assert seen == ["only-once"]
