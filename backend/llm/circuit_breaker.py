import time
import asyncio
from config import Config

class CircuitOpenError(Exception):
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold=None, recovery_timeout=None, call_timeout=None):
        self.failure_threshold = failure_threshold if failure_threshold is not None else Config.CIRCUIT_FAILURE_THRESHOLD
        self.recovery_timeout = recovery_timeout if recovery_timeout is not None else Config.CIRCUIT_RECOVERY_TIMEOUT
        self.call_timeout = call_timeout if call_timeout is not None else Config.LLM_CALL_TIMEOUT_SECONDS
        self.failure_count = 0
        self.state = "closed"   # closed | open | half_open
        self.last_failure_time = 0

    async def call(self, llm_func, *args, **kwargs):
        if self.state == "open":
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
