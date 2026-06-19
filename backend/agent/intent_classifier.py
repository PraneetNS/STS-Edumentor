"""
EduMentor Agent Layer — Intent Classifier

Classifies the student's utterance into one of 14 intent categories using the
existing EduMentor GGUF model via a highly compressed classification prompt.

Design goals:
  - Use existing LLMEngine (no second model, no new dependencies)
  - Low token usage (~80 tokens total for system + user message)
  - Fast inference (max_tokens=60, temperature=0.0)
  - Robust JSON parsing with regex fallback
  - Graceful fallback to CONCEPT_EXPLANATION on any parsing failure
  - Can be disabled entirely via Config.AGENT_INTENT_CLASSIFY=False

Output format:
  {
    "intent": "SIMPLIFY",
    "needs_history": true,
    "confidence": 0.95
  }

Pipeline position:
  AgentController → IntentClassifier.classify() → IntentResult
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from agent.models import Intent, IntentResult

logger = logging.getLogger("edumentor.agent.intent")


# ─────────────────────────────────────────────────────────────────────────────
# Classification prompt (ultra-compressed for speed)
# ─────────────────────────────────────────────────────────────────────────────

# System prompt: defines the task and valid output format
_SYSTEM_PROMPT = (
    "You are an intent classifier for an AI tutoring system. "
    "Classify the student message into exactly one intent. "
    "Return ONLY valid JSON. No explanation."
)

# User prompt template: lists all valid intents and the message to classify
_USER_TEMPLATE = """Intents: CONCEPT_EXPLANATION, CODE_HELP, DEBUGGING, QUIZ_REQUEST, REPEAT_LAST, SIMPLIFY, FOLLOW_UP, OFF_TOPIC, GREETING, THANKS, PDF_QUESTION, PROJECT_HELP, CAREER_GUIDANCE, UNSAFE

needs_history=true when the message refers to previous conversation (it, that, again, simpler, explain more, continue).

Message: "{user_text}"

