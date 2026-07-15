"""
backend/speech/endpointing.py

Semantic endpointing for EduMentor Voice.

Goal: decide *when* the user has actually finished talking, instead of
always waiting a fixed VAD_SILENCE_TIMEOUT. This module only ever makes
that decision EARLIER than the fixed timeout for high-confidence complete
utterances, or EXTENDS it slightly (bounded by a hard ceiling) when the
transcript clearly trails off mid-thought (e.g. ends on "and", "um").

Design constraints (deliberate, do not relax without re-testing):
  1. Zero new dependencies, zero model load, zero GPU. Pure rule-based
     text analysis on already-available transcript state. This must never
     become the latency bottleneck.
  2. Operates ONLY on stabilizer.py's *confirmed* words, never temporary/
     hypothesis words -- avoids firing early on noisy or half-formed ASR
     output.
  3. Hard max ceiling means the worst case is never worse than today's
     fixed-timeout behavior (as long as ENDPOINT_MAX_SILENCE_MS >=
     current VAD_SILENCE_TIMEOUT).
  4. Fully feature-flagged. ENDPOINTING_MODE=fixed reproduces the exact
     legacy behavior with zero code-path risk.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Config (mirror these in backend/config.py + .env; shown here with safe
# defaults so this module works standalone / in unit tests too)
# ---------------------------------------------------------------------------

class EndpointingMode(str, Enum):
    FIXED = "fixed"        # legacy behavior: always wait full max_silence_ms
    ADAPTIVE = "adaptive"  # new semantic behavior


@dataclass
class EndpointingConfig:
    mode: EndpointingMode = EndpointingMode.FIXED
    # Fired immediately once silence + confident-complete transcript.
    min_silence_ms: int = 250
    # Used when the transcript is ambiguous (mirrors old default).
    default_silence_ms: int = 800
    # Hard ceiling. Never wait longer than this regardless of signal.
    # Keep >= your current VAD_SILENCE_TIMEOUT so ADAPTIVE can only help.
    max_silence_ms: int = 1200
    # How often the decision function gets polled while silent.
    check_interval_ms: int = 100
    # Below this many confirmed words, don't allow fast-fire (avoids
    # "um" / "okay" / noise blips triggering a premature finalize).
    min_words_for_fast_fire: int = 2


# ---------------------------------------------------------------------------
# Lexicons -- tune these against your own transcript logs over time.
# ---------------------------------------------------------------------------

# Words that, if trailing, strongly signal "more is coming."
# Hesitation, thinking, and filler tokens (like hmm, hmmm, err, mhm) are included here
# to prevent the VAD from cutting the user off early when they pause to think.
_TRAILING_INCOMPLETE = {
    "and", "but", "so", "or", "because", "um", "uh", "like", "the", "a",
    "an", "to", "with", "for", "of", "in", "on", "is", "are", "was",
    "were", "that", "which", "if", "then", "also", "well", "actually",
    "basically", "i", "you", "we", "my", "your", "hmm", "hmmm", "uhm",
    "err", "mhm", "ah", "eh",
}

# Sentence-final punctuation from the normalizer/stabilizer output.
_TERMINAL_PUNCT = re.compile(r"[.?!]\s*$")

# Interrogative openers -- questions are usually complete once they hit a
# terminal token, and are lower-risk to fast-fire on (tutoring context =
# mostly Q&A).
_QUESTION_STARTERS = re.compile(
    r"^\s*(what|why|how|when|where|who|which|is|are|can|could|does|do|"
    r"did|will|would|should|explain|tell)\b",
    re.IGNORECASE,
)


class Completeness(str, Enum):
    CONFIDENT_COMPLETE = "confident_complete"
    AMBIGUOUS = "ambiguous"
    TRAILING_INCOMPLETE = "trailing_incomplete"


@dataclass
class EndpointDecision:
    should_finalize: bool
    reason: str
    completeness: Completeness
    effective_wait_ms: int


class SemanticEndpointer:
    """
    Stateless-per-call decision function. Call this on every VAD "tick"
    while the user is silent (roughly every check_interval_ms), passing
    the CONFIRMED transcript text so far and elapsed silence duration.
    """

    def __init__(self, config: Optional[EndpointingConfig] = None):
        self.config = config or EndpointingConfig()

    def classify_completeness(self, confirmed_text: str) -> Completeness:
        """
        Classifies the confirmed text into CONFIDENT_COMPLETE, AMBIGUOUS, or TRAILING_INCOMPLETE completeness categories
        by checking terminal punctuation, question patterns, and trailing grammatical fillers.
        """
        text = confirmed_text.strip()
        if not text:
            return Completeness.AMBIGUOUS

        words = text.split()
        last_word = re.sub(r"[^\w']", "", words[-1]).lower() if words else ""

        if last_word in _TRAILING_INCOMPLETE:
            return Completeness.TRAILING_INCOMPLETE

        has_terminal_punct = bool(_TERMINAL_PUNCT.search(text))
        looks_like_question = bool(_QUESTION_STARTERS.search(text))

        if has_terminal_punct and len(words) >= self.config.min_words_for_fast_fire:
            return Completeness.CONFIDENT_COMPLETE

        if looks_like_question and len(words) >= self.config.min_words_for_fast_fire:
            # Question word + no trailing filler + reasonable length is a
            # strong enough signal even without punctuation (Whisper drops
            # punctuation sometimes on short utterances).
            return Completeness.CONFIDENT_COMPLETE

        return Completeness.AMBIGUOUS

    def decide(
        self,
        confirmed_text: str,
        silence_elapsed_ms: int,
    ) -> EndpointDecision:
        cfg = self.config

        if cfg.mode == EndpointingMode.FIXED:
            should_finalize = silence_elapsed_ms >= cfg.default_silence_ms
            decision = EndpointDecision(
                should_finalize=should_finalize,
                reason="fixed_mode",
                completeness=Completeness.AMBIGUOUS,
                effective_wait_ms=cfg.default_silence_ms,
            )
        else:
            completeness = self.classify_completeness(confirmed_text)

            # Hard safety net: never exceed max_silence_ms regardless of signal.
            if silence_elapsed_ms >= cfg.max_silence_ms:
                decision = EndpointDecision(
                    should_finalize=True,
                    reason="max_silence_ceiling",
                    completeness=completeness,
                    effective_wait_ms=cfg.max_silence_ms,
                )
            elif completeness == Completeness.CONFIDENT_COMPLETE:
                should_finalize = silence_elapsed_ms >= cfg.min_silence_ms
                decision = EndpointDecision(
                    should_finalize=should_finalize,
                    reason="confident_complete_fast_fire",
                    completeness=completeness,
                    effective_wait_ms=cfg.min_silence_ms,
                )
            elif completeness == Completeness.TRAILING_INCOMPLETE:
                # Don't finalize on the default timeout either -- push toward
                # the ceiling, but the ceiling check above still protects us.
                should_finalize = False
                decision = EndpointDecision(
                    should_finalize=should_finalize,
                    reason="trailing_incomplete_extend",
                    completeness=completeness,
                    effective_wait_ms=cfg.max_silence_ms,
                )
            else:
                # AMBIGUOUS -- behave like today's system.
                should_finalize = silence_elapsed_ms >= cfg.default_silence_ms
                decision = EndpointDecision(
                    should_finalize=should_finalize,
                    reason="ambiguous_default_timeout",
                    completeness=completeness,
                    effective_wait_ms=cfg.default_silence_ms,
                )

        from observability.metrics import endpoint_decision_total
        endpoint_decision_total.labels(reason=decision.reason).inc()
        return decision
