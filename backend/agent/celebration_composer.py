"""
backend/agent/celebration_composer.py

Composes celebratory response prefixes and speed boosts when positive
emotional engagement (confidence/excitement/pride) is detected.
"""

from __future__ import annotations

import time
import random
from dataclasses import dataclass
from typing import Dict, List, Optional
from agent.positive_signal_detector import PositiveEmotion, PositiveSignal


@dataclass
class CelebrationConfig:
    enabled: bool = False
    min_speed_boost: float = 0.03
    max_speed_boost: float = 0.12
    cooldown_s: float = 8.0
    recent_history_size: int = 4


@dataclass
class CelebrationResult:
    phrase: str
    speed_multiplier: float


class CelebrationComposer:
    def __init__(self, config: Optional[CelebrationConfig] = None):
        self.config = config or CelebrationConfig()
        self.last_celebration_time: Dict[str, float] = {}
        self.recent_phrases: Dict[str, List[str]] = {}

        self.phrase_pools = {
            PositiveEmotion.EXCITED: [
                "Yes, exactly!",
                "That's it!",
                "Nailed it!",
                "You've got it!",
                "That's exactly right!"
            ],
            PositiveEmotion.CONFIDENT: [
                "Perfect.",
                "Correct.",
                "Spot on.",
                "Absolutely."
            ],
            PositiveEmotion.PROUD: [
                "Fantastic job!",
                "Sensational!",
                "I knew you could do it!",
                "Outstanding progress!"
            ]
        }

    def compose(self, session_id: str, signal: PositiveSignal) -> Optional[CelebrationResult]:
        if not self.config.enabled:
            return None

        if signal.emotion == PositiveEmotion.NONE:
            return None

        now = time.time()
        last_time = self.last_celebration_time.get(session_id, 0.0)
        if now - last_time < self.config.cooldown_s:
            return None

        pool = self.phrase_pools.get(signal.emotion, [])
        if not pool:
            return None

        history = self.recent_phrases.setdefault(session_id, [])
        available_phrases = [p for p in pool if p not in history]
        if not available_phrases:
            available_phrases = pool

        chosen_phrase = random.choice(available_phrases)

        history.append(chosen_phrase)
        if len(history) > self.config.recent_history_size:
            history.pop(0)

        boost = self.config.min_speed_boost + (self.config.max_speed_boost - self.config.min_speed_boost) * signal.intensity
        speed_multiplier = round(1.0 + boost, 4)

        self.last_celebration_time[session_id] = now

        return CelebrationResult(phrase=chosen_phrase, speed_multiplier=speed_multiplier)
