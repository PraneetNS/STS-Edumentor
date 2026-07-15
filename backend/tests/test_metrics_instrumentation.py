import asyncio
import time
import pytest
import prometheus_client
import fakeredis.aioredis as fakeaioredis
from fakeredis import FakeServer

from speech.endpointing import SemanticEndpointer, EndpointingConfig, EndpointingMode
from request_queue.llm_queue import LLMRequestQueue, LLMWorker, QueueConfig, QueueFullError
from loadtest.load_test import simulate_session
from agent.celebration_composer import CelebrationComposer, CelebrationConfig
from agent.positive_signal_detector import PositiveEmotion, PositiveSignal
from agent.memory_retriever import MemoryRetriever, RetrievalConfig

# Import the metrics proxy registry reset helper
from observability.metrics import set_registry

# Helper to find a metric value in a custom registry
def get_metric_value(registry, name, labels=None):
    for metric in registry.collect():
        for sample in metric.samples:
            if sample.name == name:
                if labels:
                    if all(sample.labels.get(k) == v for k, v in labels.items()):
                        return sample.value
                else:
                    return sample.value
    return None

def test_endpointing_metrics():
    registry = prometheus_client.CollectorRegistry()
    set_registry(registry)
    
    config = EndpointingConfig(mode=EndpointingMode.FIXED)
    endpointer = SemanticEndpointer(config)
    
    # Trigger fixed mode
    endpointer.decide("hello", 1000)
    
    val = get_metric_value(registry, "edumentor_endpoint_decision_total", {"reason": "fixed_mode"})
    assert val == 1.0

@pytest.mark.asyncio
async def test_queue_metrics_enqueue_and_depth():
    registry = prometheus_client.CollectorRegistry()
    set_registry(registry)
    
    server = FakeServer()
    redis_client = fakeaioredis.FakeRedis(server=server, decode_responses=True)
    try:
        config = QueueConfig(max_queue_depth=2, stream_key="test_metrics:llm:requests", group_name="test_metrics-workers")
        queue = LLMRequestQueue(redis_client, config)
        await queue.ensure_group()
        
        # 1. Test queue_depth (should set gauge)
        depth = await queue.queue_depth()
        assert depth == 0
        depth_val = get_metric_value(registry, "edumentor_queue_depth")
        assert depth_val == 0.0
        
        # 2. Test enqueue success
        req_id1 = await queue.enqueue("session-1", "hello")
        enqueued_val = get_metric_value(registry, "edumentor_queue_enqueued_total")
        assert enqueued_val == 1.0
        
        # 3. Test queue_depth with 1 item
        depth = await queue.queue_depth()
        assert depth == 1
        depth_val = get_metric_value(registry, "edumentor_queue_depth")
        assert depth_val == 1.0
        
        # 4. Enqueue second to hit max_queue_depth
        await queue.enqueue("session-2", "world")
        
        # 5. Enqueue third to trigger QueueFullError
        with pytest.raises(QueueFullError):
            await queue.enqueue("session-3", "full")
            
        rejected_val = get_metric_value(registry, "edumentor_queue_rejected_total")
        assert rejected_val == 1.0
        
    finally:
        await redis_client.aclose()

@pytest.mark.asyncio
async def test_worker_metrics_ack_and_reclaim():
    registry = prometheus_client.CollectorRegistry()
    set_registry(registry)
    
    server = FakeServer()
    redis_client = fakeaioredis.FakeRedis(server=server, decode_responses=True)
    try:
        config = QueueConfig(
            stream_key="test_worker_metrics:llm:requests",
            group_name="test_worker_metrics-workers",
            claim_stale_after_ms=50,
            block_ms=100
        )
        queue = LLMRequestQueue(redis_client, config)
        await queue.ensure_group()
        
        # Enqueue job
        req_id = await queue.enqueue("session-1", "what's a pointer?")
        
        async def fake_generator(prompt):
            yield "token1"
            yield "token2"
            
        worker = LLMWorker(redis_client, fake_generator, "worker-1", config)
        
        # Run worker processing
        processed = await worker.run_once()
        assert processed is True
        
        # Assert acked counter
        acked_val = get_metric_value(registry, "edumentor_queue_acked_total")
        assert acked_val == 1.0
        
        # Test reclaim: enqueue another job, but reclaim it
        req_id2 = await queue.enqueue("session-2", "reclaim me")
        # We need to simulate worker processing starting but crashing (crashed worker doesn't ack)
        # So we read the stream group but do not ack it.
        # Let's read it using a different consumer
        crashed_worker = LLMWorker(redis_client, fake_generator, "worker-crashed", config)
        messages = await redis_client.xreadgroup(
            groupname=config.group_name,
            consumername=crashed_worker.consumer_name,
            streams={config.stream_key: ">"},
            count=1,
            block=100
        )
        assert messages
        
        # Wait for stale timeout
        await asyncio.sleep(0.06)
        
        # Now reclaim from worker-1
        reclaimed_count = await worker.reclaim_stale()
        assert reclaimed_count == 1
        
        # Assert reclaimed metric
        reclaimed_val = get_metric_value(registry, "edumentor_queue_reclaimed_total")
        assert reclaimed_val == 1.0
        
    finally:
        await redis_client.aclose()

