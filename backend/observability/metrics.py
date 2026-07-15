import prometheus_client
from prometheus_client import Counter, Gauge, Histogram

# The active registry to use for metrics registration. If None, uses prometheus_client.REGISTRY.
_active_registry = None


class MetricProxy:
    def __init__(self, metric_cls, name, documentation, labelnames=(), buckets=None):
        self._metric_cls = metric_cls
        self._name = name
        self._documentation = documentation
        self._labelnames = labelnames
        self._buckets = buckets
        self._instance = None

    def _get_metric(self):
        if self._instance is None:
            registry = _active_registry if _active_registry is not None else prometheus_client.REGISTRY
            kwargs = {}
            if self._labelnames:
                kwargs["labelnames"] = self._labelnames
            if self._buckets is not None:
                kwargs["buckets"] = self._buckets
            self._instance = self._metric_cls(
                self._name,
                self._documentation,
                registry=registry,
                **kwargs
            )
        return self._instance

    def inc(self, amount=1):
        self._get_metric().inc(amount)

    def set(self, value):
        self._get_metric().set(value)

    def observe(self, value):
        self._get_metric().observe(value)

    def labels(self, *args, **kwargs):
        return self._get_metric().labels(*args, **kwargs)


# 1. Endpointing Decisions
endpoint_decision_total = MetricProxy(
    Counter,
    "edumentor_endpoint_decision_total",
    "Semantic endpointing decisions by reason",
    labelnames=["reason"]
)

# 2. Queue Metrics
queue_depth = MetricProxy(
    Gauge,
    "edumentor_queue_depth",
    "Current unacked jobs in the LLM request queue"
)

queue_enqueued_total = MetricProxy(
    Counter,
    "edumentor_queue_enqueued_total",
    "Jobs enqueued"
)

queue_rejected_total = MetricProxy(
    Counter,
    "edumentor_queue_rejected_total",
    "Jobs rejected (queue full)"
)

queue_acked_total = MetricProxy(
    Counter,
    "edumentor_queue_acked_total",
    "Jobs acked by workers"
)

queue_reclaimed_total = MetricProxy(
    Counter,
    "edumentor_queue_reclaimed_total",
    "Stale jobs reclaimed from a crashed or unresponsive worker"
)

# 3. LLM Latencies
llm_ttft_seconds = MetricProxy(
    Histogram,
    "edumentor_llm_ttft_seconds",
    "Time to first token, enqueue to first token chunk",
    buckets=[0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 30]
)

llm_total_latency_seconds = MetricProxy(
    Histogram,
    "edumentor_llm_total_latency_seconds",
    "Total turn latency, enqueue to done",
    buckets=[0.5, 1, 2, 4, 8, 16, 30, 60]
)

# 4. Celebration Composer
celebration_triggered_total = MetricProxy(
    Counter,
    "edumentor_celebration_triggered_total",
    "Positive-signal celebrations actually composed (post cooldown/gate)",
    labelnames=["emotion"]
)

# 5. Memory Retriever
memory_recall_total = MetricProxy(
    Counter,
    "edumentor_memory_recall_total",
    "Cross-session memory retrieval outcomes",
    labelnames=["outcome"]
)


def set_registry(registry):
    """
    Sets the active registry for metrics and resets existing metric instances
    so they are recreated on the new registry when accessed next.
    """
    global _active_registry
    _active_registry = registry
    
    # Reset all metric instances
    endpoint_decision_total._instance = None
    queue_depth._instance = None
    queue_enqueued_total._instance = None
    queue_rejected_total._instance = None
    queue_acked_total._instance = None
    queue_reclaimed_total._instance = None
    llm_ttft_seconds._instance = None
    llm_total_latency_seconds._instance = None
    celebration_triggered_total._instance = None
    memory_recall_total._instance = None
