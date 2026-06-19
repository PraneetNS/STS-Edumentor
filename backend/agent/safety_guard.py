"""
EduMentor Agent Layer — Safety Guard

Provides rule-based content safety filtering for both user input and LLM output.
This is intentionally a ZERO-LATENCY, ZERO-LLM implementation — pure regex and
keyword matching. The architecture uses a pluggable checker pattern so individual
rule sets can be swapped out for ML classifiers later without changing any
other code.

Pipeline position:
  User Input → [check_input()] → LLM → [check_output()] → Student

Design notes:
  - Each SafetyCategory is handled by its own _Checker class.
  - Checkers are composable and independently testable.
  - Keyword lists are intentionally conservative — prefer false negatives
    over blocking legitimate educational content.
  - The check_output() scanner is lighter (primarily for injected content).
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from agent.models import SafetyCategory, SafetyResult

logger = logging.getLogger("edumentor.agent.safety")


# ─────────────────────────────────────────────────────────────────────────────
# Base Checker Interface
# ─────────────────────────────────────────────────────────────────────────────

class _BaseChecker(ABC):
    """Abstract base for all safety rule checkers."""

    category: SafetyCategory  # Set by each subclass

    @abstractmethod
    def check(self, text: str) -> Optional[str]:
        """
        Inspect text for violations.

        Returns:
            The matched phrase/pattern if a violation is found, else None.
        """
        ...


class _KeywordChecker(_BaseChecker):
    """
    Simple case-insensitive keyword/phrase checker.

    Matches whole-word or phrase patterns from a list. Uses word-boundary
    anchors where possible to avoid false positives (e.g. 'kill' in 'skill').
    """

    def __init__(self, category: SafetyCategory, phrases: List[str]) -> None:
        self.category = category
        # Pre-compile all patterns at construction time for speed
        self._patterns: List[re.Pattern] = []
        for phrase in phrases:
            # Multi-word phrases: exact substring match (case-insensitive)
            # Single words: whole-word boundary match
            if " " in phrase:
                self._patterns.append(re.compile(re.escape(phrase), re.IGNORECASE))
            else:
                self._patterns.append(
                    re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
                )

    def check(self, text: str) -> Optional[str]:
        for pattern in self._patterns:
            m = pattern.search(text)
            if m:
                return m.group(0)
        return None


class _RegexChecker(_BaseChecker):
    """Custom regex-based checker for structured patterns (e.g. URLs, code)."""

    def __init__(self, category: SafetyCategory, patterns: List[str]) -> None:
        self.category = category
        self._patterns = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns]

    def check(self, text: str) -> Optional[str]:
        for pattern in self._patterns:
            m = pattern.search(text)
            if m:
                return m.group(0)[:80]  # Truncate for logging
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Category-specific Checkers
# ─────────────────────────────────────────────────────────────────────────────

_SELF_HARM_CHECKER = _KeywordChecker(SafetyCategory.SELF_HARM, [
    "kill myself", "end my life", "commit suicide", "want to die",
    "self-harm", "cut myself", "hurt myself", "i want to disappear",
    "i hate my life", "no reason to live",
])

_VIOLENCE_CHECKER = _KeywordChecker(SafetyCategory.VIOLENCE, [
    "how to kill", "how to murder", "make a bomb", "build a weapon",
    "how to hurt someone", "how to attack", "instructions to harm",
    "make explosives", "how to poison",
])

_ADULT_CHECKER = _KeywordChecker(SafetyCategory.ADULT, [
    "pornography", "sexual content", "explicit content", "nude photos",
    "generate explicit", "erotic",
])

_MALWARE_CHECKER = _KeywordChecker(SafetyCategory.MALWARE, [
    "write malware", "create virus", "ransomware code", "write a trojan",
    "keylogger code", "rootkit", "spyware code", "write a worm",
    "exploit code", "write a payload", "reverse shell",
    "bind shell", "meterpreter",
])

# Phishing / credential theft — look for patterns suggesting a social engineering request
_CREDENTIAL_CHECKER = _KeywordChecker(SafetyCategory.CREDENTIAL_THEFT, [
    "steal passwords", "harvest credentials", "credential stuffing",
    "brute force login", "bypass authentication", "dump password hashes",
    "crack password", "phishing email template", "fake login page",
    "social engineering script",
])

_PHISHING_CHECKER = _KeywordChecker(SafetyCategory.PHISHING, [
    "write a phishing", "send phishing", "phishing campaign",
    "spear phishing", "business email compromise", "bec attack",
])

_PRIVACY_CHECKER = _KeywordChecker(SafetyCategory.PRIVACY_ABUSE, [
    "stalk someone", "track someone without", "spy on my",
    "how to dox", "find someone's address", "get someone's location",
    "access someone else's account", "hack someone's account",
])

_EXAM_CHEATING_CHECKER = _KeywordChecker(SafetyCategory.EXAM_CHEATING, [
    "write my exam", "do my homework for me", "complete my assignment",
    "take my test", "answer my exam", "cheat on my test",
    "write my essay for submission", "do my coursework",
])

_PROMPT_INJECTION_CHECKER = _RegexChecker(SafetyCategory.PROMPT_INJECTION, [
    # Attempts to override system instructions
    r"ignore (all |your )?(previous |prior )?instructions",
    r"disregard (all |your )?(previous |prior )?instructions",
    r"forget (all |your )?(previous |prior )?instructions",
    r"you are now (a |an )?(?!EduMentor)",  # Persona override
    r"pretend (you are|to be) (?!EduMentor)",
    r"act as (a |an )?(?!EduMentor|a tutor|a teacher)",
    r"new system prompt",
    r"system:\s*(you are|ignore)",
])

_JAILBREAK_CHECKER = _RegexChecker(SafetyCategory.JAILBREAK, [
    r"DAN\s*(mode|prompt|jailbreak)",
    r"jailbreak (mode|prompt|yourself)",
    r"developer mode",
    r"no restrictions",
    r"without (any |your )?(ethical |moral )?restrictions",
    r"you have no (content |safety )?filters",
    r"bypass (your )?(safety|content|ethical) (filter|guardrail|restriction)",
])


# ─────────────────────────────────────────────────────────────────────────────
# Input and Output Checker Stacks
# ─────────────────────────────────────────────────────────────────────────────

# These checkers are run for user INPUT (student → backend).
# Order matters: cheapest/most common first.
_INPUT_CHECKERS: List[_BaseChecker] = [
    _PROMPT_INJECTION_CHECKER,   # Most common attack vector in AI systems
    _JAILBREAK_CHECKER,
    _SELF_HARM_CHECKER,
    _VIOLENCE_CHECKER,
    _MALWARE_CHECKER,
    _CREDENTIAL_CHECKER,
    _PHISHING_CHECKER,
    _EXAM_CHEATING_CHECKER,
    _PRIVACY_CHECKER,
    _ADULT_CHECKER,
]

# These checkers are run for LLM OUTPUT (backend → student).
# Lighter stack — primarily defends against prompt-injection-induced output.
_OUTPUT_CHECKERS: List[_BaseChecker] = [
    _MALWARE_CHECKER,
    _CREDENTIAL_CHECKER,
    _SELF_HARM_CHECKER,
    _ADULT_CHECKER,
]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def check_input(text: str) -> SafetyResult:
    """
    Run the full input safety scan on user-provided text.

    This is called BEFORE the intent classifier and LLM.
    If blocked, the controller should return a polite refusal without
    ever reaching the LLM.

    Args:
        text: The transcribed user speech.

    Returns:
        SafetyResult with allowed=True if clean, or a block reason if not.
    """
    if not text or not text.strip():
        return SafetyResult.safe()

    for checker in _INPUT_CHECKERS:
        match = checker.check(text)
        if match is not None:
            logger.warning(
                "[SAFETY INPUT BLOCKED] category=%s match=%r text=%r",
                checker.category.value, match, text[:60]
            )
            return SafetyResult.blocked(checker.category, details=match)

    return SafetyResult.safe()


def check_output(text: str) -> SafetyResult:
    """
    Run output safety scan on LLM-generated text.

    This is called AFTER LLM generation, before sending to TTS.
    Defends against prompt-injection attacks that manipulate LLM output.

    Args:
        text: The full or partial LLM response text.

    Returns:
        SafetyResult with allowed=True if clean.
    """
    if not text or not text.strip():
        return SafetyResult.safe()

    for checker in _OUTPUT_CHECKERS:
        match = checker.check(text)
        if match is not None:
            logger.warning(
                "[SAFETY OUTPUT BLOCKED] category=%s match=%r",
                checker.category.value, match
            )
            return SafetyResult.blocked(checker.category, details=match)

    return SafetyResult.safe()


# ─────────────────────────────────────────────────────────────────────────────
# Safe Response Generator
# ─────────────────────────────────────────────────────────────────────────────

# Student-friendly refusal messages keyed by safety category.
# These are spoken by the TTS, so they must be natural and non-alarming.
_REFUSAL_MESSAGES: dict = {
    SafetyCategory.SELF_HARM.value: (
        "I'm not able to help with that. If you're going through a difficult time, "
        "please reach out to a trusted person or a mental health helpline."
    ),
    SafetyCategory.VIOLENCE.value: (
        "That's not something I can help with. I'm here to support your learning journey."
    ),
    SafetyCategory.MALWARE.value: (
        "I can't help with creating harmful software. "
        "If you're studying cybersecurity, I'm happy to explain defensive concepts."
    ),
    SafetyCategory.CREDENTIAL_THEFT.value: (
        "That falls outside what I can help with. "
        "I'd love to teach you ethical hacking concepts instead."
    ),
    SafetyCategory.PHISHING.value: (
        "I can't assist with that. Let me know if you have a programming question I can help with."
    ),
    SafetyCategory.EXAM_CHEATING.value: (
        "I'm designed to help you learn, not to do the work for you. "
        "Let's work through this together step by step — you'll understand it much better that way."
    ),
    SafetyCategory.PROMPT_INJECTION.value: (
        "I noticed something unusual in that message. Could you rephrase your question?"
    ),
    SafetyCategory.JAILBREAK.value: (
        "I'm EduMentor, your AI tutor. I'm not able to change that role. "
        "What would you like to learn today?"
    ),
}

_DEFAULT_REFUSAL = (
    "I'm not able to help with that particular request. "
    "Is there something about programming or computer science I can help you learn?"
)


def get_refusal_message(safety_result: SafetyResult) -> str:
    """
    Return a student-friendly spoken refusal message for a blocked result.

    Args:
        safety_result: A SafetyResult with allowed=False.

    Returns:
        A natural-language refusal string suitable for TTS.
    """
    if safety_result.reason:
        return _REFUSAL_MESSAGES.get(safety_result.reason, _DEFAULT_REFUSAL)
    return _DEFAULT_REFUSAL
