"""
EduMentor Voice — Audio Utilities

Helpers for audio format conversion and sentence boundary detection
used throughout the real-time pipeline.
"""

import re
import numpy as np
from typing import List


# ─────────────────────────────────────────────────────────────────────────────
# Audio format conversion
# ─────────────────────────────────────────────────────────────────────────────

def int16_bytes_to_float32(raw_bytes: bytes) -> np.ndarray:
    """
    Convert raw Int16 PCM bytes (sent from the browser AudioWorklet) to a
    Float32 numpy array in the range [-1.0, 1.0].

    The browser sends Int16 samples at 16 kHz mono — exactly what
    faster-whisper expects as input.

    Args:
        raw_bytes: Binary data where each 2-byte pair is a little-endian Int16 sample.

    Returns:
        Float32 numpy array normalised to [-1.0, 1.0].
    """
    if len(raw_bytes) == 0:
        return np.array([], dtype=np.float32)

    audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16)
    return audio_int16.astype(np.float32) / 32768.0


def float32_to_int16_bytes(audio: np.ndarray) -> bytes:
    """
    Convert a Float32 numpy array back to raw Int16 PCM bytes.
    Useful for debugging or alternative playback paths.
    """
    clipped = np.clip(audio, -1.0, 1.0)
    int16_array = (clipped * 32767).astype(np.int16)
    return int16_array.tobytes()


# ─────────────────────────────────────────────────────────────────────────────
# Sentence segmentation for TTS chunking
# ─────────────────────────────────────────────────────────────────────────────

# Clause-ending punctuation: comma, semicolon, colon, newline, etc.
_CLAUSE_END_RE = re.compile(r"(?<=\S{2})[,;:—\n\r]+(?:\s|$)")
# Sentence-ending punctuation: period, exclamation mark, question mark
_SENTENCE_END_RE = re.compile(r"(?<=\S{2})[.!?]+(?:\s|$)")

MIN_SENTENCE_CHARS = 3
MIN_CLAUSE_CHARS = 30


def is_sentence_complete(text: str) -> bool:
    """
    Return True if `text` ends with a sentence or clause boundary that is ready
    to be synthesized by TTS to minimize playback latency.

    Args:
        text: Accumulated token text so far.

    Returns:
        True if we should flush this text to TTS now.
    """
    stripped = text.strip()
    if not stripped:
        return False

    # Complete sentence: flush immediately if long enough
    if len(stripped) >= MIN_SENTENCE_CHARS and _SENTENCE_END_RE.search(stripped):
        return True

    # Clause boundary: flush if long enough for natural prosody
    if len(stripped) >= MIN_CLAUSE_CHARS and _CLAUSE_END_RE.search(stripped):
        return True

    return False


def split_into_sentences(text: str) -> List[str]:
    """
    Split a block of text into individual sentences for batch TTS processing.

    This is used when processing already-complete text (e.g. flushing the
    remaining buffer after LLM generation ends).

    Args:
        text: A paragraph or multi-sentence string.

    Returns:
        List of non-empty sentence strings.
    """
    # Split at sentence boundaries; keep trailing punctuation with its sentence
    parts = _SENTENCE_END_RE.split(text)
    sentences = []
    for part in parts:
        cleaned = part.strip()
        if cleaned:
            sentences.append(cleaned)
    return sentences or [text.strip()]


def validate_audio_chunk(chunk: bytes) -> bool:
    """
    Validate that the incoming binary frame does not exceed Config.MAX_AUDIO_CHUNK_BYTES.
    """
    from config import Config
    return len(chunk) <= Config.MAX_AUDIO_CHUNK_BYTES


def validate_utterance_duration(duration_seconds: float) -> bool:
    """
    Validate that the accumulated speech duration falls within the allowed range.
    Below MIN_UTTERANCE_MS/1000 is treated as noise, above MAX_UTTERANCE_SECONDS is forced cutoff.
    """
    from config import Config
    return Config.MIN_UTTERANCE_MS / 1000 <= duration_seconds <= Config.MAX_UTTERANCE_SECONDS

