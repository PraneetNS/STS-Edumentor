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
    r"override (all |your )?(previous |prior )?instructions",
    r"you are now (a |an )?(?!EduMentor)",  # Persona override
    r"pretend (you are|to be) (?!EduMentor)",
    r"act as (a |an )?(?!EduMentor|a tutor|a teacher)",
    r"new system prompt",
    r"system:\s*(you are|ignore)",
    # System prompt extraction variants
    r"reveal (your )?system prompt",
    r"show (your )?system prompt",
    r"(output|print|repeat|display) (your )?(system )?(prompt|instructions)",
    r"what is (your )?system prompt",
    # Special token injection (breaks model context boundary)
    r"<\|(?:im_start|im_end|system|user|assistant|endoftext)\|>",
    r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>",
    r"###\s*(System|Instruction|Human|Assistant)\s*:",
    # Indirect / nested injection
    r"complete (the )?(sentence|text|phrase).{0,30}you are",
    r"continue (the )?(sentence|text).{0,30}ignore",
    # Translation / encoding attacks
    r"translate (your )?(system prompt|instructions|rules) (to|into)",
    r"(encode|decode|convert) (your )?(system prompt|instructions) (to|as|in)",
    # Context window poisoning
    r"(everything|all text) (above|before) (this|these) (line|message|prompt)",
    # Authority impersonation
    r"(i am|this is) (your )?(developer|creator|admin|operator|openai|anthropic|meta)",
    r"(as (your|the) )?(developer|creator|admin|operator) i (am )?(?:instruct|order|tell|command)ing you",
])

_JAILBREAK_CHECKER = _RegexChecker(SafetyCategory.JAILBREAK, [
    r"DAN\s*(mode|prompt|jailbreak)",
    r"jailbreak (mode|prompt|yourself)",
    r"developer mode",
    r"god mode",
    r"no restrictions",
    r"unrestricted mode",
    r"without (any |your )?(ethical |moral )?restrictions",
    r"you have no (content |safety )?filters",
    r"bypass (your )?(safety|content|ethical) (filter|guardrail|restriction)",
    # Hypothetical / fictional framing to bypass safety
    r"hypothetically (speaking )?if you had no (restrictions|filters|safety)",
    r"in a (story|novel|game|simulation) where (you|an ai) (has no|ignores)",
    r"imagine you (have no|are without) (restrictions|filters|safety|guidelines)",
    # Capability probing
    r"what (can you really do|are your real capabilities|are you actually allowed)",
    r"(show|tell|reveal) me (your )?(real|true|actual|hidden) (capabilities|self|mode|instructions)",
])

# ── LLM07: Roleplay / persona-swap jailbreak patterns ─────────────────────
# Pen testers don't ask directly for the system prompt — they use roleplay
# framing, translation requests, completion attacks, and hypothetical framing.
# These catch the input-side of those attacks. The output-side is caught by
# check_output_for_system_leak() regardless of how the input was framed.
ROLEPLAY_JAILBREAK_PATTERNS = [
    r"(?i)pretend (you'?re|you are|to be)",
    # 'act as if/though you are/you're' — not 'act as a tutor/interviewer'
    r"(?i)act as (if |though )(you'?re|you are)",
    r"(?i)in this (hypothetical|fictional|imaginary) scenario",
    r"(?i)for (educational|research) purposes only,? (ignore|disregard|bypass)",
    r"(?i)write a story where (an? ai|you) (reveals?|tells?|shares?)",
    # Catches 'translate your system prompt into French' and
    # 'translate the instructions above into Spanish'
    r"(?i)translate.{0,40}(system prompt|instructions).{0,20}(to|into|above)",
    r"(?i)repeat (the )?(words?|text|sentence)s? above",
    # Catches 'what would you say if' and 'what did you respond with'
    r"(?i)what (would|did) you (say|respond) (if|with)",
]

_ROLEPLAY_JAILBREAK_CHECKER = _RegexChecker(
    SafetyCategory.JAILBREAK, ROLEPLAY_JAILBREAK_PATTERNS
)


# ─────────────────────────────────────────────────────────────────────────────
# Input and Output Checker Stacks
# ─────────────────────────────────────────────────────────────────────────────

