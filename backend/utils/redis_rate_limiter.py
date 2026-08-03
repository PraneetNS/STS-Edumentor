"""
utils/redis_rate_limiter.py - Redis-backed sliding-window rate limiter.

Drop-in replacement for utils/rate_limiter.py (RateLimiter) that works
across multiple backend workers because all state lives in Redis.

Algorithm - fixed-window INCR + EXPIRE:
    For each key (IP / session) we keep a counter in Redis with a TTL equal
    to the window length.  The first request in any window creates the key
    and sets its expiry; subsequent requests INCR it.  When the counter
    exceeds the limit the request is rejected and retry_after is estimated
    as the key remaining TTL.

Thread-safety:
    INCR is atomic in Redis, so no additional locking is required.

Usage::

    from utils.redis_rate_limiter import RedisRateLimiter

    limiter = RedisRateLimiter(redis_client, limit=20, window_seconds=60)

    allowed, retry_after = await limiter.consume("192.168.1.1")
    if not allowed:
        raise HTTPException(429, f"Rate limit exceeded. Retry after {retry_after:.1f}s")
"""

from __future__ import annotations

import logging
from typing import Tuple

from agent.rate_limiter import is_bypass_token

logger = logging.getLogger("edumentor.utils.redis_rate_limiter")


class RedisRateLimiter:
    """
    Async Redis-backed fixed-window rate limiter.

    Args:
        redis_client:   An redis.asyncio client instance (already connected).
        limit:          Maximum requests allowed per window per key.
        window_seconds: Window length in seconds.
        key_prefix:     Namespace prefix for Redis keys (default "ratelimit").
    """

    def __init__(
        self,
        redis_client,
        limit: int = 20,
        window_seconds: int = 60,
        key_prefix: str = "ratelimit",
    ) -> None:
        self._redis = redis_client
        self._limit = limit
        self._window = window_seconds
        self._prefix = key_prefix
        logger.info(
            "[OK] RedisRateLimiter ready (limit=%d/%ds, prefix=%s).",
            limit, window_seconds, key_prefix,
        )

    # internal

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    # public API (matches RateLimiter interface)

    async def consume(self, key: str, cost: int = 1) -> Tuple[bool, float]:
        """
        Attempt to consume cost requests for key.

        Returns:
            (allowed, retry_after) - retry_after is 0.0 when allowed,
            otherwise the estimated seconds until the window resets.
        """
        rkey = self._key(key)
        try:
            # INCR is atomic; returns the new value after increment.
            count = await self._redis.incr(rkey)
            if count == 1:
                # First request in this window - set the expiry.
                await self._redis.expire(rkey, self._window)

            if count <= self._limit:
                return True, 0.0

            # Over limit - return remaining window TTL as retry_after.
            ttl = await self._redis.ttl(rkey)
            retry_after = max(float(ttl), 0.0)
            return False, retry_after

        except Exception as exc:
            # If Redis is down, fail open (allow the request) so the system
            # degrades gracefully rather than blocking all traffic.
            logger.warning(
                "RedisRateLimiter.consume error for key=%r - failing open: %s",
                key, exc,
            )
            return True, 0.0

    async def reset(self, key: str) -> None:
        """Delete the counter for key (resets to zero on next request)."""
        try:
            await self._redis.delete(self._key(key))
        except Exception as exc:
            logger.warning("RedisRateLimiter.reset error: %s", exc)

    async def current_count(self, key: str) -> int:
        """Return the current request count for key in this window."""
        try:
            val = await self._redis.get(self._key(key))
            return int(val) if val is not None else 0
        except Exception:
            return 0

    async def check_voice_rate_limit(self, student_id: str, bypass_token: str = "") -> tuple[bool, str]:
        """Mirror the voice rate limiting interface used by the in-process limiter."""
        if bypass_token and is_bypass_token(bypass_token):
            logger.debug("[VOICE_RATE_LIMIT] Bypass token accepted for student_id=%s", student_id)
            return True, ""

        allowed, retry_after = await self.consume(student_id)
        if allowed:
            return True, ""

        remaining_wait = int(retry_after) if retry_after > 0 else 1
        return False, f"Slow down — wait {remaining_wait} seconds before speaking again."
