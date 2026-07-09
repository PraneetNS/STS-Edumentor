"""
backend/tests/test_positive_signal_detector.py

Run with: pytest backend/tests/test_positive_signal_detector.py -v

The single most important property here: a wrong answer must NEVER be
classified as a celebration, no matter how enthusiastic the text or audio
signal looks. Everything else is secondary to that gate holding.
"""

import pytest

from agent.positive_signal_detector import (
    PositiveSignalDetector,
    PositiveSignalConfig,
    PositiveEmotion,
)


@pytest.fixture
def detector():
    return PositiveSignalDetector(PositiveSignalConfig(enabled=True, min_intensity_to_celebrate=0.4))


# --- Disabled is a true no-op -----------------------------------------------

def test_disabled_returns_none_regardless_of_signal():
    d = PositiveSignalDetector(PositiveSignalConfig(enabled=False))
    result = d.detect("yes! got it! definitely!", answer_was_correct=True)
    assert result.emotion == PositiveEmotion.NONE
    assert result.reason == "disabled"


# --- The hard gate: wrong answer is NEVER a celebration ---------------------

@pytest.mark.parametrize("text", [
    "yes! I got it! that makes sense now!",
    "definitely, I'm sure, obviously!!!",
    "finally understand this, aha!",
])
def test_wrong_answer_never_celebrates_regardless_of_enthusiastic_text(detector, text):
    result = detector.detect(
        text,
        answer_was_correct=False,
        previously_weak_topic=True,
        audio_energy_delta=0.9,
    )
    assert result.emotion == PositiveEmotion.NONE
    assert result.reason == "answer_incorrect"


def test_wrong_answer_gate_short_circuits_before_any_scoring(detector):
    # Even maximal positive signal everywhere else must not leak through.
    result = detector.detect(
        "yes! definitely! finally! got it!",
        answer_was_correct=False,
        previously_weak_topic=True,
        audio_energy_delta=1.0,
    )
    assert result.intensity == 0.0


# --- Correct answers can celebrate, scaled by supporting signal -------------

def test_correct_plain_answer_is_mild_confident(detector):
    result = detector.detect("that is correct", answer_was_correct=True)
    assert result.emotion == PositiveEmotion.CONFIDENT
    assert 0.4 <= result.intensity < 0.7


def test_correct_plus_excited_language_is_excited(detector):
    result = detector.detect("yes I got it!", answer_was_correct=True)
    assert result.emotion == PositiveEmotion.EXCITED


def test_correct_on_previously_weak_topic_is_proud(detector):
    result = detector.detect(
        "that is correct", answer_was_correct=True, previously_weak_topic=True
    )
    assert result.emotion == PositiveEmotion.PROUD


# --- Audio energy is an amplifier only, never a standalone trigger ----------

def test_audio_energy_alone_without_any_text_or_context_does_not_trigger(detector):
    result = detector.detect("", answer_was_correct=None, audio_energy_delta=0.9)
    assert result.emotion == PositiveEmotion.NONE


def test_audio_energy_amplifies_an_existing_signal(detector):
    without_audio = detector.detect("that's correct", answer_was_correct=True)
    with_audio = detector.detect(
        "that's correct", answer_was_correct=True, audio_energy_delta=0.5
    )
    assert with_audio.intensity >= without_audio.intensity


# --- Threshold gating --------------------------------------------------------

def test_weak_signal_stays_below_threshold(detector):
    # Not correct (None = not applicable), no strong language, no audio --
    # should not clear the 0.4 celebration threshold.
    result = detector.detect("okay", answer_was_correct=None)
    assert result.emotion == PositiveEmotion.NONE
    assert "below_threshold" in result.reason


def test_intensity_is_capped_at_one(detector):
    result = detector.detect(
        "yes! I got it! definitely! finally understand!",
        answer_was_correct=True,
        previously_weak_topic=True,
        audio_energy_delta=0.9,
    )
    assert result.intensity <= 1.0