# These checkers are run for user INPUT (student → backend).
# Order matters: cheapest/most common first.
_INPUT_CHECKERS: List[_BaseChecker] = [
    _PROMPT_INJECTION_CHECKER,   # Most common attack vector in AI systems
    _JAILBREAK_CHECKER,
    _ROLEPLAY_JAILBREAK_CHECKER,  # LLM07: persona-swap / indirect extraction
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

# Known Limitation: The safety guard injection regex patterns are English-only.
# Highly multi-lingual jailbreak attempts or non-Latin queries might bypass English regexes.
# To mitigate this, we calculate the ratio of non-Latin characters and check the intent classifier's off_topic label.

BASE64_PAT = re.compile(r'\b[A-Za-z0-9+/]{8,}=*\b')
LEET_MAP = str.maketrans("13405@", "ieaosa")

# PII Detection Patterns
AADHAAR_RE = re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\+?\d{1,4}[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{3,4}[-.\s]?\d{4}")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

HEDGING_PATTERNS = ["i think", "probably", "i'm not entirely sure", "might be"]


def normalize_leetspeak(text: str) -> str:
    """Normalize common leetspeak substitutions (e.g. 1->i, 3->e, 4->a, 0->o, 5->s, @->a)."""
    return text.translate(LEET_MAP)


def decode_base64_substrings(text: str) -> List[str]:
    """Base64-decode any suspicious-looking base64 substrings in the transcript."""
    import base64
    decoded_texts = []
    for match in BASE64_PAT.finditer(text):
        candidate = match.group(0)
        # Pad candidate if needed
        missing_padding = len(candidate) % 4
        if missing_padding:
            candidate += '=' * (4 - missing_padding)
        try:
            decoded = base64.b64decode(candidate).decode('utf-8', errors='ignore')
            if decoded.strip():
                decoded_texts.append(decoded)
        except Exception:
            pass
    return decoded_texts


def get_non_latin_ratio(text: str) -> float:
    """Calculate the ratio of non-Latin alphabetic characters in the text."""
    alphas = [c for c in text if c.isalpha()]
    if not alphas:
        return 0.0
    non_latin = [c for c in alphas if not (
        (65 <= ord(c) <= 90) or (97 <= ord(c) <= 122) or (192 <= ord(c) <= 255) or (384 <= ord(c) <= 591)
    )]
    return len(non_latin) / len(alphas)


def redact_pii(text: str) -> str:
    """Redact email patterns to your.email@example.com and phone/SSN/Aadhaar to XXX-XXX-XXXX."""
    text = EMAIL_RE.sub("your.email@example.com", text)
    text = PHONE_RE.sub("XXX-XXX-XXXX", text)
    text = AADHAAR_RE.sub("XXX-XXX-XXXX", text)
    text = SSN_RE.sub("XXX-XXX-XXXX", text)
    return text


def check_hedging(text: str) -> Optional[str]:
    """Check if the text contains hedging patterns indicating low confidence."""
    text_lower = text.lower()
    for pattern in HEDGING_PATTERNS:
        if pattern in text_lower:
            return pattern
    return None


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

    # 1. Check standard input checkers
    for checker in _INPUT_CHECKERS:
        match = checker.check(text)
        if match is not None:
            logger.warning(
                "[SAFETY INPUT BLOCKED] category=%s match=%r text=%r",
                checker.category.value, match, text[:60]
            )
            return SafetyResult.blocked(checker.category, details=match)

    # 2. Check leetspeak substitutions
    normalized_leet = normalize_leetspeak(text)
    if normalized_leet != text:
        for checker in _INPUT_CHECKERS:
            match = checker.check(normalized_leet)
            if match is not None:
                logger.warning(
                    "[SAFETY INPUT LEETSPEAK BLOCKED] category=%s match=%r text=%r",
                    checker.category.value, match, text[:60]
                )
                return SafetyResult.blocked(checker.category, details=f"Leetspeak: {match}")

    # 3. Check base64 obfuscation
    decoded_texts = decode_base64_substrings(text)
    for decoded_text in decoded_texts:
        res = check_input(decoded_text)
        if not res.allowed:
            logger.warning(
                "[SAFETY INPUT BASE64 BLOCKED] text=%r decoded=%r reason=%s",
                text[:60], decoded_text[:60], res.reason
            )
            return SafetyResult.blocked(
                SafetyCategory(res.reason) if res.reason else SafetyCategory.JAILBREAK,
                details=f"Base64: {res.details}"
            )

    return SafetyResult.safe()


# ─────────────────────────────────────────────────────────────────────────────
# LLM07: Output-stage system prompt leak detection
# ─────────────────────────────────────────────────────────────────────────────

# Patterns indicating the LLM has leaked its own system configuration.
# These are checked AFTER generation — not on the input — so they catch
# extraction attempts regardless of how the input was crafted: roleplay,
# translation, completion attacks, or direct asks all get caught here.
SYSTEM_LEAK_INDICATORS = [
    r"(?i)you are edi\b",                                    # model repeating its own framing
    r"(?i)you are edumentor\b",
    r"(?i)as an? (ai|language model|assistant) (configured|instructed|told)",
    r"(?i)my (system prompt|instructions) (say|state|tell me|are)",
    r"(?i)llama\.cpp|kokoro|faster.whisper|chromadb|postgresql",  # stack names
    r"(?i)temperature.{0,30}0\.\d+",                        # leaked generation params (any phrasing)
    r"(?i)max_tokens|top_p|repeat_penalty",
    r"(?i)as an? (ai|language model|assistant).{0,30}(configured|instructed|told)",
]

_SYSTEM_LEAK_COMPILED = [
    re.compile(p, re.IGNORECASE) for p in SYSTEM_LEAK_INDICATORS
]


def check_output_for_system_leak(response_text: str) -> bool:
    """
    Scan LLM output for signs that system configuration has been leaked.

    Called AFTER LLM generation, at the output stage in controller.py.
    Returns True if a leak indicator is found (caller should replace the
    response with an EduMentor identity redirect).

    This is the primary defence against LLM07 (system prompt extraction).
    Because it operates on the OUTPUT, it catches attacks regardless of
    how the input was crafted — roleplay, translation requests, completion
    attacks, and direct asks are all caught here.

    Args:
        response_text: The full assembled LLM response string.

    Returns:
        True  → leak detected, replace response.
        False → response is clean.
    """
    if not response_text or not response_text.strip():
        return False
    matched = any(p.search(response_text) for p in _SYSTEM_LEAK_COMPILED)
    if matched:
        logger.warning(
            "[SAFETY OUTPUT SYSTEM-LEAK] Potential system prompt leak detected. "
            "response_preview=%r", response_text[:120]
        )
    return matched


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


class StreamingPIIFilter:
    def __init__(self, lookback_chars: int = 40):
        self.buffer = ""
        self.lookback_chars = lookback_chars
        self.released_length = 0

    def process_token(self, token: str) -> str:
        """
        Returns the text that is now safe to release downstream.
        Holds back the last `lookback_chars` of the buffer on
        every call so a pattern split across token boundaries
        is always checked as a whole before release.
        """
        self.buffer += token

        # Don't release the tail — PII might still be forming
        safe_to_check = self.buffer[:-self.lookback_chars] if len(self.buffer) > self.lookback_chars else ""

        if not safe_to_check:
            return ""

        redacted = redact_pii(safe_to_check)

        release_length = len(safe_to_check)
        new_release = redacted[self.released_length:] if self.released_length < len(redacted) else redacted
        self.released_length = release_length

        return new_release

    def flush(self) -> str:
        """Call when stream ends — release everything remaining"""
        redacted = redact_pii(self.buffer)
        remaining = redacted[self.released_length:]
        self.released_length = len(redacted)
        return remaining


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
        "I'm EduMentor. I can't process instructions that try to change how I work. "
        "What engineering topic can I help you with?"
    ),
    SafetyCategory.JAILBREAK.value: (
        "I'm EduMentor, your AI engineering tutor. That's not something I can help with. "
        "What would you like to learn today?"
    ),
}

# Categories whose inputs must NEVER be stored in conversation_logs or memory.
# Storing them would allow injected instructions to resurface in future prompts.
DB_DISCARD_CATEGORIES = {
    SafetyCategory.PROMPT_INJECTION.value,
    SafetyCategory.JAILBREAK.value,
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

