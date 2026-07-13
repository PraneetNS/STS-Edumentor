"""
test_rate_limiter.py — Unit tests for backend/utils/rate_limiter.py

Covers:
  - Token consumption and refill behaviour
  - Per-key isolation
  - retry_after accuracy
  - reset and reset_all helpers
  - stats() reporting
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from utils.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Basic consumption
# ---------------------------------------------------------------------------

class TestConsume:
    def test_allows_within_capacity(self):
        limiter = RateLimiter(capacity=5, refill_rate=1.0)
        for _ in range(5):
            allowed, retry_after = limiter.consume("user1")
            assert allowed is True
            assert retry_after == 0.0

    def test_denies_when_exhausted(self):
        limiter = RateLimiter(capacity=2, refill_rate=1.0)
        limiter.consume("user1")
        limiter.consume("user1")
        allowed, retry_after = limiter.consume("user1")
        assert allowed is False
        assert retry_after > 0.0

    def test_retry_after_is_positive(self):
        limiter = RateLimiter(capacity=1, refill_rate=0.5)
        limiter.consume("u")  # drain
        allowed, retry_after = limiter.consume("u")
        assert not allowed
        assert retry_after > 0.0

    def test_per_key_isolation(self):
        limiter = RateLimiter(capacity=1, refill_rate=1.0)
        limiter.consume("key_a")  # drain key_a
        allowed_a, _ = limiter.consume("key_a")
        allowed_b, _ = limiter.consume("key_b")
        assert not allowed_a
        assert allowed_b  # key_b has fresh tokens

    def test_custom_cost(self):
        limiter = RateLimiter(capacity=3, refill_rate=1.0)
        allowed, _ = limiter.consume("x", cost=2.0)
        assert allowed
        allowed2, _ = limiter.consume("x", cost=2.0)
        assert not allowed2


# ---------------------------------------------------------------------------
# Refill over time
# ---------------------------------------------------------------------------

class TestRefill:
    def test_tokens_refill_after_sleep(self):
        limiter = RateLimiter(capacity=1, refill_rate=10.0)  # 10 tokens/sec
        limiter.consume("r")  # drain to 0
        time.sleep(0.15)      # wait ~1.5 tokens
        allowed, _ = limiter.consume("r")
        assert allowed

    def test_refill_does_not_exceed_capacity(self):
        limiter = RateLimiter(capacity=3, refill_rate=100.0)
        time.sleep(0.05)  # refill period
        stats = limiter.stats("fresh_key")
        assert stats["tokens"] <= limiter.capacity


# ---------------------------------------------------------------------------
# Reset helpers
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_single_key(self):
        limiter = RateLimiter(capacity=1, refill_rate=1.0)
        limiter.consume("k")  # drain
        limiter.reset("k")
        allowed, _ = limiter.consume("k")
        assert allowed

    def test_reset_all(self):
        limiter = RateLimiter(capacity=1, refill_rate=1.0)
        limiter.consume("a")
        limiter.consume("b")
        limiter.reset_all()
        assert limiter.consume("a")[0] is True
        assert limiter.consume("b")[0] is True


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_contains_expected_keys(self):
        limiter = RateLimiter(capacity=10, refill_rate=2.0)
        s = limiter.stats("key")
        assert "tokens" in s
        assert "capacity" in s
        assert "refill_rate" in s
        assert s["capacity"] == 10
        assert s["refill_rate"] == 2.0

    def test_stats_tokens_decrease_after_consume(self):
        limiter = RateLimiter(capacity=10, refill_rate=0.0)
        limiter.consume("s", cost=3.0)
        s = limiter.stats("s")
        assert s["tokens"] <= 7.1  # allow tiny float drift
