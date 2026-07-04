"""
Tests — Audio Utilities
"""

import sys
import os
import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import Config
from utils.audio import (
    int16_bytes_to_float32,
    float32_to_int16_bytes,
    is_sentence_complete,
    split_into_sentences,
    validate_audio_chunk,
    validate_utterance_duration,
)


def test_int16_bytes_to_float32():
    # Empty bytes should yield empty float32 array
    assert len(int16_bytes_to_float32(b"")) == 0
    
    # 2 bytes = 1 sample (Int16, little-endian)
    raw = b"\x00\x00\x00\x40"  # 0, 16384 (which is 0.5 when divided by 32768)
    arr = int16_bytes_to_float32(raw)
    assert len(arr) == 2
    assert arr[0] == 0.0
    assert arr[1] == 0.5


def test_float32_to_int16_bytes():
    arr = np.array([0.0, 0.5, 1.0, -1.0], dtype=np.float32)
    raw = float32_to_int16_bytes(arr)
    # Check that output length is correct (4 samples * 2 bytes = 8 bytes)
    assert len(raw) == 8
    
    # Check clipping
    arr_large = np.array([2.0, -2.0], dtype=np.float32)
    raw_clipped = float32_to_int16_bytes(arr_large)
    arr_decoded = int16_bytes_to_float32(raw_clipped)
    # 32767/32768 is ~0.9999
    assert np.allclose(arr_decoded, [0.9999, -1.0], atol=1e-3)


def test_is_sentence_complete():
    # Empty or white spaces
    assert is_sentence_complete("") is False
    assert is_sentence_complete("   ") is False
    
    # Short question/statement
    assert is_sentence_complete("H.") is False  # too short (< 3 chars)
    assert is_sentence_complete("Hello, world!") is True  # >= 3 chars, ends with exclamation
    assert is_sentence_complete("What is recursion?") is True
    
    # Clauses
    assert is_sentence_complete("This is a short clause;") is False  # < 30 chars
    assert is_sentence_complete("This is a sufficiently long sentence that is structured as a clause; ") is True  # >= 30 chars


def test_split_into_sentences():
    text = "Hello! How are you doing today? I am a voice tutor."
    s = split_into_sentences(text)
    assert len(s) == 3
    assert s[0] == "Hello"
    assert s[1] == "How are you doing today"
    assert s[2] == "I am a voice tutor"
    
    # Single sentence
    assert split_into_sentences("Just one.") == ["Just one"]


def test_validate_audio_chunk():
    # Large chunk exceeding maximum size limit
    chunk = b"\x00" * (Config.MAX_AUDIO_CHUNK_BYTES + 1)
    assert validate_audio_chunk(chunk) is False
    
    # Normal chunk
    assert validate_audio_chunk(b"\x00" * 512) is True


def test_validate_utterance_duration():
    assert validate_utterance_duration(0.01) is False  # too short
    assert validate_utterance_duration(15.0) is True
    assert validate_utterance_duration(120.0) is False  # too long (default max: 60s)
