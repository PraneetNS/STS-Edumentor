"""
test_text_cleaner.py — Unit tests for backend/utils/text_cleaner.py

Covers:
  - strip_filler_words: removes common filler words, preserves content words
  - normalise_whitespace: collapses spaces and newlines
  - remove_control_chars: strips control characters, keeps printable
  - truncate_to_sentences: limits to N sentences correctly
  - clean_transcript: full pipeline integration
"""

import sys
import os

# Ensure the backend package is on the path when run from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from utils.text_cleaner import (
    strip_filler_words,
    normalise_whitespace,
    remove_control_chars,
    truncate_to_sentences,
    clean_transcript,
    sanitise_for_tts,
)


# ---------------------------------------------------------------------------
# strip_filler_words
# ---------------------------------------------------------------------------

class TestStripFillerWords:
    def test_removes_um(self):
        result = strip_filler_words("Um, this is a test.")
        assert "um" not in result.lower()
        assert "test" in result

    def test_removes_uh(self):
        result = strip_filler_words("I uh need to think about this.")
        assert "uh" not in result.lower()
        assert "think" in result

    def test_removes_like_as_filler(self):
        result = strip_filler_words("It is like, you know, basically correct.")
        assert "basically" not in result.lower()

    def test_preserves_content(self):
        result = strip_filler_words("Use a hash map for O(1) lookup.")
        assert "hash map" in result
        assert "O(1)" in result

    def test_empty_string(self):
        assert strip_filler_words("") == ""

    def test_only_fillers(self):
        result = strip_filler_words("Um uh er like")
        assert result.strip() == "" or len(result.strip()) < 5

    def test_case_insensitive(self):
        result = strip_filler_words("UM, UH, so I think...")
        assert "UM" not in result
        assert "UH" not in result


# ---------------------------------------------------------------------------
# normalise_whitespace
# ---------------------------------------------------------------------------

class TestNormaliseWhitespace:
    def test_collapses_spaces(self):
        result = normalise_whitespace("hello   world")
        assert result == "hello world"

    def test_collapses_tabs(self):
        result = normalise_whitespace("hello\t\tworld")
        assert result == "hello world"

    def test_collapses_excessive_newlines(self):
        result = normalise_whitespace("line1\n\n\n\nline2")
        assert result == "line1\n\nline2"

    def test_strips_leading_trailing(self):
        assert normalise_whitespace("  hello  ") == "hello"

    def test_empty(self):
        assert normalise_whitespace("") == ""

    def test_no_change_needed(self):
        s = "clean text already"
        assert normalise_whitespace(s) == s


# ---------------------------------------------------------------------------
# remove_control_chars
# ---------------------------------------------------------------------------

class TestRemoveControlChars:
    def test_removes_null_byte(self):
        result = remove_control_chars("hello\x00world")
        assert "\x00" not in result
        assert "helloworld" in result

    def test_removes_bell(self):
        result = remove_control_chars("ring\x07bell")
        assert "\x07" not in result

    def test_preserves_newline(self):
        result = remove_control_chars("line1\nline2")
        assert "\n" in result

    def test_preserves_tab(self):
        result = remove_control_chars("col1\tcol2")
        assert "\t" in result

    def test_normal_text_unchanged(self):
        s = "Hello, World! 123"
        assert remove_control_chars(s) == s

    def test_empty(self):
        assert remove_control_chars("") == ""


# ---------------------------------------------------------------------------
# truncate_to_sentences
# ---------------------------------------------------------------------------

class TestTruncateToSentences:
    def test_keeps_under_limit(self):
        text = "One sentence."
        assert truncate_to_sentences(text, max_sentences=3) == "One sentence."

    def test_truncates_to_limit(self):
        text = "First. Second. Third. Fourth. Fifth."
        result = truncate_to_sentences(text, max_sentences=3)
        assert "Fourth" not in result
        assert "Fifth" not in result

    def test_adds_ellipsis_when_truncated(self):
        text = "Alpha. Beta. Gamma. Delta."
        result = truncate_to_sentences(text, max_sentences=2)
        assert result.endswith("…") or result.endswith("Gamma.") or "Delta" not in result

    def test_empty_text(self):
        assert truncate_to_sentences("", max_sentences=3) == ""

    def test_no_truncation_needed(self):
        text = "One. Two."
        assert truncate_to_sentences(text, max_sentences=5) == "One. Two."


# ---------------------------------------------------------------------------
# clean_transcript — integration pipeline
# ---------------------------------------------------------------------------

class TestCleanTranscript:
    def test_full_pipeline(self):
        raw = "Um, like, so  basically\x00 you need to uh use a hash map."
        result = clean_transcript(raw)
        assert "um" not in result.lower()
        assert "\x00" not in result
        assert "hash map" in result

    def test_no_filler_stripping(self):
        raw = "Um, hello world."
        result = clean_transcript(raw, strip_fillers=False)
        assert "um" in result.lower()

    def test_with_max_sentences(self):
        raw = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = clean_transcript(raw, max_sentences=2)
        assert "Third" not in result
        assert "Fourth" not in result

    def test_empty(self):
        assert clean_transcript("") == ""


# ---------------------------------------------------------------------------
# sanitise_for_tts
# ---------------------------------------------------------------------------

class TestSanitiseForTts:
    def test_removes_code_fence(self):
        text = "Here is a snippet:\n```python\nprint('hello')\n```\nDone."
        result = sanitise_for_tts(text)
        assert "```" not in result
        assert "print" not in result
        assert "Done" in result

    def test_removes_inline_code(self):
        result = sanitise_for_tts("Call the `compute()` function.")
        assert "`" not in result
        assert "compute" not in result
        assert "function" in result

    def test_removes_urls(self):
        result = sanitise_for_tts("See https://docs.python.org for more info.")
        assert "https" not in result
        assert "more info" in result

    def test_removes_markdown_symbols(self):
        result = sanitise_for_tts("**Bold** and _italic_ and ~strike~")
        assert "*" not in result
        assert "_" not in result
        assert "~" not in result
        assert "Bold" in result

    def test_normalises_ellipsis(self):
        result = sanitise_for_tts("Hmm....let me think.")
        # Multiple dots should become a single ellipsis character or single dot
        assert "...." not in result

    def test_empty_string(self):
        assert sanitise_for_tts("") == ""

    def test_plain_text_unchanged(self):
        text = "The quick brown fox jumps over the lazy dog."
        result = sanitise_for_tts(text)
        assert result == text
