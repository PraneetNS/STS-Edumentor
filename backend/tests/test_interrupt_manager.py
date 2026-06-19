"""
Tests — Interrupt Manager

Tests state save/restore/clear lifecycle and bridge instruction generation.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import pytest
from agent.interrupt_manager import InterruptManager
from agent.models import InterruptState


@pytest.fixture
def manager():
    return InterruptManager()


def test_initial_state_is_empty(manager):
    assert not manager.was_interrupted("session-1")
    assert manager.get_state("session-1") is None


def test_save_and_retrieve_state(manager):
    manager.save_state(
        session_id="session-1",
        partial_response="Recursion is when a function calls itself",
        topic="recursion",
        total_response_chars=100,
    )
    assert manager.was_interrupted("session-1")
    state = manager.get_state("session-1")
    assert state is not None
    assert state.topic == "recursion"
    assert "Recursion" in state.interrupted_response
    assert state.was_mid_explanation is True


def test_save_short_response_not_mid_explanation(manager):
    manager.save_state("session-2", partial_response="Hi", topic="greeting")
    state = manager.get_state("session-2")
    assert state.was_mid_explanation is False


def test_clear_state(manager):
    manager.save_state("session-3", "Some partial text", "topic", 200)
    assert manager.was_interrupted("session-3")
    manager.clear_state("session-3")
    assert not manager.was_interrupted("session-3")


def test_build_bridge_instruction_with_explanation(manager):
    manager.save_state("session-4", "Recursion is the process of calling...", "recursion", 200)
    bridge = manager.build_bridge_instruction("session-4", "Wait, what is a base case?")
    assert bridge is not None
    assert "recursion" in bridge.lower()
    assert "base case" in bridge.lower() or "interrupted" in bridge.lower()


def test_build_bridge_clears_state(manager):
    manager.save_state("session-5", "Explaining binary search...", "binary search", 300)
    manager.build_bridge_instruction("session-5", "New question")
    # State should be cleared after bridge is built
    assert not manager.was_interrupted("session-5")


def test_build_bridge_returns_none_when_no_state(manager):
    result = manager.build_bridge_instruction("no-session", "some question")
    assert result is None


def test_chars_tracking(manager):
    manager.reset_turn("session-6")
    manager.track_chars_sent("session-6", 50)
    manager.track_chars_sent("session-6", 100)
    # After 150 chars sent, total 300 chars, fraction = 0.5
    manager.save_state("session-6", "x" * 50, "topic", total_response_chars=300)
    state = manager.get_state("session-6")
    assert state.interrupted_at_fraction > 0.0


def test_session_isolation(manager):
    manager.save_state("session-A", "text A", "topic A", 100)
    assert not manager.was_interrupted("session-B")
    assert manager.was_interrupted("session-A")


def test_clear_session_removes_all_data(manager):
    manager.save_state("session-7", "text", "topic", 100)
    manager.track_chars_sent("session-7", 50)
    manager.clear_session("session-7")
    assert not manager.was_interrupted("session-7")


def test_timestamp_is_recent(manager):
    manager.save_state("session-8", "text", "topic")
    state = manager.get_state("session-8")
    assert abs(state.timestamp - time.time()) < 2.0  # Within 2 seconds


def test_long_response_is_truncated(manager):
    long_response = "x" * 1000
    manager.save_state("session-9", long_response, "topic", 1000)
    state = manager.get_state("session-9")
    # Should be capped at 500 chars
    assert len(state.interrupted_response) <= 500
