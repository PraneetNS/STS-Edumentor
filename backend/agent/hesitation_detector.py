"""
backend/agent/hesitation_detector.py

Detects pure filler/hesitation speech turns (e.g., "hmm", "uhh", "umm...")
with no substantive content, allowing the agent to provide proactive guidance.

Distinction from emotion_detector.py's "confused" classification:
  - emotion_detector.py works on SUBSTANTIVE text that expresses confusion
    (e.g., "I don't get how memory allocation works...").
  - hesitation_detector.py handles the case where there is NO substantive text
    at all (e.g., just "uhhhh...").
  - These two modules are complementary and run without conflict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class HesitationSignal:
    detected: bool
    confidence: float
    reason: str


class HesitationDetector:
    def __init__(self) -> None:
        # Matches hmm, mhm, uh, um, err, ah, eh, uhm, and their elongated variants (e.g. hmmmm, uhhhh, ummmm, errrr)
        # Considers word boundaries to prevent matching words like "hammer", "umbrella", "error", etc.
        self.filler_pattern = re.compile(
            r"^(h+m+|u+h+|u+m+|e+r+|m+h+m+|a+h+|e+h+|uhm)$",
            re.IGNORECASE
        )

    def detect(self, finalized_transcript: str, audio_energy_signal: Optional[float] = None) -> HesitationSignal:
        """
        Analyze the finalized transcript and optional prosody signal to detect pure hesitation.

        audio_energy_signal: optional RMS energy or energy delta from the audio.
            Only acts as an amplifier to raise confidence if the text gate has already passed;
            it cannot trigger detection on its own.
        """
        if not finalized_transcript:
            return HesitationSignal(detected=False, confidence=0.0, reason="empty_transcript")

        # Strip punctuation and convert to lowercase for matching
        # Keeping only letters, numbers, and spaces
        cleaned = re.sub(r"[^\w\s]", "", finalized_transcript).strip().lower()
        if not cleaned:
            return HesitationSignal(detected=False, confidence=0.0, reason="no_words_after_cleaning")

        words = cleaned.split()
        
        # Hard gate: every single word in the finalized transcript must be a hesitation marker
        is_pure_filler = True
        for w in words:
            if not self.filler_pattern.match(w):
                is_pure_filler = False
                break

        if not is_pure_filler:
            return HesitationSignal(detected=False, confidence=0.0, reason="substantive_content_present")

        # Base confidence for pure filler text
        confidence = 0.7
        reasons = ["pure_filler_text"]

        # Prosody amplifier only - raises confidence when the text gate has already passed
        if audio_energy_signal is not None and audio_energy_signal > 0.15:
            # Add a prosody boost (capped at 1.0)
            confidence = min(1.0, confidence + 0.15)
            reasons.append("elevated_audio_energy")

        return HesitationSignal(detected=True, confidence=confidence, reason=",".join(reasons))
