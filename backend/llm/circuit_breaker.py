import time
import asyncio
from config import Config

class CircuitOpenError(Exception):
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold=None, recovery_timeout=None, call_timeout=None):
        self.failure_threshold = failure_threshold if failure_threshold is not None else Config.CIRCUIT_FAILURE_THRESHOLD
        self.recovery_timeout = recovery_timeout if recovery_timeout is not None else Config.CIRCUIT_RECOVERY_TIMEOUT
        # call_timeout: how long to wait for first token from llama.cpp.
        # Q6_K models on first turn can take 15-30s on initial KV cache fill.
        # 8s trips the circuit on every cold start — use 60s instead.
        self.call_timeout = call_timeout if call_timeout is not None else max(Config.LLM_CALL_TIMEOUT_SECONDS, 60.0)
        self.failure_count = 0
        self.state = "closed"   # closed | open | half_open
        self.last_failure_time = 0

    def reset(self) -> None:
        """Fully reset the circuit breaker to closed state.
        Called on backend startup so stale open state from a previous
        crash/restart never blocks the first real request."""
        self.failure_count = 0
        self.state = "closed"
        self.last_failure_time = 0

    async def call(self, llm_func, *args, **kwargs):
        if self.state == "open":
            # recovery_timeout: try again sooner (10s default instead of 30s)
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half_open"
            else:
                raise CircuitOpenError("LLM circuit breaker is open")

        try:
            result = await asyncio.wait_for(
                llm_func(*args, **kwargs),
                timeout=self.call_timeout
            )
            if self.state == "half_open":
                self.state = "closed"
                self.failure_count = 0
            return result

        except (asyncio.TimeoutError, Exception) as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                print(f"[CIRCUIT BREAKER] Opened after {self.failure_count} failures")
            raise

llm_circuit = CircuitBreaker()
