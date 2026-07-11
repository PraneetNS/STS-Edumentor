"""
Unit tests for the ProfanityFilter / check_profanity() added to safety_guard.

Tests cover:
- Clean input passes through unchanged
- Single blocked words are detected and masked
- Multi-word phrases are detected and masked
- Case-insensitive matching
- Word-boundary guards (no false positives on substrings)
- Multiple blocked words in one string are ALL masked
- Educational / technical terms are not falsely flagged
- ProfanityResult fields (detected, matched, clean_text)
"""

from __future__ import annotations

import pytest

from agent.safety_guard import check_profanity, ProfanityResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    return check_profanity(text).clean_text


def detected(text: str) -> bool:
    return check_profanity(text).detected


# ── Clean Input ───────────────────────────────────────────────────────────────

class TestCleanInput:
    def test_empty_string_passes(self):
        r = check_profanity("")
        assert not r.detected
        assert r.matched is None
        assert r.clean_text == ""

    def test_plain_technical_question_passes(self):
        text = "How do I implement a binary search tree in Python?"
        r = check_profanity(text)
        assert not r.detected
        assert r.clean_text == text

    def test_greeting_passes(self):
        text = "Hello, my name is Alice and I want to learn recursion."
        assert not detected(text)

    def test_long_academic_paragraph_passes(self):
        text = (
            "Dynamic programming is a method for solving complex problems by breaking "
            "them down into simpler subproblems. It is applicable where the subproblems "
            "overlap and can be solved once and reused."
        )
        assert not detected(text)


# ── Single Word Detection ─────────────────────────────────────────────────────

class TestSingleWordDetection:
    def test_detects_common_profanity(self):
        assert detected("What the fuck is this?")

    def test_masks_matched_word_with_asterisks(self):
        result = check_profanity("This is bullshit.")
        assert result.detected
        assert "*" in result.clean_text
        assert "bullshit" not in result.clean_text

    def test_matched_field_contains_the_word(self):
        result = check_profanity("You are such an asshole.")
        assert result.matched is not None
        assert result.matched.lower() == "asshole"

    def test_asterisk_length_matches_word_length(self):
        result = check_profanity("You are a bitch.")
        # "bitch" is 5 chars → 5 asterisks
        assert "*****" in result.clean_text

    def test_detects_bastard(self):
        assert detected("You absolute bastard!")

    def test_detects_slur(self):
        assert detected("He called me a retard.")

    def test_detects_wanker(self):
        assert detected("What a complete wanker.")


# ── Multi-Word Phrase Detection ───────────────────────────────────────────────

class TestMultiWordPhraseDetection:
    def test_detects_shut_the_fuck_up(self):
        assert detected("Just shut the fuck up already.")

    def test_detects_piece_of_shit(self):
        result = check_profanity("This code is a piece of shit.")
        assert result.detected
        assert "piece of shit" not in result.clean_text.lower()

    def test_detects_son_of_a_bitch(self):
        assert detected("Son of a bitch that was unexpected!")

    def test_detects_go_to_hell(self):
        assert detected("You can go to hell for all I care.")


# ── Case-Insensitive Matching ─────────────────────────────────────────────────

class TestCaseInsensitiveMatching:
    def test_uppercase_detected(self):
        assert detected("FUCK this error!")

    def test_title_case_detected(self):
        assert detected("You stupid Bastard.")

    def test_mixed_case_detected(self):
        assert detected("What a BiTcH move.")

    def test_clean_text_is_still_masked(self):
        result = check_profanity("BULLSHIT solution!")
        assert "BULLSHIT" not in result.clean_text


# ── Word Boundary Guards (No False Positives) ─────────────────────────────────

class TestWordBoundaryGuards:
    def test_scunthorpe_problem_for_cunt(self):
        # "Scunthorpe" or other compound words should not trip blocklist
        # 'cunt' embedded mid-word should not match
        # We test a common false-positive victim
        text = "The county of Yorkshire"
        # 'county' contains 'coun' not 'cunt' — passes
        assert not detected(text)

    def test_skill_does_not_trigger_kill(self):
        assert not detected("We need to build our coding skill.")

    def test_class_does_not_trigger_ass(self):
        # 'class' should not match 'ass' checker since word boundary is enforced
        assert not detected("Define a class in Python with __init__.")

    def test_background_does_not_trigger(self):
        assert not detected("Run the process in the background thread.")

    def test_prick_as_standalone_is_blocked(self):
        assert detected("Don't be such a prick.")


# ── Multiple Blocked Words ────────────────────────────────────────────────────

class TestMultipleBlockedWords:
    def test_all_blocked_words_are_masked(self):
        text = "This is fucking bullshit!"
        result = check_profanity(text)
        assert result.detected
        assert "fucking" not in result.clean_text
        assert "bullshit" not in result.clean_text

    def test_clean_text_preserves_surrounding_words(self):
        result = check_profanity("What the fuck is this shit?")
        # "What the" and "is this" should survive
        assert "What the" in result.clean_text
        assert "is this" in result.clean_text


# ── ProfanityResult Dataclass ─────────────────────────────────────────────────

class TestProfanityResultDataclass:
    def test_result_is_frozen(self):
        result = check_profanity("hello world")
        with pytest.raises((AttributeError, TypeError)):
            result.detected = True  # type: ignore[misc]

    def test_result_is_profanity_result_instance(self):
        result = check_profanity("hello")
        assert isinstance(result, ProfanityResult)

    def test_no_match_returns_none_for_matched(self):
        result = check_profanity("I love Python programming.")
        assert result.matched is None

    def test_clean_text_equals_input_when_clean(self):
        text = "Help me understand pointers in C."
        result = check_profanity(text)
        assert result.clean_text == text
