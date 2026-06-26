from collections import defaultdict
import time
from config import Config

class TokenBudget:
    def __init__(self):
        self.daily_tokens: dict[str, int] = defaultdict(int)
        self.daily_reset: dict[str, float] = {}
        self.MAX_DAILY_TOKENS = Config.MAX_DAILY_TOKENS
        self.MAX_CONTEXT_TOKENS = Config.MAX_CONTEXT_TOKENS

    def estimate_tokens(self, text: str) -> int:
        # Rough estimate: 1 token ≈ 4 characters for English
        return max(1, len(text) // 4)

    def check_daily_budget(self, student_id: str) -> bool:
        now = time.time()
        if student_id not in self.daily_reset or now > self.daily_reset[student_id]:
            self.daily_tokens[student_id] = 0
            self.daily_reset[student_id] = now + 86400
        return self.daily_tokens[student_id] < self.MAX_DAILY_TOKENS

    def record_usage(self, student_id: str, prompt_tokens: int, completion_tokens: int):
        self.daily_tokens[student_id] += prompt_tokens + completion_tokens

    def enforce_context_limit(self, context_text: str) -> str:
        """Truncate context to fit budget, keep most recent turns"""
        if self.estimate_tokens(context_text) <= self.MAX_CONTEXT_TOKENS:
            return context_text
        # Truncate from the start, keep the tail (most recent)
        target_chars = self.MAX_CONTEXT_TOKENS * 4
        return context_text[-target_chars:]

token_budget = TokenBudget()
