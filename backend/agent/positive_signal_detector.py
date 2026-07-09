"""
backend/agent/positive_signal_detector.py

Detects confidence/excitement/pride so Edi can celebrate a student
nailing something, instead of only reacting to negative emotions
(confused/frustrated/bored) the way emotion_detector.py and
speech/emotion.py currently do.

Why this is deliberately conservative, not just "detect happy tone":

  Audio pitch and energy alone cannot reliably distinguish excitement
  from frustration -- both raise pitch variance and loudness. A student
  who's frustrated and talking loudly must never get treated as if
  they're excited; that would land as tone-deaf, not encouraging.

  So this detector uses CORRECTNESS as a hard gate, not just a scoring
  input:
    - answer_was_correct=False -> always PositiveEmotion.NONE, full stop,
      regardless of how enthusiastic the text or audio sounds.
    - Text cues ("got it", "!", "definitely") and audio energy are
      AMPLIFIERS on top of a correct answer, never standalone triggers.
    - Audio energy specifically only counts when there's already a
      nonzero textual/contextual score -- it cannot single-handedly
      produce a celebration.

  This mirrors the same posture as endpointing.py and the queue module:
  rule-based, fast, no new model/dependency, and the failure mode is
  "occasionally too conservative" rather than "occasionally embarrassing."
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PositiveEmotion(str, Enum):
    NONE = "none"
    CONFIDENT = "confident"   # correct, calm, matter-of-fact
    EXCITED = "excited"       # correct + enthusiastic language/energy
    PROUD = "proud"           # correct on a topic that was previously a weak area


@dataclass
class PositiveSignalConfig:
    enabled: bool = False
    min_intensity_to_celebrate: float = 0.4   # 0.0-1.0 gate


_EXCITED_MARKERS = {
    "got it", "i got it", "finally", "oh i see", "that makes sense",
    "makes sense now", "i understand now", "aha", "i see it now", "yes!",
}
_CONFIDENT_MARKERS = {
    "i'm sure", "definitely", "of course", "easy", "obviously", "no doubt",
}
_EXCLAMATION = re.compile(r"!")


@dataclass
class PositiveSignal:
    emotion: PositiveEmotion
    intensity: float  # 0.0-1.0, informational even when below threshold
    reason: str        # comma-separated contributing factors, for logging/tuning


class PositiveSignalDetector:
    def __init__(self, config: Optional[PositiveSignalConfig] = None):
        self.config = config or PositiveSignalConfig()

    def detect(
        self,
        transcript_text: str,
        *,
        answer_was_correct: Optional[bool] = None,
        previously_weak_topic: bool = False,
        audio_energy_delta: Optional[float] = None,
    ) -> PositiveSignal:
        """
        answer_was_correct: pass this from whatever already grades quiz/
            check-answer intents. None means "not applicable" (e.g. a
            free-form question, not a graded check) -- text/audio cues
            can still produce a mild CONFIDENT signal in that case, but
            never PROUD (which requires a genuine correctness win).
        previously_weak_topic: from student_profile.py's weak_areas.
        audio_energy_delta: optional +/- signal from speech/emotion.py
            (e.g. RMS energy relative to the student's own baseline).
            Only ever amplifies an existing nonzero score.
        """
        if not self.config.enabled:
            return PositiveSignal(PositiveEmotion.NONE, 0.0, "disabled")

        # Hard gate: a wrong answer is never a celebration, no matter how
        # enthusiastic it sounds. This is not a scoring input -- it's a
        # short-circuit.
        if answer_was_correct is False:
            return PositiveSignal(PositiveEmotion.NONE, 0.0, "answer_incorrect")

        text = (transcript_text or "").lower()
        score = 0.0
        reasons = []

        if answer_was_correct is True:
            score += 0.5
            reasons.append("correct_answer")

        if any(marker in text for marker in _EXCITED_MARKERS):
            score += 0.3
            reasons.append("excited_language")

        if any(marker in text for marker in _CONFIDENT_MARKERS):
            score += 0.2
            reasons.append("confident_language")

        if _EXCLAMATION.search(text):
            score += 0.1
            reasons.append("exclamation")

        if previously_weak_topic and answer_was_correct:
            score += 0.2
            reasons.append("overcame_weak_topic")

        # Amplifier only -- never fires on its own (guarded by score > 0).
        if audio_energy_delta is not None and score > 0 and audio_energy_delta > 0.15:
            score += 0.15
            reasons.append("elevated_audio_energy")

        score = min(1.0, score)
        reason_str = ",".join(reasons) if reasons else "no_signal"

        if score < self.config.min_intensity_to_celebrate:
            return PositiveSignal(PositiveEmotion.NONE, score, f"below_threshold:{reason_str}")

        if previously_weak_topic and answer_was_correct:
            emotion = PositiveEmotion.PROUD
        elif any(marker in text for marker in _EXCITED_MARKERS):
            emotion = PositiveEmotion.EXCITED
        else:
            emotion = PositiveEmotion.CONFIDENT

        return PositiveSignal(emotion, score, reason_str)
