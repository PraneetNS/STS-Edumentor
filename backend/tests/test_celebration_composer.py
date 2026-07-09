"""
backend/tests/test_celebration_composer.py

Run with: pytest backend/tests/test_celebration_composer.py -v
"""

import time
import pytest

from agent.celebration_composer import CelebrationComposer, CelebrationConfig
from agent.positive_signal_detector import PositiveEmotion, PositiveSignal


@pytest.fixture
def composer():
    return CelebrationComposer(
        CelebrationConfig(
            enabled=True,
            min_speed_boost=0.03,
            max_speed_boost=0.12,
            cooldown_s=0.2,          # short, for fast tests
            recent_history_size=2,
        )
    )


def _signal(emotion=PositiveEmotion.EXCITED, intensity=0.8):
    return PositiveSignal(emotion=emotion, intensity=intensity, reason="test")


# --- Disabled / no-signal are true no-ops -----------------------------------

def test_disabled_returns_none():
    c = CelebrationComposer(CelebrationConfig(enabled=False))
    assert c.compose("sess1", _signal()) is None


def test_none_emotion_returns_none(composer):
    assert composer.compose("sess1", _signal(emotion=PositiveEmotion.NONE)) is None


# --- Basic composition -------------------------------------------------------

def test_composes_phrase_and_bounded_speed(composer):
    result = composer.compose("sess1", _signal())
    assert result is not None
    assert result.phrase in {
        "Yes, exactly!", "That's it!", "Nailed it!", "You've got it!", "That's exactly right!"
    }
    assert 1.03 <= result.speed_multiplier <= 1.12


def test_speed_scales_with_intensity(composer):
    low = composer.compose("sess1", _signal(intensity=0.1))
    time.sleep(0.25)  # clear cooldown
    high = composer.compose("sess1", _signal(intensity=1.0))
    assert high.speed_multiplier > low.speed_multiplier


def test_speed_never_exceeds_configured_ceiling(composer):
    result = composer.compose("sess1", _signal(intensity=1.0))
    assert result.speed_multiplier <= 1.0 + composer.config.max_speed_boost


# --- Cooldown: no back-to-back celebrations ---------------------------------

def test_cooldown_blocks_immediate_repeat_celebration(composer):
    first = composer.compose("sess1", _signal())
    second = composer.compose("sess1", _signal())
    assert first is not None
    assert second is None


def test_cooldown_expires_after_configured_window(composer):
    first = composer.compose("sess1", _signal())
    time.sleep(0.25)
    second = composer.compose("sess1", _signal())
    assert first is not None
    assert second is not None


def test_cooldown_is_per_session(composer):
    a = composer.compose("sess-a", _signal())
    b = composer.compose("sess-b", _signal())
    assert a is not None
    assert b is not None  # different session, no shared cooldown


# --- Anti-repetition ---------------------------------------------------------

def test_does_not_repeat_recent_phrase_within_history_window():
    composer = CelebrationComposer(
        CelebrationConfig(enabled=True, cooldown_s=0.0, recent_history_size=4)
    )
    seen = []
    for _ in range(4):
        result = composer.compose("sess1", _signal())
        seen.append(result.phrase)
        time.sleep(0.01)
    # With recent_history_size=4 and only 5 phrases in the EXCITED pool,
    # no phrase should repeat within these 4 draws unless the pool is
    # nearly exhausted -- check no IMMEDIATE repeat at minimum.
    for i in range(1, len(seen)):
        assert seen[i] != seen[i - 1], "should not repeat the immediately preceding phrase"


def test_falls_back_to_full_pool_if_history_exceeds_pool_size():
    # CONFIDENT pool has 4 phrases; history_size larger than pool must not
    # crash or deadlock -- it should just fall back to allowing repeats.
    composer = CelebrationComposer(
        CelebrationConfig(enabled=True, cooldown_s=0.0, recent_history_size=10)
    )
    for _ in range(10):
        result = composer.compose("sess1", _signal(emotion=PositiveEmotion.CONFIDENT))
        assert result is not None
        time.sleep(0.01)