@pytest.mark.asyncio
async def test_load_test_timing_metrics():
    registry = prometheus_client.CollectorRegistry()
    set_registry(registry)
    
    server = FakeServer()
    redis_client = fakeaioredis.FakeRedis(server=server, decode_responses=True)
    try:
        config = QueueConfig(
            stream_key="test_load_test_metrics:llm:requests",
            group_name="test_load_test_metrics-workers"
        )
        queue = LLMRequestQueue(redis_client, config)
        await queue.ensure_group()
        
        # Simulate worker processing concurrently to generate chunks
        async def process_concurrently():
            await asyncio.sleep(0.05)
            # Read and process using worker
            async def fake_generator(prompt):
                await asyncio.sleep(0.05)
                yield "tok1"
                await asyncio.sleep(0.05)
                yield "tok2"
            worker = LLMWorker(redis_client, fake_generator, "worker-loadtest", config)
            await worker.run_once()
            
        task = asyncio.create_task(process_concurrently())
        
        # Run simulate_session (the gateway integration point)
        res = await simulate_session(queue, 1)
        await task
        
        assert res.error is None
        assert res.first_token_time is not None
        assert res.done_time is not None
        
        # Verify histograms recorded observations
        ttft_count = get_metric_value(registry, "edumentor_llm_ttft_seconds_count")
        assert ttft_count is not None and ttft_count >= 1.0
        
        latency_count = get_metric_value(registry, "edumentor_llm_total_latency_seconds_count")
        assert latency_count is not None and latency_count >= 1.0
        
    finally:
        await redis_client.aclose()

def test_celebration_composer_metrics():
    registry = prometheus_client.CollectorRegistry()
    set_registry(registry)
    
    config = CelebrationConfig(enabled=True, cooldown_s=0.0)
    composer = CelebrationComposer(config)
    
    signal = PositiveSignal(
        emotion=PositiveEmotion.EXCITED,
        intensity=0.8,
        reason="excited_language"
    )
    
    res = composer.compose("session-123", signal)
    assert res is not None
    
    val = get_metric_value(registry, "edumentor_celebration_triggered_total", {"emotion": "excited"})
    assert val == 1.0

@pytest.mark.asyncio
async def test_memory_retriever_metrics():
    registry = prometheus_client.CollectorRegistry()
    set_registry(registry)
    
    class DummyEmbeddingFn:
        async def embed(self, text):
            return [0.1]
            
    class DummyVectorStore:
        def __init__(self, search_results):
            self.search_results = search_results
        async def search(self, collection, vector, filter_payload, limit):
            return self.search_results
            
    # Case 1: Hit (returns a memory)
    hits = [
        {
            "payload": {
                "student_id": "student-123",
                "timestamp": time.time(),
                "was_weak_area": False,
                "topic": "math",
                "summary_text": "Fraction mastery"
            },
            "score": 0.9
        }
    ]
    vs = DummyVectorStore(hits)
    embedding = DummyEmbeddingFn()
    
    config = RetrievalConfig(enabled=True, min_relevance_score=0.1, max_age_days=10)
    retriever = MemoryRetriever(vs, embedding, config)
    
    res_hit = await retriever.retrieve("student-123", "math query", set(), now=time.time())
    assert len(res_hit) == 1
    
    val_hit = get_metric_value(registry, "edumentor_memory_recall_total", {"outcome": "hit"})
    assert val_hit == 1.0
    
    # Case 2: Miss (no memory)
    vs_empty = DummyVectorStore([])
    retriever_miss = MemoryRetriever(vs_empty, embedding, config)
    res_miss = await retriever_miss.retrieve("student-123", "math query", set(), now=time.time())
    assert len(res_miss) == 0
    
    val_miss = get_metric_value(registry, "edumentor_memory_recall_total", {"outcome": "miss"})
    assert val_miss == 1.0
