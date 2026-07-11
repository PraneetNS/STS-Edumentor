"""
Unit tests for SQLiteBackend — persistent SQLite-based conversation memory.

All tests use a temporary in-memory SQLite database (:memory:) so they run
fast, in parallel, and leave no files on disk.
"""

from __future__ import annotations

import time
import pytest

from agent.memory_manager import SQLiteBackend
from agent.models import MemoryTurn


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path):
    """Return a fresh SQLiteBackend pointing at a temp directory."""
    db_file = str(tmp_path / "test_memory.db")
    return SQLiteBackend(db_path=db_file)


def make_turn(user: str = "hello", assistant: str = "hi", **kwargs) -> MemoryTurn:
    return MemoryTurn(user=user, assistant=assistant, **kwargs)


# ── Basic CRUD ─────────────────────────────────────────────────────────────────

class TestSQLiteBackendCRUD:
    def test_get_empty_session_returns_empty_list(self, db):
        assert db.get("session-x") == []

    def test_append_and_get_single_turn(self, db):
        turn = make_turn("What is recursion?", "Recursion is a function calling itself.")
        db.append("s1", turn)
        result = db.get("s1")
        assert len(result) == 1
        assert result[0].user == "What is recursion?"
        assert result[0].assistant == "Recursion is a function calling itself."

    def test_get_returns_oldest_first(self, db):
        t0 = time.time()
        db.append("s1", make_turn("first", "a", timestamp=t0))
        db.append("s1", make_turn("second", "b", timestamp=t0 + 1))
        db.append("s1", make_turn("third", "c", timestamp=t0 + 2))
        turns = db.get("s1")
        assert [t.user for t in turns] == ["first", "second", "third"]

    def test_append_preserves_metadata(self, db):
        turn = make_turn(intent="CONCEPT_EXPLANATION", emotion="curious")
        db.append("s1", turn)
        result = db.get("s1")[0]
        assert result.intent == "CONCEPT_EXPLANATION"
        assert result.emotion == "curious"

    def test_append_none_metadata_fields(self, db):
        turn = make_turn(intent=None, emotion=None)
        db.append("s1", turn)
        result = db.get("s1")[0]
        assert result.intent is None
        assert result.emotion is None

    def test_clear_removes_only_target_session(self, db):
        db.append("s1", make_turn())
        db.append("s2", make_turn())
        db.clear("s1")
        assert db.get("s1") == []
        assert len(db.get("s2")) == 1

    def test_clear_empty_session_is_noop(self, db):
        db.clear("nonexistent")  # should not raise
        assert db.get("nonexistent") == []


# ── Count ─────────────────────────────────────────────────────────────────────

class TestSQLiteBackendCount:
    def test_count_zero_for_new_session(self, db):
        assert db.count("s-new") == 0

    def test_count_increments_per_append(self, db):
        for i in range(5):
            db.append("s1", make_turn(f"q{i}", f"a{i}"))
        assert db.count("s1") == 5

    def test_count_reflects_remaining_after_prune(self, db):
        for i in range(8):
            db.append("s1", make_turn(f"q{i}", f"a{i}"))
        db.prune("s1", max_turns=3)
        assert db.count("s1") == 3

    def test_count_zero_after_clear(self, db):
        db.append("s1", make_turn())
        db.clear("s1")
        assert db.count("s1") == 0


# ── Prune ─────────────────────────────────────────────────────────────────────

class TestSQLiteBackendPrune:
    def test_prune_keeps_most_recent_turns(self, db):
        t0 = time.time()
        for i in range(6):
            db.append("s1", make_turn(f"q{i}", f"a{i}", timestamp=t0 + i))
        db.prune("s1", max_turns=3)
        turns = db.get("s1")
        assert len(turns) == 3
        assert turns[0].user == "q3"
        assert turns[-1].user == "q5"

    def test_prune_with_max_turns_larger_than_existing_is_noop(self, db):
        for i in range(3):
            db.append("s1", make_turn(f"q{i}", f"a{i}"))
        db.prune("s1", max_turns=10)
        assert len(db.get("s1")) == 3

    def test_prune_to_zero_empties_session(self, db):
        for i in range(5):
            db.append("s1", make_turn())
        db.prune("s1", max_turns=0)
        assert db.get("s1") == []


# ── Session Isolation ─────────────────────────────────────────────────────────

class TestSQLiteBackendIsolation:
    def test_sessions_are_isolated(self, db):
        db.append("alice", make_turn("Alice question", "Alice answer"))
        db.append("bob", make_turn("Bob question", "Bob answer"))
        assert len(db.get("alice")) == 1
        assert db.get("alice")[0].user == "Alice question"
        assert len(db.get("bob")) == 1
        assert db.get("bob")[0].user == "Bob question"

    def test_prune_does_not_affect_other_sessions(self, db):
        t0 = time.time()
        for i in range(5):
            db.append("s1", make_turn(timestamp=t0 + i))
        db.append("s2", make_turn("keeper", "stays"))
        db.prune("s1", max_turns=2)
        assert len(db.get("s2")) == 1
        assert db.get("s2")[0].user == "keeper"

    def test_clear_does_not_affect_other_sessions(self, db):
        db.append("s1", make_turn())
        db.append("s2", make_turn("safe", "kept"))
        db.clear("s1")
        assert db.get("s2")[0].user == "safe"


# ── Persistence simulation ────────────────────────────────────────────────────

class TestSQLiteBackendPersistence:
    def test_data_persists_across_backend_instances(self, tmp_path):
        """Creating a second SQLiteBackend on same file should see existing data."""
        db_file = str(tmp_path / "persist.db")
        backend1 = SQLiteBackend(db_path=db_file)
        backend1.append("s1", make_turn("persisted question", "persisted answer"))

        backend2 = SQLiteBackend(db_path=db_file)
        turns = backend2.get("s1")
        assert len(turns) == 1
        assert turns[0].user == "persisted question"
