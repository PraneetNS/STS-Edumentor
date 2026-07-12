"""
metrics.py — Lightweight in-process metrics collector for EduMentor Voice.

Provides counters, gauges, and histograms that accumulate in memory and can
be serialised to a dict (for the /metrics endpoint or Prometheus text format).

This is intentionally zero-dependency (no prometheus_client required) so it
works in environments where the full Prometheus client is not installed.

Usage::

    from utils.metrics import counter, gauge, histogram, snapshot

    counter("llm.requests").inc()
    gauge("ws.connections").set(12)
    histogram("llm.latency_ms").observe(342)

    print(snapshot())  # {"llm.requests": 1, "ws.connections": 12, ...}
"""

import threading
import time
from collections import defaultdict
from typing import Any

_lock = threading.Lock()

_counters: dict[str, float] = defaultdict(float)
_gauges: dict[str, float] = {}
_histograms: dict[str, list[float]] = defaultdict(list)
_start_time = time.monotonic()


# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------

class _Counter:
    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def inc(self, amount: float = 1.0) -> None:
        """Increment the counter by *amount* (default 1)."""
        with _lock:
            _counters[self._name] += amount

    @property
    def value(self) -> float:
        return _counters[self._name]


# ---------------------------------------------------------------------------
# Gauge
# ---------------------------------------------------------------------------

class _Gauge:
    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def set(self, value: float) -> None:
        """Set the gauge to an absolute *value*."""
        with _lock:
            _gauges[self._name] = value

    def inc(self, amount: float = 1.0) -> None:
        with _lock:
            _gauges[self._name] = _gauges.get(self._name, 0) + amount

    def dec(self, amount: float = 1.0) -> None:
        with _lock:
            _gauges[self._name] = _gauges.get(self._name, 0) - amount

    @property
    def value(self) -> float:
        return _gauges.get(self._name, 0.0)


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------

class _Histogram:
    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def observe(self, value: float) -> None:
        """Record an observation."""
        with _lock:
            _histograms[self._name].append(value)

    def summary(self) -> dict[str, float]:
        """Return count, sum, mean, p50, p95, p99."""
        with _lock:
            values = sorted(_histograms[self._name])
        if not values:
            return {"count": 0}
        n = len(values)
        return {
            "count": n,
            "sum": sum(values),
            "mean": sum(values) / n,
            "p50": values[int(n * 0.50)],
            "p95": values[min(int(n * 0.95), n - 1)],
            "p99": values[min(int(n * 0.99), n - 1)],
        }


# ---------------------------------------------------------------------------
# Public factory functions
# ---------------------------------------------------------------------------

def counter(name: str) -> _Counter:
    """Return (or create) a named counter."""
    return _Counter(name)


def gauge(name: str) -> _Gauge:
    """Return (or create) a named gauge."""
    return _Gauge(name)


def histogram(name: str) -> _Histogram:
    """Return (or create) a named histogram."""
    return _Histogram(name)


def snapshot() -> dict[str, Any]:
    """
    Return a full snapshot of all metrics as a plain dict.

    Suitable for serialisation to JSON via the /metrics endpoint.
    """
    with _lock:
        return {
            "uptime_s": round(time.monotonic() - _start_time, 1),
            "counters": dict(_counters),
            "gauges": dict(_gauges),
            "histograms": {
                name: _Histogram(name).summary()
                for name in _histograms
            },
        }


def reset() -> None:
    """Clear all metrics (useful in tests)."""
    with _lock:
        _counters.clear()
        _gauges.clear()
        _histograms.clear()
