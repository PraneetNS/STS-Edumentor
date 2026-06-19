"""
EduMentor Agent Layer — Emotion / Frustration Detector

Detects the student's emotional state from transcribed speech text.
This module is:
  - ZERO latency (no LLM call)
  - Pure rule-based (regex + keyword phrase matching)
  - Fully pluggable via the EmotionBackend protocol

Pipeline position:
  User transcript → detect() → EmotionResult → DialogueManager

The DialogueManager uses the result to inject style modifiers into the
system prompt, making the tutor feel genuinely empathetic.

Future upgrade path:
  Implement MLEmotionBackend (e.g. distilbert-emotion) and swap it in
  via the EmotionBackend protocol. Zero changes to DialogueManager required.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from agent.models import Emotion, EmotionResult

logger = logging.getLogger("edumentor.agent.emotion")


# ─────────────────────────────────────────────────────────────────────────────
# EmotionBackend Protocol (for future ML swap-in)
# ─────────────────────────────────────────────────────────────────────────────

class EmotionBackend(ABC):
    """Abstract backend for emotion detection. Swap implementations freely."""

    @abstractmethod
    def detect(self, text: str) -> EmotionResult:
        """Analyse text and return an EmotionResult."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Emotion Rule Definitions
# ─────────────────────────────────────────────────────────────────────────────

# Each rule is a (Emotion, List[phrase_or_regex], confidence) tuple.
# Rules are checked in order — first match wins.
# Phrases: simple case-insensitive substring matches.
# Regexes: strings starting with r"" are compiled as regex patterns.

_EMOTION_RULES: List[Tuple[Emotion, List[str], float]] = [
    # ── Frustrated — strong negative with repetition signals ─────────────────
    (Emotion.FRUSTRATED, [
        "i still don't understand",
        "i still dont understand",
        "this makes no sense",
        "i don't get it at all",
        "i dont get it at all",
        "i keep getting it wrong",
        "i've tried multiple times",
        "ive tried multiple times",
        "nothing is working",
        "nothing works",
        "i give up",
        "this is impossible",
        "why is this so hard",
        "i hate this",
        "so frustrating",
        "i'm so frustrated",
        "im so frustrated",
        "i don't understand anything",
        "i dont understand anything",
        r"explain.{0,20}again.{0,20}(please|again|one more)",
    ], 0.95),

    # ── Confused — uncertainty / lost signals ─────────────────────────────────
    (Emotion.CONFUSED, [
        "i'm confused",
        "im confused",
        "i am confused",
        "i'm lost",
        "im lost",
        "i am lost",
        "i don't understand",
        "i dont understand",
        "what does that mean",
        "i don't follow",
        "i dont follow",
        "can you explain",
        "i'm not sure",
        "im not sure",
        "what is that",
        "could you clarify",
        "what do you mean",
        "i'm having trouble",
        "im having trouble",
        "this is confusing",
        r"(don't|dont|not) (understand|get|follow)",
        r"what (is|are|does|do) (that|this|it)",
    ], 0.85),

    # ── Confident — positive understanding signals ────────────────────────────
    (Emotion.CONFIDENT, [
        "i understand now",
        "i get it now",
        "that makes sense",
        "i think i understand",
        "i think i get it",
        "got it",
        "i see",
        "now i understand",
        "that clicked",
        "it clicked",
        "makes sense to me",
        "i understand",
        "i figured it out",
        "i solved it",
        "i know how to",
        "makes total sense",
        r"(now |finally )?(i )?(get|understand|see) (it|that|this|now)",
    ], 0.9),

    # ── Happy — positive sentiment / gratitude ────────────────────────────────
    (Emotion.HAPPY, [
        "thank you",
        "thanks",
        "that was helpful",
        "that helped",
        "awesome",
        "amazing",
        "great explanation",
        "perfect",
        "exactly what i needed",
        "this is great",
        "wonderful",
        "fantastic",
        "excellent",
        "love it",
        "brilliant",
        "you're great",
        "youre great",
        r"(thank|thanks).{0,30}(so much|a lot|very much)",
    ], 0.85),

    # ── Bored — disengagement signals ────────────────────────────────────────
    (Emotion.BORED, [
        "this is boring",
        "can we do something else",
        "skip this",
        "let's move on",
        "lets move on",
        "i know this already",
        "i already know",
        "can we change",
        "something more interesting",
        "i'm bored",
        "im bored",
        r"(skip|move on|change|next|something else)",
    ], 0.80),
]


# ─────────────────────────────────────────────────────────────────────────────
# Rule-Based Backend Implementation
# ─────────────────────────────────────────────────────────────────────────────

