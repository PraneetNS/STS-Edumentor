import hashlib
import time

class IdempotencyGuard:
    def __init__(self, window_seconds: float = 1.0):
        self.window = window_seconds
        # key -> (timestamp, result_or_None)
        self._seen: dict[str, tuple[float, str | None]] = {}

    def _make_key(self, session_id: str, transcript: str) -> str:
        h = hashlib.sha256(f"{session_id}:{transcript.strip().lower()}".encode()).hexdigest()[:16]
        return h

    def is_duplicate(self, session_id: str, transcript: str) -> bool:
        key = self._make_key(session_id, transcript)
        now = time.monotonic()
        if key in self._seen:
            ts, _ = self._seen[key]
            if now - ts < self.window:
                return True
        return False

    def register(self, session_id: str, transcript: str):
        key = self._make_key(session_id, transcript)
        self._seen[key] = (time.monotonic(), None)

    def cleanup(self):
        now = time.monotonic()
        self._seen = {k: v for k, v in self._seen.items()
                      if now - v[0] < self.window * 2}

idempotency_guard = IdempotencyGuard(window_seconds=1.0)
