"""
rate_limiter.py — Async token-bucket rate limiter for EduMentor Voice.

Provides per-key (IP / session) rate limiting using the token-bucket algorithm.
All state is stored in-process (no Redis required), making it suitable for
single-node deployments and tests.

Usage::

    from utils.rate_limiter import RateLimiter

    limiter = RateLimiter(capacity=10, refill_rate=2.0)   # 2 tokens/sec

    async def handle_request(ip: str):
        allowed, retry_after = limiter.consume(ip)
        if not allowed:
            raise HTTPException(429, f"Rate limit exceeded. Retry after {retry_after:.1f}s")
        ...

Algorithm:
    - Each key starts with *capacity* tokens.
    - Tokens refill at *refill_rate* per second (continuous, not bursty).
    - A single request costs 1 token.
    - When empty the bucket returns ``allowed=False`` and a ``retry_after``
      estimate (seconds until 1 token is available).

Thread-safety:
    ``consume()`` and ``reset()`` are protected by a ``threading.Lock``
    so they are safe to call from multiple asyncio tasks via
    ``asyncio.to_thread`` or directly if the event loop is single-threaded.
"""

import threading
import time
from typing import Tuple


class RateLimiter:
    """Token-bucket rate limiter with per-key state."""

    def __init__(self, capacity: float = 20.0, refill_rate: float = 1.0) -> None:
        """
        Args:
            capacity:     Maximum number of tokens per key (burst ceiling).
            refill_rate:  Tokens added per second (sustain rate).
        """
        self._capacity    = capacity
        self._refill_rate = refill_rate
        self._buckets: dict[str, tuple[float, float]] = {}  # key → (tokens, last_refill_ts)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def consume(self, key: str, cost: float = 1.0) -> Tuple[bool, float]:
        """
        Attempt to consume *cost* tokens for *key*.

        Returns:
            (allowed, retry_after) where *retry_after* is the number of
            seconds to wait before retrying (0.0 when allowed).
        """
        now = time.monotonic()
        with self._lock:
            tokens, last_ts = self._buckets.get(key, (self._capacity, now))

            # Refill tokens proportional to elapsed time
            elapsed = now - last_ts
            tokens  = min(self._capacity, tokens + elapsed * self._refill_rate)

            if tokens >= cost:
                self._buckets[key] = (tokens - cost, now)
                return True, 0.0
            else:
                # Compute how long until *cost* tokens are available
                deficit      = cost - tokens
                retry_after  = deficit / self._refill_rate
                self._buckets[key] = (tokens, now)
                return False, retry_after

    def reset(self, key: str) -> None:
        """Remove the bucket for *key* (refills to capacity on next access)."""
        with self._lock:
            self._buckets.pop(key, None)

    def reset_all(self) -> None:
        """Clear all buckets (useful in tests)."""
        with self._lock:
            self._buckets.clear()

    @property
    def capacity(self) -> float:
        return self._capacity

    @property
    def refill_rate(self) -> float:
        return self._refill_rate

    def stats(self, key: str) -> dict:
        """Return current token count and refill rate for *key*."""
        now = time.monotonic()
        with self._lock:
            tokens, last_ts = self._buckets.get(key, (self._capacity, now))
            elapsed = now - last_ts
            current = min(self._capacity, tokens + elapsed * self._refill_rate)
        return {
            "key": key,
            "tokens": round(current, 3),
            "capacity": self._capacity,
            "refill_rate": self._refill_rate,
        }
