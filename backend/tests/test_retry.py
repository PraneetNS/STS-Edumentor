"""
test_retry.py — Unit tests for backend/utils/retry.py

Covers:
  - Successful first attempt (no retry triggered)
  - Retries exactly the right number of times before raising
  - Raises original exception after max attempts
  - Respects ``retry_on`` filter (does not retry unmatched exceptions)
  - Succeeds on a later attempt after initial failures
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
import pytest
from utils.retry import async_retry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine synchronously (Python 3.10+ compatible)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAsyncRetry:
    def test_succeeds_immediately(self):
        call_count = 0

        @async_retry(max_attempts=3, base_delay=0)
        async def fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = run(fn())
        assert result == "ok"
        assert call_count == 1

    def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @async_retry(max_attempts=3, base_delay=0)
        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        result = run(fn())
        assert result == "ok"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        call_count = 0

        @async_retry(max_attempts=3, base_delay=0)
        async def fn():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError, match="always fails"):
            run(fn())
        assert call_count == 3

    def test_does_not_retry_unmatched_exception(self):
        call_count = 0

        @async_retry(max_attempts=5, base_delay=0, retry_on=(TypeError,))
        async def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("not a TypeError")

        with pytest.raises(ValueError):
            run(fn())
        assert call_count == 1  # should NOT retry

    def test_retries_matched_exception(self):
        call_count = 0

        @async_retry(max_attempts=4, base_delay=0, retry_on=(TypeError,))
        async def fn():
            nonlocal call_count
            call_count += 1
            raise TypeError("retryable")

        with pytest.raises(TypeError):
            run(fn())
        assert call_count == 4

    def test_returns_value_on_retry_success(self):
        results = []

        @async_retry(max_attempts=5, base_delay=0)
        async def fn():
            results.append(1)
            if len(results) < 2:
                raise IOError("retry me")
            return 42

        assert run(fn()) == 42
        assert len(results) == 2

    def test_preserves_function_name(self):
        @async_retry(max_attempts=1, base_delay=0)
        async def my_special_function():
            return True

        assert my_special_function.__name__ == "my_special_function"