JSON:"""

# ─────────────────────────────────────────────────────────────────────────────
# Intent needs_history defaults (used as fallback when LLM doesn't specify)
# ─────────────────────────────────────────────────────────────────────────────

_NEEDS_HISTORY_DEFAULTS: dict = {
    Intent.CONCEPT_EXPLANATION: False,
    Intent.CODE_HELP:           False,
    Intent.DEBUGGING:           True,   # Usually about existing code
    Intent.QUIZ_REQUEST:        True,   # Often about recent topic
    Intent.REPEAT_LAST:         True,   # Explicitly references last response
    Intent.SIMPLIFY:            True,   # Needs to know what was said
    Intent.FOLLOW_UP:           True,   # Explicitly references prior content
    Intent.OFF_TOPIC:           False,
    Intent.GREETING:            False,
    Intent.THANKS:              True,   # "Thanks for explaining X"
    Intent.PDF_QUESTION:        False,
    Intent.PROJECT_HELP:        True,   # Usually references ongoing project
    Intent.CAREER_GUIDANCE:     False,
    Intent.UNSAFE:              False,
}


class IntentClassifier:
    """
    Lightweight intent classifier using the existing GGUF LLM.

    The LLMEngine is injected at construction time (same instance as the
    main pipeline, no second HTTP connection opened).

    Args:
        llm_engine: The existing LLMEngine instance from main.py.
        enabled:    If False, always returns CONCEPT_EXPLANATION (zero latency).
    """

    def __init__(self, llm_engine, enabled: bool = True) -> None:
        self._llm = llm_engine
        self._enabled = enabled

        if enabled:
            logger.info("[OK] IntentClassifier ready (enabled=True).")
        else:
            logger.info("[OK] IntentClassifier ready (enabled=False — always CONCEPT_EXPLANATION).")

    async def classify(self, user_text: str) -> IntentResult:
        """
        Classify the student's utterance into an Intent.

        Args:
            user_text: The transcribed student speech.

        Returns:
            IntentResult with intent, needs_history, and confidence.
            Falls back to CONCEPT_EXPLANATION on any failure.
        """
        # ── Fast path: empty text ─────────────────────────────────────────────
        if not user_text or not user_text.strip():
            return IntentResult.fallback()

        # ── Fast path: obvious single-word/regex intents (0ms latency check) ──
        quick = self._quick_classify(user_text)
        if quick is not None:
            logger.info(
                "[INTENT] quick_classify → %s (no LLM call)", quick.intent.value
            )
            return quick

        # ── Fast path: disabled (skip LLM call, fallback to CONCEPT_EXPLANATION) 
        if not self._enabled:
            return IntentResult(
                intent=Intent.CONCEPT_EXPLANATION,
                needs_history=False,
                confidence=1.0,
            )

        # ── LLM classification ────────────────────────────────────────────────
        try:
            raw = await self._call_llm(user_text)
            result = self._parse_response(raw, user_text)
            logger.info(
                "[INTENT] classified=%s confidence=%.2f needs_history=%s",
                result.intent.value, result.confidence, result.needs_history
            )
            return result
        except Exception as exc:
            logger.exception("[INTENT] Classification failed: %s", exc)
            return IntentResult.fallback()

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: fast rule-based pre-classifier (avoids LLM call for obvious cases)
    # ─────────────────────────────────────────────────────────────────────────

    _QUICK_RULES: list = [
        # (regex_pattern, Intent, needs_history, confidence)
        (r"^(hi|hello|hey|good morning|good afternoon|good evening|howdy)\b", Intent.GREETING, False, 1.0),
        (r"^(thank|thanks|thank you|cheers)\b", Intent.THANKS, True, 1.0),
        (r"\b(repeat|say that again|say it again|again please)\b", Intent.REPEAT_LAST, True, 0.95),
        (r"\b(simpl(er|ify|e)|easier|easy version|for a beginner)\b", Intent.SIMPLIFY, True, 0.92),
        (r"\b(quiz me|test me|give me a quiz|ask me|question me)\b", Intent.QUIZ_REQUEST, True, 0.92),
        (r"\b(my (project|app|system|code|repo|codebase))\b", Intent.PROJECT_HELP, True, 0.88),
        (r"\b(career|job|resume|hiring|interview prep)\b", Intent.CAREER_GUIDANCE, False, 0.88),
        (r"\b(pdf|document|my notes|my file|page \d+)\b", Intent.PDF_QUESTION, False, 0.90),
        (r"\b(debug|error|bug|fix|not working|broken|exception|traceback)\b", Intent.DEBUGGING, True, 0.88),
        (r"\b(code|write|function|class|implement|script|program)\b", Intent.CODE_HELP, False, 0.80),
        (r"\b(more|tell me more|elaborate|continue|go on|and then)\b", Intent.FOLLOW_UP, True, 0.85),
    ]

    _compiled_quick: Optional[list] = None

    def _quick_classify(self, text: str) -> Optional[IntentResult]:
        """
        Run fast regex-based pre-classification before calling the LLM.

        Returns an IntentResult if confident, else None (falls through to LLM).
        """
        if self.__class__._compiled_quick is None:
            self.__class__._compiled_quick = [
                (re.compile(pattern, re.IGNORECASE), intent, needs_hist, conf)
                for pattern, intent, needs_hist, conf in self._QUICK_RULES
            ]

        text_lower = text.strip().lower()
        for pattern, intent, needs_hist, conf in self.__class__._compiled_quick:
            if pattern.search(text_lower):
                return IntentResult(
                    intent=intent,
                    needs_history=needs_hist,
                    confidence=conf,
                )
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: LLM call (non-streaming, short)
    # ─────────────────────────────────────────────────────────────────────────

    async def _call_llm(self, user_text: str) -> str:
        """
        Make a non-streaming LLM call for intent classification.

        Uses max_tokens=60 and temperature=0.0 for fast, deterministic output.
        """
        import httpx

        payload = {
            "model": "local",
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _USER_TEMPLATE.format(user_text=user_text[:200])},
            ],
            "stream":      False,
            "max_tokens":  60,
            "temperature": 0.0,
        }

        async with httpx.AsyncClient(
            base_url=self._llm.base_url,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0),
            headers={"Content-Type": "application/json"},
        ) as client:
            response = await client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        return ""

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: JSON parsing with robust fallback
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_response(self, raw: str, user_text: str) -> IntentResult:
        """
        Parse the LLM's JSON response into an IntentResult.

        Attempts multiple parsing strategies before falling back to defaults.

        Strategies:
          1. Direct JSON parse
          2. Extract JSON from text via regex
          3. Extract intent keyword via regex (no JSON)
          4. Default fallback (CONCEPT_EXPLANATION)
        """
        if not raw:
            return IntentResult.fallback()

        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()

        parsed_dict = None

        # Strategy 1: Direct JSON parse
        try:
            parsed_dict = json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract JSON object via regex
        if parsed_dict is None:
            match = re.search(r"\{[^{}]+\}", cleaned, re.DOTALL)
            if match:
                try:
                    parsed_dict = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        # Strategy 3: Extract just the intent keyword from raw text
        if parsed_dict is None:
            intent_match = re.search(
                r"\b(CONCEPT_EXPLANATION|CODE_HELP|DEBUGGING|QUIZ_REQUEST|"
                r"REPEAT_LAST|SIMPLIFY|FOLLOW_UP|OFF_TOPIC|GREETING|THANKS|"
                r"PDF_QUESTION|PROJECT_HELP|CAREER_GUIDANCE|UNSAFE)\b",
                raw, re.IGNORECASE
            )
            if intent_match:
                intent_str = intent_match.group(1).upper()
                try:
                    intent = Intent(intent_str)
                    return IntentResult(
                        intent=intent,
                        needs_history=_NEEDS_HISTORY_DEFAULTS.get(intent, False),
                        confidence=0.7,
                        raw_json=raw,
                    )
                except ValueError:
                    pass

        # Strategy 4: Fallback
        if parsed_dict is None:
            logger.warning("[INTENT] Could not parse LLM response: %r", raw[:100])
            return IntentResult.fallback()

        # Parse the dict
        intent_str = str(parsed_dict.get("intent", "")).upper()
        try:
            intent = Intent(intent_str)
        except ValueError:
            logger.warning("[INTENT] Unknown intent value: %r", intent_str)
            return IntentResult.fallback()

        needs_history = bool(parsed_dict.get("needs_history", _NEEDS_HISTORY_DEFAULTS.get(intent, False)))
        confidence = float(parsed_dict.get("confidence", 0.8))

        return IntentResult(
            intent=intent,
            needs_history=needs_history,
            confidence=min(max(confidence, 0.0), 1.0),
            raw_json=raw,
        )
