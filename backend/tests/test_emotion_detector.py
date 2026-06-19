"""
Tests — Emotion Detector

Covers all 6 emotion categories and neutral fallback.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agent.emotion_detector import detect, get_style_for_emotion
from agent.models import Emotion, EmotionResult


# ─────────────────────────────────────────────────────────────────────────────
# Frustration detection
# ─────────────────────────────────────────────────────────────────────────────

def test_frustrated_phrase_1():
    result = detect("I still don't understand this")
    assert result.emotion == Emotion.FRUSTRATED

def test_frustrated_phrase_2():
    result = detect("This makes no sense to me at all")
    assert result.emotion == Emotion.FRUSTRATED

def test_frustrated_gives_up():
    result = detect("I give up, this is impossible")
    assert result.emotion == Emotion.FRUSTRATED


# ─────────────────────────────────────────────────────────────────────────────
# Confusion detection
# ─────────────────────────────────────────────────────────────────────────────

def test_confused_direct():
    result = detect("I am confused about recursion")
    assert result.emotion == Emotion.CONFUSED

def test_confused_lost():
    result = detect("I'm lost, what does that mean?")
    assert result.emotion == Emotion.CONFUSED

def test_confused_clarify():
    result = detect("Could you clarify that last part?")
    assert result.emotion == Emotion.CONFUSED


# ─────────────────────────────────────────────────────────────────────────────
# Confidence detection
# ─────────────────────────────────────────────────────────────────────────────

def test_confident_got_it():
    result = detect("Got it! That makes total sense now.")
    assert result.emotion == Emotion.CONFIDENT

def test_confident_understand_now():
    result = detect("Oh I understand now, thank you!")
    assert result.emotion == Emotion.CONFIDENT


# ─────────────────────────────────────────────────────────────────────────────
# Happy detection
# ─────────────────────────────────────────────────────────────────────────────

def test_happy_thank_you():
    result = detect("Thank you, that was really helpful!")
    assert result.emotion == Emotion.HAPPY

def test_happy_awesome():
    result = detect("Awesome explanation!")
    assert result.emotion == Emotion.HAPPY


# ─────────────────────────────────────────────────────────────────────────────
# Boredom detection
# ─────────────────────────────────────────────────────────────────────────────

def test_bored_skip():
    result = detect("Can we skip this and do something more interesting?")
    assert result.emotion == Emotion.BORED

def test_bored_move_on():
    result = detect("Let's move on to the next topic")
    assert result.emotion == Emotion.BORED


# ─────────────────────────────────────────────────────────────────────────────
# Neutral fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_neutral_for_factual_question():
    result = detect("What is recursion?")
    assert result.emotion == Emotion.NEUTRAL

def test_neutral_for_empty_string():
    result = detect("")
    assert result.emotion == Emotion.NEUTRAL

def test_neutral_for_code_question():
    result = detect("How do I write a for loop in Python?")
    assert result.emotion == Emotion.NEUTRAL


# ─────────────────────────────────────────────────────────────────────────────
# Confidence values
# ─────────────────────────────────────────────────────────────────────────────

def test_confidence_in_range():
    result = detect("I still don't understand this at all")
    assert 0.0 <= result.confidence <= 1.0

def test_trigger_phrase_is_set():
    result = detect("This makes no sense")
    assert result.trigger_phrase != ""


# ─────────────────────────────────────────────────────────────────────────────
# Style map
# ─────────────────────────────────────────────────────────────────────────────

def test_style_map_frustrated_has_bridge():
    style = get_style_for_emotion(Emotion.FRUSTRATED)
    assert style["bridge_phrase"] is not None
    assert style["simplify"] is True

def test_style_map_confident_advances():
    style = get_style_for_emotion(Emotion.CONFIDENT)
    assert style["advance_topic"] is True

def test_style_map_neutral_has_no_instructions():
    style = get_style_for_emotion(Emotion.NEUTRAL)
    assert style["instructions"] is None

def test_style_map_bored_changes_format():
    style = get_style_for_emotion(Emotion.BORED)
    assert style["change_format"] == "quiz"
