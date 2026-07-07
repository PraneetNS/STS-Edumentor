"""
backend/tests/test_endpointing.py

Run with: pytest backend/tests/test_endpointing.py -v

These tests exist specifically to prove the safety properties before this
touches the live pipeline:
  - FIXED mode reproduces the exact legacy fixed-timeout behavior.
  - ADAPTIVE never fires faster than min_silence_ms.
  - ADAPTIVE never waits longer than max_silence_ms (the ceiling holds
    even for trailing-incomplete text).
  - Confident-complete utterances fire before the old default timeout.
  - Trailing conjunctions/fillers extend the wait instead of cutting the
    user off.
"""

import pytest

from speech.endpointing import (
    SemanticEndpointer,
    EndpointingConfig,
    EndpointingMode,
    Completeness,
)


@pytest.fixture
def cfg():
    return EndpointingConfig(
        mode=EndpointingMode.ADAPTIVE,
        min_silence_ms=250,
        default_silence_ms=800,
        max_silence_ms=1200,
        check_interval_ms=100,
        min_words_for_fast_fire=2,
    )


@pytest.fixture
def endpointer(cfg):
    return SemanticEndpointer(cfg)


# --- FIXED mode: must exactly reproduce legacy behavior -------------------

def test_fixed_mode_never_fires_before_default_timeout():
    """Verify that under FIXED mode, endpointing never triggers if the silence is less than the default timeout."""
    fixed_cfg = EndpointingConfig(mode=EndpointingMode.FIXED, default_silence_ms=800)
    ep = SemanticEndpointer(fixed_cfg)
    decision = ep.decide("what's a pointer?", silence_elapsed_ms=799)
    assert decision.should_finalize is False


def test_fixed_mode_fires_exactly_at_default_timeout():
    """Verify that under FIXED mode, endpointing triggers exactly at the default silence timeout."""
    fixed_cfg = EndpointingConfig(mode=EndpointingMode.FIXED, default_silence_ms=800)
    ep = SemanticEndpointer(fixed_cfg)
    decision = ep.decide("what's a pointer?", silence_elapsed_ms=800)
    assert decision.should_finalize is True
    assert decision.reason == "fixed_mode"


# --- Completeness classification ------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("what's a pointer?", Completeness.CONFIDENT_COMPLETE),
    ("explain recursion to me.", Completeness.CONFIDENT_COMPLETE),
    ("how does a hash map work", Completeness.CONFIDENT_COMPLETE),  # no punct, question starter
    ("so basically the loop runs and", Completeness.TRAILING_INCOMPLETE),
    ("i was thinking that we could use a", Completeness.TRAILING_INCOMPLETE),
    ("um", Completeness.TRAILING_INCOMPLETE),  # filler word -> extend wait, don't fast-fire
    ("okay so", Completeness.TRAILING_INCOMPLETE),
    ("", Completeness.AMBIGUOUS),
])
def test_classify_completeness(endpointer, text, expected):
    assert endpointer.classify_completeness(text) == expected


# --- Fast-fire on confident-complete ---------------------------------------

def test_confident_complete_fires_before_default_timeout(endpointer):
    decision = endpointer.decide("what's a pointer?", silence_elapsed_ms=300)
    assert decision.should_finalize is True
    assert decision.reason == "confident_complete_fast_fire"
    assert decision.effective_wait_ms == 250


def test_confident_complete_does_not_fire_before_min_silence(endpointer):
    decision = endpointer.decide("what's a pointer?", silence_elapsed_ms=100)
    assert decision.should_finalize is False


# --- Trailing incomplete extends, but ceiling still protects ---------------

def test_trailing_incomplete_does_not_fire_at_default_timeout(endpointer):
    decision = endpointer.decide("so basically the loop runs and", silence_elapsed_ms=800)
    assert decision.should_finalize is False
    assert decision.reason == "trailing_incomplete_extend"


def test_ceiling_always_fires_even_on_trailing_incomplete(endpointer):
    decision = endpointer.decide("so basically the loop runs and", silence_elapsed_ms=1200)
    assert decision.should_finalize is True
    assert decision.reason == "max_silence_ceiling"


def test_ceiling_never_exceeded_regardless_of_signal(endpointer, cfg):
    for text in ["", "and", "what's a pointer?", "so basically and"]:
        decision = endpointer.decide(text, silence_elapsed_ms=cfg.max_silence_ms)
        assert decision.should_finalize is True


# --- Ambiguous falls back to legacy default timeout ------------------------

def test_ambiguous_behaves_like_legacy_default(endpointer):
    decision = endpointer.decide("hmm okay", silence_elapsed_ms=799)
    assert decision.should_finalize is False
    decision2 = endpointer.decide("hmm okay", silence_elapsed_ms=800)
    assert decision2.should_finalize is True
    assert decision2.reason == "ambiguous_default_timeout"


# --- Guardrail: min_words_for_fast_fire prevents noise/blip false triggers -

def test_short_confirmed_text_does_not_fast_fire(endpointer):
    # Single word with terminal punctuation shouldn't fast-fire -- could be
    # a stray ASR blip on background noise.
    decision = endpointer.decide("what?", silence_elapsed_ms=300)
    assert decision.reason != "confident_complete_fast_fire"
