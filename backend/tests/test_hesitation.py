"""
backend/tests/test_hesitation.py

Tests for hesitation detection and composer subsystems.
"""

from __future__ import annotations

import time
import pytest
from agent.hesitation_detector import HesitationDetector, HesitationSignal
from agent.hesitation_composer import HesitationComposer, HesitationConfig


# ─────────────────────────────────────────────────────────────────────────────
# Hesitation Detector Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_hesitation_detector_hard_gate():
    detector = HesitationDetector()

    # Pure filler cases
    assert detector.detect("hmm").detected is True
    assert detector.detect("uhhh...").detected is True
    assert detector.detect("umm umm").detected is True
    assert detector.detect("hmmmm").detected is True
    assert detector.detect("err").detected is True
    assert detector.detect("mhm").detected is True
    assert detector.detect("ah... eh").detected is True
    assert detector.detect("uhh, err, umm").detected is True

    # Substantive content cases (must NEVER trigger)
    assert detector.detect("umm what's a linked list").detected is False
    assert detector.detect("explain recursion, hmm").detected is False
    assert detector.detect("uh, i don't know").detected is False
    assert detector.detect("hello").detected is False
    assert detector.detect("").detected is False


def test_hesitation_detector_audio_amplifier():
    detector = HesitationDetector()

    # 1. High energy signal alone (substantive text) does NOT trigger detection
    sig_substantive = detector.detect("what is recursion", audio_energy_signal=0.5)
    assert sig_substantive.detected is False

    # 2. Text gate passes -> audio energy amplifies confidence
    sig_no_audio = detector.detect("hmm", audio_energy_signal=None)
    sig_low_audio = detector.detect("hmm", audio_energy_signal=0.05)
    sig_high_audio = detector.detect("hmm", audio_energy_signal=0.25)

    assert sig_no_audio.detected is True
    assert sig_low_audio.detected is True
    assert sig_high_audio.detected is True

    # Energy signal > 0.15 boosts confidence
    assert sig_low_audio.confidence == sig_no_audio.confidence
    assert sig_high_audio.confidence > sig_no_audio.confidence
    assert "elevated_audio_energy" in sig_high_audio.reason


# ─────────────────────────────────────────────────────────────────────────────
# Hesitation Composer Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_hesitation_composer_fallback():
    config = HesitationConfig(enabled=True, cooldown_s=0.0)
    composer = HesitationComposer(config)
    signal = HesitationSignal(detected=True, confidence=0.7, reason="pure_filler_text")

    # 1. Topic is None -> fallback to generic offer
    phrase1 = composer.compose("session_1", signal, current_topic=None)
    assert phrase1 in composer.generic_phrases

    # 2. Topic is "general" -> fallback to generic offer
    phrase2 = composer.compose("session_1", signal, current_topic="general")
    assert phrase2 in composer.generic_phrases

    # 3. Topic is not in TOPIC_SUBTOPICS -> fallback to generic offer
    phrase3 = composer.compose("session_1", signal, current_topic="unknown_topic_abc")
    assert phrase3 in composer.generic_phrases


def test_hesitation_composer_topic_specific():
    config = HesitationConfig(enabled=True, cooldown_s=0.0)
    composer = HesitationComposer(config)
    signal = HesitationSignal(detected=True, confidence=0.7, reason="pure_filler_text")

    # Topic is "recursion"
    phrase = composer.compose("session_2", signal, current_topic="recursion")
    assert phrase is not None

    # Verify that the generated offer targets subtopics of recursion
    # Subtopics are: "the base case", "the stack frames", "how the calls unwind"
    subtopics = composer.topic_subtopics["recursion"]
    matches = [sub for sub in subtopics if sub in phrase]
    
    # Must choose exactly 2 distinct subtopics
    assert len(matches) == 2


def test_hesitation_composer_cooldown():
    config = HesitationConfig(enabled=True, cooldown_s=2.0)
    composer = HesitationComposer(config)
    signal = HesitationSignal(detected=True, confidence=0.7, reason="pure_filler_text")

    # First turn compose
    phrase1 = composer.compose("session_3", signal, current_topic=None)
    assert phrase1 is not None

    # Immediate second turn compose -> blocked by cooldown
    phrase2 = composer.compose("session_3", signal, current_topic=None)
    assert phrase2 is None


def test_hesitation_composer_anti_repetition():
    config = HesitationConfig(enabled=True, cooldown_s=0.0, recent_history_size=3)
    composer = HesitationComposer(config)
    signal = HesitationSignal(detected=True, confidence=0.7, reason="pure_filler_text")

    phrases = []
    for _ in range(4):
        p = composer.compose("session_4", signal, current_topic=None)
        phrases.append(p)

    # Within the recent_history_size window, we should not see duplicates of generic phrases
    # First 4 phrases can have repeats only if pool is exhausted, but pool has size 4
    # and history size is 3, so consecutive calls shouldn't repeat immediate history.
    assert phrases[0] != phrases[1]
    assert phrases[1] != phrases[2]
    assert phrases[2] != phrases[3]
