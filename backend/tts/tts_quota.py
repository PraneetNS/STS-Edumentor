import time
from collections import defaultdict
from config import Config

class TTSQuota:
    def __init__(self):
        self.daily_chars: dict[str, int] = defaultdict(int)
        self.daily_reset: dict[str, float] = {}
        self.MAX_DAILY_CHARS = Config.MAX_DAILY_TTS_CHARS

    def check_budget(self, student_id: str) -> bool:
        now = time.time()
        if student_id not in self.daily_reset or now > self.daily_reset[student_id]:
            self.daily_chars[student_id] = 0
            self.daily_reset[student_id] = now + 86400
        return self.daily_chars[student_id] < self.MAX_DAILY_CHARS

    def record_usage(self, student_id: str, char_count: int):
        self.daily_chars[student_id] += char_count

tts_quota = TTSQuota()
