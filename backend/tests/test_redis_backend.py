"""
Unit tests for RedisBackend — Redis-backed conversation memory.

All tests use unittest.mock to patch redis.Redis so no live Redis server
is required.  The mock captures RPUSH, LRANGE, LTRIM, INCR, GET, DELETE,
and PING calls, verifying the correct Redis API is used.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch, call

import pytest

from agent.models import MemoryTurn


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_turn(user: str = "hello", assistant: str = "hi", **kwargs) -> MemoryTurn:
    return MemoryTurn(user=user, assistant=assistant, **kwargs)


def _serialise(turn: MemoryTurn) -> str:
    return json.dumps(turn.to_dict())


def _mem_key(session_id: str) -> str:
    return f"edumentor:memory:{session_id}"


def _count_key(session_id: str) -> str:
    return f"edumentor:count:{session_id}"


def make_mock_redis():
    """Return a preconfigured MagicMock that mimics redis.Redis behaviour."""
    mock = MagicMock()
    mock.ping.return_value = True
    mock.lrange.return_value = []
    mock.get.return_value = None
    return mock


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_redis():
    return make_mock_redis()


@pytest.fixture()
def backend(mock_redis):
    """Return a RedisBackend with redis.Redis patched to mock_redis."""
    mock_redis_class = MagicMock(return_value=mock_redis)
    mock_module = MagicMock()
    mock_module.Redis = MagicMock()
    mock_module.Redis.from_url = MagicMock(return_value=mock_redis)

    with patch.dict("sys.modules", {"redis": mock_module}):
        from agent.memory_manager import RedisBackend
        b = RedisBackend(redis_url="redis://localhost:6379")
    return b, mock_redis


# ── Construction ──────────────────────────────────────────────────────────────

class TestRedisBackendConstruction:
    def test_ping_called_on_init(self, backend):
        _, mock = backend
        mock.ping.assert_called_once()

    def test_import_error_raised_when_redis_not_installed(self):
        with patch.dict("sys.modules", {"redis": None}):
            with pytest.raises(ImportError, match="pip install redis"):
                # Force re-import to trigger the guard
                import importlib
                import agent.memory_manager as mm
                importlib.reload(mm)
                # Directly instantiate to trigger the guard
                from agent.memory_manager import RedisBackend as RB
                RB.__init__(RB.__new__(RB), "redis://localhost:6379")


# ── get() ─────────────────────────────────────────────────────────────────────

class TestRedisBackendGet:
    def test_get_empty_session(self, backend):
        b, mock = backend
        mock.lrange.return_value = []
        result = b.get("s1")
        assert result == []
        mock.lrange.assert_called_once_with(_mem_key("s1"), 0, -1)

    def test_get_deserialises_turns(self, backend):
        b, mock = backend
        turn = make_turn("what is X?", "X is Y.", intent="CONCEPT_EXPLANATION")
        mock.lrange.return_value = [_serialise(turn)]
        result = b.get("s1")
        assert len(result) == 1
        assert result[0].user == "what is X?"
        assert result[0].assistant == "X is Y."
        assert result[0].intent == "CONCEPT_EXPLANATION"

    def test_get_multiple_turns_in_order(self, backend):
        b, mock = backend
        turns = [make_turn(f"q{i}", f"a{i}") for i in range(3)]
        mock.lrange.return_value = [_serialise(t) for t in turns]
        result = b.get("s1")
        assert [r.user for r in result] == ["q0", "q1", "q2"]


# ── append() ─────────────────────────────────────────────────────────────────

class TestRedisBackendAppend:
    def test_append_calls_rpush(self, backend):
        b, mock = backend
        turn = make_turn("q1", "a1")
        b.append("s1", turn)
        mock.rpush.assert_called_once_with(_mem_key("s1"), _serialise(turn))

    def test_append_increments_count(self, backend):
        b, mock = backend
        b.append("s1", make_turn())
        mock.incr.assert_called_once_with(_count_key("s1"))

    def test_append_multiple_calls_rpush_each_time(self, backend):
        b, mock = backend
        for i in range(3):
            b.append("s1", make_turn(f"q{i}", f"a{i}"))
        assert mock.rpush.call_count == 3
        assert mock.incr.call_count == 3


# ── prune() ───────────────────────────────────────────────────────────────────

class TestRedisBackendPrune:
    def test_prune_calls_ltrim(self, backend):
        b, mock = backend
        b.prune("s1", max_turns=5)
        mock.ltrim.assert_called_once_with(_mem_key("s1"), -5, -1)

    def test_prune_zero_trims_all(self, backend):
        b, mock = backend
        b.prune("s1", max_turns=0)
        mock.ltrim.assert_called_once_with(_mem_key("s1"), 0, -1)


# ── clear() ───────────────────────────────────────────────────────────────────

class TestRedisBackendClear:
    def test_clear_deletes_both_keys(self, backend):
        b, mock = backend
        b.clear("s1")
        mock.delete.assert_any_call(_mem_key("s1"))
        mock.delete.assert_any_call(_count_key("s1"))
        assert mock.delete.call_count == 2


# ── count() ───────────────────────────────────────────────────────────────────

class TestRedisBackendCount:
    def test_count_zero_when_key_missing(self, backend):
        b, mock = backend
        mock.get.return_value = None
        assert b.count("s1") == 0

    def test_count_returns_parsed_integer(self, backend):
        b, mock = backend
        mock.get.return_value = "7"
        assert b.count("s1") == 7

    def test_count_uses_correct_key(self, backend):
        b, mock = backend
        mock.get.return_value = "3"
        b.count("s1")
        mock.get.assert_called_with(_count_key("s1"))


# ── Key helpers ───────────────────────────────────────────────────────────────

class TestRedisKeyHelpers:
    def test_mem_key_format(self):
        from agent.memory_manager import RedisBackend
        assert RedisBackend._mem_key("abc") == "edumentor:memory:abc"

    def test_count_key_format(self):
        from agent.memory_manager import RedisBackend
        assert RedisBackend._count_key("abc") == "edumentor:count:abc"

    def test_serialise_deserialise_round_trip(self):
        from agent.memory_manager import RedisBackend
        t = time.time()
        turn = make_turn("user msg", "assistant msg", timestamp=t, intent="QUIZ_REQUEST", emotion="curious")
        serialised = RedisBackend._serialise(turn)
        restored = RedisBackend._deserialise(serialised)
        assert restored.user == turn.user
        assert restored.assistant == turn.assistant
        assert restored.timestamp == pytest.approx(turn.timestamp, rel=1e-6)
        assert restored.intent == turn.intent
        assert restored.emotion == turn.emotion