class RuleBasedEmotionBackend(EmotionBackend):
    """
    Default backend: tiered matching using phrase lists + regex patterns.

    Matching tiers (in order):
      1. Exact phrase (case-insensitive substring)
      2. Regex pattern (if rule starts with r"")
      3. No match → Emotion.NEUTRAL
    """

    def __init__(self) -> None:
        # Pre-compile all rules into (emotion, compiled_patterns, confidence)
        self._compiled: List[Tuple[Emotion, List[re.Pattern], float]] = []

        for emotion, patterns, confidence in _EMOTION_RULES:
            compiled_patterns = []
            for p in patterns:
                # Detect if this looks like a regex (contains regex metacharacters)
                if any(c in p for c in r"()[]{}+*?\\"):
                    compiled_patterns.append(re.compile(p, re.IGNORECASE))
                else:
                    # Exact substring — escape and compile as plain pattern
                    compiled_patterns.append(
                        re.compile(re.escape(p), re.IGNORECASE)
                    )
            self._compiled.append((emotion, compiled_patterns, confidence))

    def detect(self, text: str) -> EmotionResult:
        """
        Check text against all emotion rules in priority order.

        Args:
            text: Transcribed user speech.

        Returns:
            EmotionResult — neutral if nothing matches.
        """
        if not text or not text.strip():
            return EmotionResult.neutral()

        text_lower = text.lower()

        for emotion, patterns, confidence in self._compiled:
            for pattern in patterns:
                m = pattern.search(text_lower)
                if m:
                    trigger = m.group(0)
                    logger.info(
                        "[EMOTION] detected=%s confidence=%.2f trigger=%r",
                        emotion.value, confidence, trigger
                    )
                    return EmotionResult(
                        emotion=emotion,
                        confidence=confidence,
                        trigger_phrase=trigger,
                    )

        return EmotionResult.neutral()


# ─────────────────────────────────────────────────────────────────────────────
# Public Singleton and API
# ─────────────────────────────────────────────────────────────────────────────

# Module-level singleton — instantiated once at import time
_backend: EmotionBackend = RuleBasedEmotionBackend()


def set_backend(backend: EmotionBackend) -> None:
    """
    Swap the emotion detection backend.

    Use this to upgrade from rule-based to ML-based detection
    without changing any calling code.

    Args:
        backend: Any object implementing the EmotionBackend protocol.
    """
    global _backend
    _backend = backend
    logger.info("EmotionDetector backend swapped to: %s", type(backend).__name__)


def detect(text: str) -> EmotionResult:
    """
    Detect emotion in the given text string.

    This is the primary public API. All callers (DialogueManager, Controller)
    should use this function rather than instantiating the backend directly.

    Args:
        text: Transcribed user speech (from Whisper).

    Returns:
        EmotionResult with detected emotion and metadata.
    """
    return _backend.detect(text)


# ─────────────────────────────────────────────────────────────────────────────
# Emotion → Dialogue Style Mapping
# ─────────────────────────────────────────────────────────────────────────────

# Used by DialogueManager to modify the system prompt based on detected emotion.
# Each entry defines tone, instructions, and an optional bridge phrase.
EMOTION_STYLE_MAP = {
    Emotion.FRUSTRATED: {
        "tone":           "extra_encouraging",
        "use_examples":   True,
        "simplify":       True,
        "advance_topic":  False,
        "change_format":  None,
        "bridge_phrase":  "That's completely okay — let's try a completely different angle on this.",
        "instructions": (
            "The student is frustrated. Be extra patient and encouraging. "
            "Start with an empathetic acknowledgement. "
            "Use a very simple, concrete analogy or real-world example. "
            "Break the explanation into tiny steps. "
            "End with positive reinforcement."
        ),
    },
    Emotion.CONFUSED: {
        "tone":           "patient",
        "use_examples":   True,
        "simplify":       True,
        "advance_topic":  False,
        "change_format":  None,
        "bridge_phrase":  "No worries at all — let me break this down step by step.",
        "instructions": (
            "The student is confused. Be patient and clear. "
            "Restate the concept from scratch using simpler vocabulary. "
            "Use a step-by-step walkthrough. "
            "Ask a simple clarifying question at the end to check understanding."
        ),
    },
    Emotion.CONFIDENT: {
        "tone":           "challenging",
        "use_examples":   False,
        "simplify":       False,
        "advance_topic":  True,
        "change_format":  None,
        "bridge_phrase":  "Great, you've got this! Let's push a bit further.",
        "instructions": (
            "The student is confident and understands. "
            "Advance to the next level of the topic or introduce a related challenge. "
            "You can use slightly more technical language. "
            "Consider asking a harder question to stretch their thinking."
        ),
    },
    Emotion.HAPPY: {
        "tone":           "warm",
        "use_examples":   False,
        "simplify":       False,
        "advance_topic":  False,
        "change_format":  None,
        "bridge_phrase":  "I'm really glad that clicked for you!",
        "instructions": (
            "The student is happy and engaged. Match their positive energy. "
            "Keep the momentum going. Build on what they just understood."
        ),
    },
    Emotion.BORED: {
        "tone":           "energetic",
        "use_examples":   True,
        "simplify":       False,
        "advance_topic":  True,
        "change_format":  "quiz",
        "bridge_phrase":  "Let's mix it up — how about a quick challenge?",
        "instructions": (
            "The student seems bored or disengaged. "
            "Immediately switch to a more interactive format. "
            "Try a quick quiz question or an interesting real-world application. "
            "Make it feel like a game or challenge."
        ),
    },
    Emotion.NEUTRAL: {
        "tone":           "default",
        "use_examples":   False,
        "simplify":       False,
        "advance_topic":  False,
        "change_format":  None,
        "bridge_phrase":  None,
        "instructions":   None,
    },
}


def get_style_for_emotion(emotion: Emotion) -> dict:
    """
    Retrieve the dialogue style configuration for a detected emotion.

    Args:
        emotion: The detected Emotion enum value.

    Returns:
        Dict with keys: tone, use_examples, simplify, advance_topic,
        change_format, bridge_phrase, instructions.
    """
    return EMOTION_STYLE_MAP.get(emotion, EMOTION_STYLE_MAP[Emotion.NEUTRAL])
