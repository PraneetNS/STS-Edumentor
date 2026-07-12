"""
test_metrics.py — Unit tests for backend/utils/metrics.py

Covers:
  - counter: inc(), value accumulation
  - gauge: set(), inc(), dec()
  - histogram: observe(), summary statistics
  - snapshot(): full metrics serialisation
  - reset(): clears all metrics
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from utils import metrics as m


@pytest.fixture(autouse=True)
def clear_metrics():
    """Reset all metrics before each test to prevent cross-test pollution."""
    m.reset()
    yield
    m.reset()


# ---------------------------------------------------------------------------
# Counter tests
# ---------------------------------------------------------------------------

class TestCounter:
    def test_starts_at_zero(self):
        assert m.counter("test.c1").value == 0

    def test_inc_by_one(self):
        m.counter("test.c2").inc()
        assert m.counter("test.c2").value == 1

    def test_inc_by_amount(self):
        m.counter("test.c3").inc(5)
        assert m.counter("test.c3").value == 5

    def test_accumulates(self):
        c = m.counter("test.c4")
        c.inc()
        c.inc()
        c.inc(3)
        assert c.value == 5

    def test_independent_counters(self):
        m.counter("test.ca").inc(10)
        m.counter("test.cb").inc(2)
        assert m.counter("test.ca").value == 10
        assert m.counter("test.cb").value == 2


# ---------------------------------------------------------------------------
# Gauge tests
# ---------------------------------------------------------------------------

class TestGauge:
    def test_starts_at_zero(self):
        assert m.gauge("test.g1").value == 0

    def test_set(self):
        m.gauge("test.g2").set(42)
        assert m.gauge("test.g2").value == 42

    def test_inc(self):
        m.gauge("test.g3").set(10)
        m.gauge("test.g3").inc(5)
        assert m.gauge("test.g3").value == 15

    def test_dec(self):
        m.gauge("test.g4").set(10)
        m.gauge("test.g4").dec(3)
        assert m.gauge("test.g4").value == 7

    def test_overwrite(self):
        g = m.gauge("test.g5")
        g.set(100)
        g.set(7)
        assert g.value == 7


# ---------------------------------------------------------------------------
# Histogram tests
# ---------------------------------------------------------------------------

class TestHistogram:
    def test_empty_summary(self):
        s = m.histogram("test.h0").summary()
        assert s == {"count": 0}

    def test_observe_count(self):
        h = m.histogram("test.h1")
        h.observe(10)
        h.observe(20)
        assert h.summary()["count"] == 2

    def test_observe_mean(self):
        h = m.histogram("test.h2")
        h.observe(10)
        h.observe(20)
        assert h.summary()["mean"] == 15.0

    def test_percentiles(self):
        h = m.histogram("test.h3")
        for v in range(1, 101):
            h.observe(float(v))
        s = h.summary()
        assert s["p50"] > 0
        assert s["p95"] >= s["p50"]
        assert s["p99"] >= s["p95"]


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_snapshot_has_uptime(self):
        snap = m.snapshot()
        assert "uptime_s" in snap
        assert snap["uptime_s"] >= 0

    def test_snapshot_includes_counter(self):
        m.counter("snap.x").inc(3)
        snap = m.snapshot()
        assert snap["counters"].get("snap.x") == 3

    def test_snapshot_includes_gauge(self):
        m.gauge("snap.y").set(99)
        snap = m.snapshot()
        assert snap["gauges"].get("snap.y") == 99

    def test_snapshot_includes_histogram(self):
        m.histogram("snap.z").observe(50)
        snap = m.snapshot()
        assert "snap.z" in snap["histograms"]
        assert snap["histograms"]["snap.z"]["count"] == 1


# ---------------------------------------------------------------------------
# Reset tests
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_counter(self):
        m.counter("reset.c").inc(99)
        m.reset()
        assert m.counter("reset.c").value == 0

    def test_reset_clears_gauge(self):
        m.gauge("reset.g").set(55)
        m.reset()
        assert m.gauge("reset.g").value == 0

    def test_reset_clears_histogram(self):
        m.histogram("reset.h").observe(1.0)
        m.reset()
        assert m.histogram("reset.h").summary() == {"count": 0}
