"""
retry.py — Async retry decorator with exponential back-off and jitter.

Provides ``@async_retry`` for wrapping coroutines that may fail transiently
(network calls, LLM API requests, WebSocket reconnects).

Features:
  - Configurable max attempts, base delay, and back-off multiplier
  - Optional jitter to avoid thundering-herd on simultaneous retries
  - Selective exception filtering via ``retry_on`` parameter
  - Structured logging of each attempt

Usage::

    from utils.retry import async_retry

    @async_retry(max_attempts=4, base_delay=0.5, backoff=2.0)
    async def call_llm(prompt: str) -> str:
        ...

    # Retry only on specific exceptions
    @async_retry(max_attempts=3, retry_on=(httpx.TimeoutException,))
    async def fetch_health(url: str) -> dict:
        ...
"""

import asyncio
import functools
import logging
import random
from collections.abc import Callable, Coroutine
from typing import Any, Type

log = logging.getLogger("edumentor.retry")


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    jitter: float = 0.25,
    max_delay: float = 30.0,
    retry_on: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable | None = None,
) -> Callable:
    """
    Decorator factory: wrap an async function with retry logic.

    Args:
        max_attempts: Total number of tries including the first attempt.
        base_delay:   Seconds to wait before the second attempt.
        backoff:      Exponential multiplier applied to delay each retry.
        jitter:       Fraction of delay to randomise (0 = no jitter).
        max_delay:    Hard ceiling on the computed wait (default 30 s).
        retry_on:     Exception types that trigger a retry (default: all).
        on_retry:     Optional async callable ``(attempt, exc, wait)`` invoked
                      before each sleep, e.g. to emit metrics or send alerts.

    Returns:
        Decorator that adds retry behaviour to a coroutine function.
    """
    def decorator(fn: Callable[..., Coroutine]) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except retry_on as exc:  # type: ignore[misc]
                    last_exc = exc
                    if attempt == max_attempts:
                        log.error(
                            "Max retries reached for %s after %d attempts: %s",
                            fn.__qualname__,
                            attempt,
                            exc,
                        )
                        raise

                    jitter_offset = random.uniform(-jitter * delay, jitter * delay)
                    wait = min(max(0.0, delay + jitter_offset), max_delay)
                    log.warning(
                        "Attempt %d/%d for %s failed (%s). Retrying in %.2fs…",
                        attempt,
                        max_attempts,
                        fn.__qualname__,
                        exc,
                        wait,
                    )
                    if on_retry is not None:
                        try:
                            await on_retry(attempt, exc, wait)
                        except Exception:
                            pass  # Never let the callback abort the retry loop
                    await asyncio.sleep(wait)
                    delay = min(delay * backoff, max_delay)

            # Should never be reached, but satisfies type checkers
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
