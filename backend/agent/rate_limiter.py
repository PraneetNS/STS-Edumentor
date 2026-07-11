from collections import defaultdict
import logging
import secrets
import time
from config import Config

logger = logging.getLogger("edumentor.rate_limiter")


def is_bypass_token(token: str) -> bool:
    """
    Return True if *token* matches ``Config.RATE_LIMIT_BYPASS_TOKEN``.

    Uses :func:`secrets.compare_digest` to prevent timing-based token leakage.
    Returns False immediately when the bypass token is empty (default), so
    the feature is inert unless explicitly configured.

    Args:
        token: Value supplied by the client (e.g. from the
               ``X-RateLimit-Bypass`` HTTP header or WebSocket query param).

    Returns:
        True only when bypass is configured AND the token matches exactly.
    """
    configured = getattr(Config, "RATE_LIMIT_BYPASS_TOKEN", "").strip()
    if not configured or not token:
        return False
    return secrets.compare_digest(configured, token.strip())


class RateLimiter:
    def __init__(self):
        self.connections_per_ip: dict[str, int] = defaultdict(int)
        self.requests_per_student: dict[str, list[float]] = defaultdict(list)
        self.daily_requests: dict[str, int] = defaultdict(int)
        self.daily_reset_time: dict[str, float] = {}

        # Violation tracking (Fix 3)
        self.violations: dict[str, list[float]] = defaultdict(list)
        self.strict_mode_until: dict[str, float] = {}

    def check_connection_limit(self, ip: str, max_per_ip: int = None) -> bool:
        if max_per_ip is None:
            max_per_ip = Config.MAX_CONNECTIONS_PER_IP
        return self.connections_per_ip[ip] < max_per_ip

    def register_connection(self, ip: str):
        self.connections_per_ip[ip] += 1

    def release_connection(self, ip: str):
        self.connections_per_ip[ip] = max(0, self.connections_per_ip[ip] - 1)

    def check_rate_limit(self, student_id: str, max_per_minute: int = None, bypass_token: str = "") -> bool:
        # Developer bypass: skip rate limiting when a valid bypass token is provided
        if bypass_token and is_bypass_token(bypass_token):
            logger.debug("[RATE_LIMIT] Bypass token accepted for student_id=%s", student_id)
            return True
        now = time.time()
        if max_per_minute is None:
            if student_id in self.strict_mode_until and now < self.strict_mode_until[student_id]:
                max_per_minute = 5   # stricter limit while flagged (Fix 3)
            else:
                max_per_minute = Config.RATE_LIMIT_PER_MINUTE
                
        window = self.requests_per_student[student_id]
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= max_per_minute:
            return False
        window.append(now)
        return True

    def check_daily_limit(self, student_id: str, max_per_day: int = None) -> bool:
        if max_per_day is None:
            max_per_day = Config.RATE_LIMIT_DAILY_REQUESTS
        now = time.time()
        if student_id not in self.daily_reset_time or now > self.daily_reset_time[student_id]:
            self.daily_requests[student_id] = 0
            self.daily_reset_time[student_id] = now + 86400
        return self.daily_requests[student_id] < max_per_day

    def increment_daily(self, student_id: str):
        self.daily_requests[student_id] += 1

    def record_violation(self, student_id: str) -> int:
        now = time.time()
        window = self.violations[student_id]
        window[:] = [t for t in window if now - t < 600]  # 10 min window
        window.append(now)
        return len(window)

    def check_voice_rate_limit(self, student_id: str, bypass_token: str = "") -> tuple[bool, str]:
        # Developer bypass: skip voice rate limiting when a valid bypass token is provided
        if bypass_token and is_bypass_token(bypass_token):
            logger.debug("[VOICE_RATE_LIMIT] Bypass token accepted for student_id=%s", student_id)
            return True, ""
        import os
        now = time.time()
        window = self.requests_per_student[student_id]
        window[:] = [t for t in window if now - t < 60]
        MAX_PER_MINUTE = int(os.getenv("VOICE_RATE_LIMIT_PER_MINUTE", "12"))

        if len(window) >= MAX_PER_MINUTE:
            remaining_wait = 60 - (now - window[0])
            return False, f"Slow down — wait {remaining_wait:.0f} seconds before speaking again."

        # Burst protection: no more than 3 utterances in 5 seconds
        recent_burst = [t for t in window if now - t < 5]
        if len(recent_burst) >= 3:
            return False, "You're speaking too fast. Give me a moment to respond."

        window.append(now)
        return True, ""

    def apply_strict_limit(self, student_id: str, duration_seconds: int):
        self.strict_mode_until[student_id] = time.time() + duration_seconds

rate_limiter = RateLimiter()
