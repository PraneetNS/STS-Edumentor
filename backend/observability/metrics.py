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

# 6. Language Routing Decisions
language_routing_total = MetricProxy(
    Counter,
    "edumentor_language_routing_total",
    "Multilingual routing decisions categorized by resolution path",
    labelnames=["routing_path", "route_lang"]
)

# 7. Multilingual Stage-by-Stage Latencies
multilingual_stt_ttf_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_stt_ttf_seconds",
    "Time to first Whisper segment output",
    labelnames=["language"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
)

multilingual_stt_total_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_stt_total_seconds",
    "Total Whisper transcription time",
    labelnames=["language"],
    buckets=[0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0]
)

multilingual_router_classify_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_router_classify_seconds",
    "Time to classify input language",
    labelnames=["language"],
    buckets=[0.0005, 0.001, 0.002, 0.005, 0.01, 0.05]
)

multilingual_glossary_protect_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_glossary_protect_seconds",
    "Time to mask technical terms in input or response",
    labelnames=["language"],
    buckets=[0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1]
)

multilingual_translate_in_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_translate_in_seconds",
    "Time for NLLB translate-in call",
    labelnames=["language"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
)

multilingual_llm_ttft_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_llm_ttft_seconds",
    "Time to first LLM token in multilingual stream",
    labelnames=["language"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
)

multilingual_llm_completion_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_llm_completion_seconds",
    "Total time to complete LLM generation in multilingual stream",
    labelnames=["language"],
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
)

multilingual_translate_out_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_translate_out_seconds",
    "Time for NLLB translate-out call (per sentence or overall)",
    labelnames=["language"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
)

multilingual_glossary_restore_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_glossary_restore_seconds",
    "Time to restore technical terms in input or response",
    labelnames=["language"],
    buckets=[0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1]
)

multilingual_tts_ttf_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_tts_ttf_seconds",
    "Time to generate first audio byte of TTS",
    labelnames=["language"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0]
)

multilingual_tts_completion_seconds = MetricProxy(
    Histogram,
    "edumentor_multilingual_tts_completion_seconds",
    "Time for TTS synthesis calls",
    labelnames=["language"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0]
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
    language_routing_total._instance = None
    
    multilingual_stt_ttf_seconds._instance = None
    multilingual_stt_total_seconds._instance = None
    multilingual_router_classify_seconds._instance = None
    multilingual_glossary_protect_seconds._instance = None
    multilingual_translate_in_seconds._instance = None
    multilingual_llm_ttft_seconds._instance = None
    multilingual_llm_completion_seconds._instance = None
    multilingual_translate_out_seconds._instance = None
    multilingual_glossary_restore_seconds._instance = None
    multilingual_tts_ttf_seconds._instance = None
    multilingual_tts_completion_seconds._instance = None

