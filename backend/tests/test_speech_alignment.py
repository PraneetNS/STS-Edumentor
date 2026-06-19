"""
Tests — Speech Alignment Layer

Covers forced word-timestamp estimation logic using mock WAV bytes.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from speech.alignment import estimate_word_timestamps


def test_estimate_word_timestamps_empty_or_invalid():
    # Empty text
    assert estimate_word_timestamps("", b"some wav audio bytes") == []
    
    # Empty audio bytes
    assert estimate_word_timestamps("hello world", b"") == []
    
    # Audio bytes smaller than header size (44 bytes)
    assert estimate_word_timestamps("hello world", b"\x00" * 40) == []
    
    # Audio bytes exactly header size
    assert estimate_word_timestamps("hello world", b"\x00" * 44) == []


def test_estimate_word_timestamps_normal():
    # 2 seconds of 16-bit PCM mono audio at 24000 Hz:
    # 2 seconds * 24000 samples/sec * 2 bytes/sample = 96000 data bytes
    # Plus 44-byte WAV header = 96044 bytes
    wav_bytes = b"\x00" * (44 + 96000)
    text = "hello world"
    
    results = estimate_word_timestamps(text, wav_bytes, sample_rate=24000)
    
    # We expect 2 words
    assert len(results) == 2
    
    # Word 1: hello (5 chars)
    # Word 2: world (5 chars)
    # total_word_chars = 10, total duration = 2.0s
    # char_duration = (2.0 * 0.85) / 10 = 0.17
    # space_duration = (2.0 * 0.15) / 1 = 0.3
    # Word 1 (hello): start = 0.0, end = 5 * 0.17 = 0.85
    # Word 2 (world): start = 0.85 + 0.30 = 1.15, end = 1.15 + 0.85 = 2.0
    
    assert results[0]["word"] == "hello"
    assert results[0]["start"] == 0.0
    assert results[0]["end"] == 0.85
    assert results[0]["index"] == 0
    
    assert results[1]["word"] == "world"
    assert results[1]["start"] == 1.15
    assert results[1]["end"] == 2.0
    assert results[1]["index"] == 1


def test_estimate_word_timestamps_single_word():
    # 1 second of 16-bit PCM mono audio at 24000 Hz:
    # 1 second * 24000 samples/sec * 2 bytes/sample = 48000 data bytes
    # Plus 44-byte WAV header = 48044 bytes
    wav_bytes = b"\x00" * (44 + 48000)
    text = "test"
    
    results = estimate_word_timestamps(text, wav_bytes, sample_rate=24000)
    
    # 1 word, total duration = 1.0s
    # char_duration = (1.0 * 0.85) / 4 = 0.2125
    # space_duration = (1.0 * 0.15) / max(1, 0) = (1.0 * 0.15) / 1 = 0.15
    # Word (test): start = 0.0, end = 4 * 0.2125 = 0.85
    
    assert len(results) == 1
    assert results[0]["word"] == "test"
    assert results[0]["start"] == 0.0
    assert results[0]["end"] == 0.85
    assert results[0]["index"] == 0


def test_estimate_word_timestamps_extra_spaces():
    wav_bytes = b"\x00" * (44 + 96000)
    # Extra spaces and trailing spaces should be normalized
    text = "   hello   world   "
    
    results = estimate_word_timestamps(text, wav_bytes, sample_rate=24000)
    
    assert len(results) == 2
    assert results[0]["word"] == "hello"
    assert results[1]["word"] == "world"
    assert results[1]["end"] == 2.0
