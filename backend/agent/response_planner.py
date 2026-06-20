"""
EduMentor Agent Layer — Response Planner

Post-processes raw LLM token streams into clean, TTS-friendly speech.

The LLM sometimes generates markdown, code blocks, or overly long responses
that sound unnatural when spoken. This module cleans and formats the output
in real-time as tokens stream in.

Responsibilities:
  1. Strip markdown syntax (*, #, **, backticks, bullet hyphens)
  2. Replace code blocks with verbal descriptions
  3. Enforce maximum speaking length (~90 seconds, ~700 chars)
  4. Convert numbered lists to natural spoken language
  5. Optionally append a comprehension check question

Usage (streaming mode):
    planner = ResponsePlanner()
    async for token in llm_engine.stream_tokens(messages):
        planned_token = planner.process_token(token)
        if planned_token:
            # Send to TTS and frontend

Usage (batch mode — for post-processing full responses):
    cleaned = planner.plan(full_response_text, intent, profile)

Pipeline position:
  LLM token stream → ResponsePlanner.process_token() → cleaned token → TTS
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from agent.models import Intent, StudentProfile

logger = logging.getLogger("edumentor.agent.response_planner")

# Maximum characters in a spoken response (~90 seconds at average speaking speed)
MAX_SPEECH_CHARS = 700

# Code block fence pattern
_CODE_FENCE_RE = re.compile(r"```[\w]*\n?", re.DOTALL)

# Markdown bold/italic
_MARKDOWN_EMPHASIS_RE = re.compile(r"\*{1,3}([^*]+)\*{1,3}")

# Markdown headers
_MARKDOWN_HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)

# Bullet list items (leading - or * with space)
_BULLET_RE = re.compile(r"^[\-\*]\s+", re.MULTILINE)

# Numbered list items (1. 2. etc.)
_NUMBERED_LIST_RE = re.compile(r"^\d+\.\s+", re.MULTILINE)

# Inline code backticks
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# Comprehension check questions by intent
_COMPREHENSION_QUESTIONS: dict = {
    Intent.CONCEPT_EXPLANATION: [
        "Does that make sense so far?",
        "Would you like me to go deeper on any part of that?",
        "What questions do you have about that?",
    ],
    Intent.CODE_HELP: [
        "Does that approach make sense to you?",
        "Would you like to walk through any part step by step?",
    ],
    Intent.DEBUGGING: [
        "Does that fix the issue?",
        "Let me know if you see a different error after trying that.",
    ],
    Intent.SIMPLIFY: [
        "Is that clearer now?",
        "Does that analogy help?",
    ],
    Intent.FOLLOW_UP: [
        "Shall we go even deeper, or move on to something new?",
    ],
}


class ResponsePlanner:
    """
    Cleans and formats LLM responses for speech synthesis.

    Supports both streaming (token-by-token) and batch (full text) modes.

    The streaming mode works by accumulating tokens into an internal buffer,
    then flushing cleaned tokens for TTS processing.
    """

    def __init__(self) -> None:
        # State for streaming mode
        self._buffer: str = ""
        self._in_code_block: bool = False
        self._total_chars_sent: int = 0
        self._truncated: bool = False
        logger.info("[OK] ResponsePlanner ready.")

    def reset(self) -> None:
        """Reset streaming state at the start of each new turn."""
        self._buffer = ""
        self._in_code_block = False
        self._total_chars_sent = 0
        self._truncated = False

    # ─────────────────────────────────────────────────────────────────────────
    # Batch mode (full text processing)
    # ─────────────────────────────────────────────────────────────────────────

    def plan(
        self,
        raw_text: str,
        intent: Intent = Intent.CONCEPT_EXPLANATION,
        profile: Optional[StudentProfile] = None,
        add_comprehension_check: bool = True,
    ) -> str:
        """
        Process a complete LLM response for TTS output.

        Applies all cleaning rules and optionally appends a
        comprehension question based on the intent.

        Args:
            raw_text:               Full LLM response text.
            intent:                 The intent for this turn.
            profile:                Student profile (for level-aware decisions).
            add_comprehension_check: If True, append a natural question.

        Returns:
            Cleaned, TTS-ready text string.
        """
        if not raw_text:
            return ""

        cleaned = self._clean_text(raw_text)

        # Enforce max length
        if len(cleaned) > MAX_SPEECH_CHARS:
            cleaned = self._truncate_gracefully(cleaned, MAX_SPEECH_CHARS)
            logger.debug(
                "[PLANNER] Response truncated to %d chars.", len(cleaned)
            )

        # Add comprehension check for teaching intents
        if add_comprehension_check and intent in _COMPREHENSION_QUESTIONS:
            # Only add if response doesn't already end with a question
            if not cleaned.rstrip().endswith("?"):
                import random
                questions = _COMPREHENSION_QUESTIONS[intent]
                cleaned = cleaned.rstrip() + " " + random.choice(questions)

        logger.debug(
            "[PLANNER] Planned response: %d chars → %d chars",
            len(raw_text), len(cleaned)
        )
        return cleaned

    # ─────────────────────────────────────────────────────────────────────────
    # Streaming mode (token-by-token)
    # ─────────────────────────────────────────────────────────────────────────

    def process_token(self, token: str) -> Optional[str]:
        """
        Process a single LLM output token in streaming mode.

        Accumulates tokens and applies cleaning. Returns cleaned text
        or None if the token was consumed by a cleaning rule.

        Args:
            token: A single token string from the LLM stream.

        Returns:
            Cleaned token string, or None if suppressed.
        """
        # Hard cutoff at max length
        if self._truncated:
            return None

        self._buffer += token

        # Detect and skip code block fences
        if "```" in self._buffer:
            if not self._in_code_block:
                self._in_code_block = True
                # Emit a verbal replacement instead
                lang_match = re.search(r"```(\w+)", self._buffer)
                lang = lang_match.group(1).lower() if lang_match else "code"
                self._buffer = ""
                # Announce the code/diagram on screen rather than reading it
                if lang in ("mermaid", "diagram", "dot", "plantuml"):
                    return "[I have displayed a diagram on the screen.] "
                else:
                    return f"[I have shown a {lang} code example on the screen.] "
            else:
                self._in_code_block = False
                self._buffer = ""
                return None

        # While in a code block, suppress all tokens for TTS
        if self._in_code_block:
            self._buffer = ""
            return None

        # Apply cleaning to the token
        cleaned = self._clean_token(token)

        if cleaned:
            self._total_chars_sent += len(cleaned)

            # Check if we've exceeded max length
            if self._total_chars_sent > MAX_SPEECH_CHARS:
                self._truncated = True
                # Return a natural cutoff phrase
                return " I'll stop there. Feel free to ask for more detail."

        return cleaned if cleaned else None

    # ─────────────────────────────────────────────────────────────────────────
    # Internal cleaning methods
    # ─────────────────────────────────────────────────────────────────────────

    def _clean_text(self, text: str) -> str:
        """Apply all cleaning rules to a full text string."""

        # Remove code fences entirely (replace with description)
        text = re.sub(
            r"```[\w]*\n(.*?)```",
            lambda m: self._verbalize_code(m.group(1)),
            text,
            flags=re.DOTALL,
        )

        # Remove diagram/roadmap ASCII lines
        lines = text.split("\n")
        filtered_lines = []
        for line in lines:
            if not is_diagram_or_roadmap(line):
                filtered_lines.append(line)
        text = "\n".join(filtered_lines)

        # Remove markdown headers (## Header → just the text)
        text = _MARKDOWN_HEADER_RE.sub("", text)

        # Remove bold/italic markers, keep content
        text = _MARKDOWN_EMPHASIS_RE.sub(r"\1", text)

        # Replace inline code backticks with natural phrasing
        text = _INLINE_CODE_RE.sub(r"\1", text)

        # Convert numbered lists to spoken language
        text = self._convert_numbered_lists(text)

        # Convert bullet lists to spoken language
        text = _BULLET_RE.sub("Also, ", text)

        # Clean up excess whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"  +", " ", text)
        text = text.strip()

        return text

    def _clean_token(self, token: str) -> Optional[str]:
        """Apply lightweight cleaning to a single streaming token."""
        # Remove leading markdown bullets
        token = re.sub(r"^\s*[\-\*]\s", " ", token)
        # Remove markdown header symbols
        token = re.sub(r"^\s*#{1,6}\s+", "", token)
        # Remove bold/italic
        token = re.sub(r"\*{1,3}", "", token)
        # Remove backticks
        token = token.replace("`", "")
        return token if token else None

    def _verbalize_code(self, code: str) -> str:
        """Replace a code block with a verbal description."""
        # Check if the code is a mermaid/diagram
        if any(keyword in code for keyword in ("graph ", "subgraph", "-->", "sequenceDiagram")):
            return "[I have displayed a diagram on the screen.] "
        return "[I have shown a code example on the screen.] "

    def _convert_numbered_lists(self, text: str) -> str:
        """Convert '1. First' style lists to 'First, ... Second, ... Third, ...'."""
        ORDINALS = {
            "1": "First", "2": "Second", "3": "Third",
            "4": "Fourth", "5": "Fifth", "6": "Sixth",
            "7": "Seventh", "8": "Eighth", "9": "Ninth", "10": "Tenth",
        }

        def replacer(m):
            num = m.group(1)
            return f"{ORDINALS.get(num, f'Number {num}')}, "

        return re.sub(r"^(\d+)\.\s+", replacer, text, flags=re.MULTILINE)

    def _truncate_gracefully(self, text: str, max_chars: int) -> str:
        """
        Truncate text at max_chars, cutting at a sentence boundary if possible.
        """
        if len(text) <= max_chars:
            return text

        # Try to cut at last sentence boundary before max_chars
        truncated = text[:max_chars]
        last_period = max(
            truncated.rfind("."),
            truncated.rfind("!"),
            truncated.rfind("?"),
        )

        if last_period > max_chars * 0.7:  # If sentence boundary is reasonably close
            return truncated[:last_period + 1]

        # Otherwise cut at last word boundary
        last_space = truncated.rfind(" ")
        return truncated[:last_space] + "..."


def is_diagram_or_roadmap(text: str) -> bool:
    """
    Check if a sentence/line contains diagrams, roadmaps, or flowcharts.
    """
    # Check for arrows: ->, -->, =>, ==>, <-, <--
    if re.search(r"[-=]>", text) or re.search(r"<[-=]", text):
        return True
    # Check for ASCII box/tree layout connectors: | or +-- or |--
    if "|" in text or "+--" in text or "|--" in text:
        return True
    # Check for typical workflow step transitions, e.g. [Input] -> [Process]
    if re.search(r"\[.*\]\s*[-=]+>", text):
        return True
    return False
