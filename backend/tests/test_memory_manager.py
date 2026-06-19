"""
Tests — Memory Manager

Tests session CRUD, pruning, total count, and summarizer trigger interface.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agent.memory_manager import MemoryManager, InMemoryBackend
from agent.models import MemoryTurn


@pytest.fixture
def manager():
    return MemoryManager(max_turns=5)


def test_empty_session(manager):
    turns = manager.get_session("s1")
    assert turns == []


def test_add_and_retrieve_turn(manager):
    manager.add_turn("s1", "Hello", "Hi there!", intent="GREETING")
    turns = manager.get_session("s1")
    assert len(turns) == 1
    assert turns[0].user == "Hello"
    assert turns[0].assistant == "Hi there!"
    assert turns[0].intent == "GREETING"


def test_pruning_at_max_turns(manager):
    for i in range(10):
        manager.add_turn("s1", f"User {i}", f"Assistant {i}")
    turns = manager.get_session("s1")
    # Should only keep last 5
    assert len(turns) == 5
    # Most recent turn should be the 10th
    assert turns[-1].user == "User 9"


def test_get_relevant_history_returns_chronological(manager):
    for i in range(3):
        manager.add_turn("s2", f"Q{i}", f"A{i}")
    history = manager.get_relevant_history("s2", max_turns=3)
    assert history[0].user == "Q0"
    assert history[-1].user == "Q2"


def test_get_relevant_history_respects_max_turns(manager):
    for i in range(5):
        manager.add_turn("s3", f"Q{i}", f"A{i}")
    history = manager.get_relevant_history("s3", max_turns=2)
    assert len(history) == 2
    # Should be the 2 most recent, in chronological order
    assert history[-1].user == "Q4"


def test_clear_session(manager):
    manager.add_turn("s4", "test", "response")
    manager.clear_session("s4")
    assert manager.get_session("s4") == []


def test_session_isolation(manager):
    manager.add_turn("s5", "Hello from 5", "Response 5")
    manager.add_turn("s6", "Hello from 6", "Response 6")
    assert len(manager.get_session("s5")) == 1
    assert len(manager.get_session("s6")) == 1
    manager.clear_session("s5")
    assert len(manager.get_session("s5")) == 0
    assert len(manager.get_session("s6")) == 1


def test_turn_count_accumulates(manager):
    for i in range(12):
        manager.add_turn("s7", f"Q{i}", f"A{i}")
    # Total count should be 12 even though window is 5
    count = manager.get_turn_count("s7")
    assert count == 12


def test_turn_metadata_stored(manager):
    manager.add_turn("s8", "confused", "let me explain", intent="SIMPLIFY", emotion="confused")
    turns = manager.get_session("s8")
    assert turns[0].intent == "SIMPLIFY"
    assert turns[0].emotion == "confused"


def test_in_memory_backend_directly():
    backend = InMemoryBackend()
    turn = MemoryTurn(user="test", assistant="response")
    backend.append("sid", turn)
    assert backend.count("sid") == 1
    backend.prune("sid", max_turns=1)
    assert len(backend.get("sid")) == 1
    backend.clear("sid")
    assert backend.get("sid") == []
