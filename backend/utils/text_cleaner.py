"""
text_cleaner.py — Text normalisation helpers for the EduMentor Voice pipeline.

Cleans raw STT transcripts and LLM outputs before they are stored, displayed,
or forwarded to downstream processors.

Functions:
  - ``strip_filler_words``   – Remove common speech disfluencies (um, uh, etc.)
  - ``normalise_whitespace`` – Collapse multiple spaces / newlines.
  - ``remove_control_chars`` – Strip ASCII/Unicode control characters.
  - ``truncate_to_sentences``– Trim text to a maximum number of complete sentences.
  - ``clean_transcript``     – Convenience pipeline combining the above.
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FILLER_WORDS = {
    "um", "uh", "er", "ah", "like", "you know", "i mean",
    "sort of", "kind of", "basically", "literally", "right",
    "so", "well", "okay", "ok",
}

# Compiled pattern: whole-word match for each filler, case-insensitive
_FILLER_RE = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in sorted(_FILLER_WORDS, key=len, reverse=True)) + r')\b[,\s]*',
    re.IGNORECASE,
)

_MULTI_SPACE_RE = re.compile(r'[ \t]+')
_MULTI_NEWLINE_RE = re.compile(r'\n{3,}')
_SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s+')


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def strip_filler_words(text: str) -> str:
    """
    Remove common speech filler words from *text*.

    >>> strip_filler_words("Um, like, so basically you need to uh use a hash map.")
    'you need to use a hash map.'
    """
    return _FILLER_RE.sub(' ', text).strip()


def normalise_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs and reduce triple+ newlines to two."""
    text = _MULTI_SPACE_RE.sub(' ', text)
    text = _MULTI_NEWLINE_RE.sub('\n\n', text)
    return text.strip()


def remove_control_chars(text: str) -> str:
    """Strip ASCII control characters and Unicode format/control categories."""
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        # Keep printable + whitespace; drop Cc (control), Cf (format), Cs (surrogate)
        if cat.startswith('C') and ch not in ('\n', '\t', '\r'):
            continue
        cleaned.append(ch)
    return ''.join(cleaned)


def truncate_to_sentences(text: str, max_sentences: int = 5) -> str:
    """
    Return at most *max_sentences* complete sentences from *text*.

    Sentences are split on '.', '!', or '?' followed by whitespace.
    """
    if not text:
        return text
    sentences = _SENTENCE_END_RE.split(text.strip())
    trimmed = sentences[:max_sentences]
    result = ' '.join(s.strip() for s in trimmed if s.strip())
    # Ensure it ends with punctuation if we truncated
    if len(sentences) > max_sentences and result and result[-1] not in '.!?':
        result += '…'
    return result


def clean_transcript(text: str, *, strip_fillers: bool = True, max_sentences: int | None = None) -> str:
    """
    Full cleaning pipeline for raw STT transcripts.

    Steps:
      1. Remove control characters
      2. Optionally strip filler words
      3. Normalise whitespace
      4. Optionally truncate to *max_sentences*
    """
    text = remove_control_chars(text)
    if strip_fillers:
        text = strip_filler_words(text)
    text = normalise_whitespace(text)
    if max_sentences is not None:
        text = truncate_to_sentences(text, max_sentences)
    return text


# ---------------------------------------------------------------------------
# TTS-specific cleaner
# ---------------------------------------------------------------------------

_URL_RE          = re.compile(r'https?://\S+')
_CODE_FENCE_RE   = re.compile(r'```[^\n]*\n.*?```', re.DOTALL)
_INLINE_CODE_RE  = re.compile(r'`[^`]+`')
_MARKDOWN_RE     = re.compile(r'[*_~#>|\\]')
_ELLIPSIS_RE     = re.compile(r'\.{2,}')


def sanitise_for_tts(text: str) -> str:
    """
    Prepare LLM output text for TTS synthesis.

    Strips elements that should not be spoken aloud:
      - Code fences (``` blocks ```)
      - Inline backtick code spans
      - URLs (http/https)
      - Markdown formatting characters (* _ ~ # > | \\)
      - Excessive ellipses (converted to a natural pause marker)

    Returns:
        Cleaned text suitable for passing directly to a TTS engine.
    """
    text = _CODE_FENCE_RE.sub('', text)
    text = _INLINE_CODE_RE.sub('', text)
    text = _URL_RE.sub('', text)
    text = _MARKDOWN_RE.sub('', text)
    text = _ELLIPSIS_RE.sub('…', text)
    return normalise_whitespace(text)

