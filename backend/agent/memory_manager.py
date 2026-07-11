"""
EduMentor Agent Layer — Memory Manager

Session-based multi-turn conversation memory with a pluggable backend
abstraction layer for future upgrades (SQLite, Redis).

Architecture:
  MemoryBackend (abstract protocol)
    └── InMemoryBackend  ← default, dict-based, cleared on restart
    └── SQLiteBackend    ← stub, ready to implement
    └── RedisBackend     ← stub, ready to implement

  MemoryManager (public API)
    ├── get_session()          → list[MemoryTurn]
    ├── add_turn()             → None  (prunes + triggers summarizer)
    ├── get_relevant_history() → list[MemoryTurn]
    └── clear_session()        → None

Design notes:
  - Session memory is keyed by session_id (derived from WebSocket client addr).
  - add_turn() automatically prunes to Config.MEMORY_MAX_TURNS (default 10).
  - After every 10 turns, the SessionSummarizer is notified asynchronously.
  - History is returned newest-first for relevance, then reversed for prompt order.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from agent.models import MemoryTurn

logger = logging.getLogger("edumentor.agent.memory")


# ─────────────────────────────────────────────────────────────────────────────
# Backend Protocol
# ─────────────────────────────────────────────────────────────────────────────

class MemoryBackend(ABC):
    """
    Abstract interface for session memory storage.

    Implement this to swap the storage mechanism without touching
    MemoryManager or any calling code.
    """

    @abstractmethod
    def get(self, session_id: str) -> List[MemoryTurn]:
        """Return all stored turns for a session (oldest first)."""
        ...

    @abstractmethod
    def append(self, session_id: str, turn: MemoryTurn) -> None:
        """Append a single turn to a session's history."""
        ...

    @abstractmethod
    def prune(self, session_id: str, max_turns: int) -> None:
        """Keep only the most recent max_turns turns."""
        ...

    @abstractmethod
    def clear(self, session_id: str) -> None:
        """Delete all turns for a session."""
        ...

    @abstractmethod
    def count(self, session_id: str) -> int:
        """Return the total number of turns ever added to a session."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# In-Memory Backend (default)
# ─────────────────────────────────────────────────────────────────────────────

class InMemoryBackend(MemoryBackend):
    """
    Pure Python dict-based memory backend.

    - Zero dependencies
    - Cleared on server restart (by design for Phase 4)
    - O(1) access, O(n) prune
    """

    def __init__(self) -> None:
        # session_id → list of MemoryTurn (oldest first)
        self._store: Dict[str, List[MemoryTurn]] = {}
        # Total turn count per session (never decremented, used for summarizer trigger)
        self._total_counts: Dict[str, int] = {}

    def get(self, session_id: str) -> List[MemoryTurn]:
        return list(self._store.get(session_id, []))

    def append(self, session_id: str, turn: MemoryTurn) -> None:
        if session_id not in self._store:
            self._store[session_id] = []
            self._total_counts[session_id] = 0
        self._store[session_id].append(turn)
        self._total_counts[session_id] += 1

    def prune(self, session_id: str, max_turns: int) -> None:
        turns = self._store.get(session_id, [])
        if len(turns) > max_turns:
            self._store[session_id] = turns[-max_turns:]

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._total_counts.pop(session_id, None)

    def count(self, session_id: str) -> int:
        """Total turns ever added (including pruned ones)."""
        return self._total_counts.get(session_id, 0)


# ─────────────────────────────────────────────────────────────────────────────
# SQLite Backend
# ─────────────────────────────────────────────────────────────────────────────

class SQLiteBackend(MemoryBackend):
    """
    SQLite-backed memory backend for cross-restart persistence.

    Uses Python's stdlib sqlite3 module — zero external dependencies.
    All turns are persisted to disk and survive server restarts.

    Schema:
        CREATE TABLE memory_turns (
            session_id     TEXT    NOT NULL,
            user_text      TEXT    NOT NULL,
            assistant_text TEXT    NOT NULL,
            timestamp      REAL    NOT NULL,
            intent         TEXT,
            emotion        TEXT
        );
        CREATE INDEX idx_memory_session ON memory_turns (session_id, timestamp);
    """

    def __init__(self, db_path: str = "data/memory.db") -> None:
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._db_path = db_path
        self._init_db()
        logger.info("[OK] SQLiteBackend ready (db=%s).", db_path)

    # ── internal helpers ───────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_turns (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id     TEXT    NOT NULL,
                    user_text      TEXT    NOT NULL,
                    assistant_text TEXT    NOT NULL,
                    timestamp      REAL    NOT NULL,
                    intent         TEXT,
                    emotion        TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_session
                ON memory_turns (session_id, timestamp)
            """)
            conn.commit()

    @staticmethod
    def _row_to_turn(row: sqlite3.Row) -> MemoryTurn:
        return MemoryTurn(
            user=row["user_text"],
            assistant=row["assistant_text"],
            timestamp=row["timestamp"],
            intent=row["intent"],
            emotion=row["emotion"],
        )

    # ── MemoryBackend interface ────────────────────────────────────────────────

    def get(self, session_id: str) -> List[MemoryTurn]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_turns WHERE session_id=? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
        return [self._row_to_turn(r) for r in rows]

    def append(self, session_id: str, turn: MemoryTurn) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_turns
                    (session_id, user_text, assistant_text, timestamp, intent, emotion)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, turn.user, turn.assistant, turn.timestamp, turn.intent, turn.emotion),
            )
            conn.commit()

    def prune(self, session_id: str, max_turns: int) -> None:
        """Delete oldest rows keeping only the most recent max_turns."""
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM memory_turns
                WHERE session_id=? AND id NOT IN (
                    SELECT id FROM memory_turns
                    WHERE session_id=?
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                """,
                (session_id, session_id, max_turns),
            )
            conn.commit()

    def clear(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM memory_turns WHERE session_id=?", (session_id,))
            conn.commit()

    def count(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM memory_turns WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return row["cnt"] if row else 0


# ─────────────────────────────────────────────────────────────────────────────
# Redis Backend
# ─────────────────────────────────────────────────────────────────────────────

class RedisBackend(MemoryBackend):
    """
    Redis-backed memory backend for distributed / multi-instance deployments.

    Requires: pip install redis

    Storage pattern:
        key  = f"edumentor:memory:{session_id}"     — list of JSON-encoded turns
        key2 = f"edumentor:count:{session_id}"      — total turn counter (INCR)

    Each MemoryTurn is JSON-serialised and pushed to the right of a Redis list.
    Pruning uses LTRIM to keep only the most recent N items.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        try:
            import redis as redis_lib  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "RedisBackend requires 'redis' package. "
                "Install it with: pip install redis"
            ) from exc

        self._client = redis_lib.Redis.from_url(redis_url, decode_responses=True)
        # Ping to validate connection at startup
        self._client.ping()
        logger.info("[OK] RedisBackend ready (url=%s).", redis_url)

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _mem_key(session_id: str) -> str:
        return f"edumentor:memory:{session_id}"

    @staticmethod
    def _count_key(session_id: str) -> str:
        return f"edumentor:count:{session_id}"

    @staticmethod
    def _serialise(turn: MemoryTurn) -> str:
        return json.dumps(turn.to_dict())

    @staticmethod
    def _deserialise(raw: str) -> MemoryTurn:
        d = json.loads(raw)
        return MemoryTurn(
            user=d["user"],
            assistant=d["assistant"],
            timestamp=d.get("timestamp", time.time()),
            intent=d.get("intent"),
            emotion=d.get("emotion"),
        )

    # ── MemoryBackend interface ────────────────────────────────────────────────

    def get(self, session_id: str) -> List[MemoryTurn]:
        raw_list = self._client.lrange(self._mem_key(session_id), 0, -1)
        return [self._deserialise(r) for r in raw_list]

    def append(self, session_id: str, turn: MemoryTurn) -> None:
        self._client.rpush(self._mem_key(session_id), self._serialise(turn))
        self._client.incr(self._count_key(session_id))

    def prune(self, session_id: str, max_turns: int) -> None:
        """Keep only the most recent max_turns entries (LTRIM from the right)."""
        self._client.ltrim(self._mem_key(session_id), -max_turns, -1)

    def clear(self, session_id: str) -> None:
        self._client.delete(self._mem_key(session_id))
        self._client.delete(self._count_key(session_id))

    def count(self, session_id: str) -> int:
        val = self._client.get(self._count_key(session_id))
        return int(val) if val is not None else 0


# ─────────────────────────────────────────────────────────────────────────────
# Backend Factory
# ─────────────────────────────────────────────────────────────────────────────

def get_backend(backend_name: str, **kwargs) -> MemoryBackend:
    """
    Instantiate and return a MemoryBackend from a config string.

    Args:
        backend_name: One of ``"memory"``, ``"sqlite"``, or ``"redis"``.
        **kwargs:     Forwarded to the backend constructor.
                      - SQLiteBackend: ``db_path``
                      - RedisBackend:  ``redis_url``

    Returns:
        A fully-initialised MemoryBackend instance.

    Raises:
        ValueError: For unknown backend names.
    """
    name = backend_name.lower().strip()
    if name == "memory":
        return InMemoryBackend()
    if name == "sqlite":
        return SQLiteBackend(**kwargs)
    if name == "redis":
        return RedisBackend(**kwargs)
    raise ValueError(
        f"Unknown MEMORY_BACKEND '{backend_name}'. "
        "Choose one of: 'memory', 'sqlite', 'redis'."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public MemoryManager API
# ─────────────────────────────────────────────────────────────────────────────

class MemoryManager:
    """
    Public API for session-based conversation memory.

    This is the only class that should be used by AgentController and
    other modules. Internal storage is managed by the chosen MemoryBackend.

    Args:
        max_turns:   Max turns to keep per session (default from config).
        backend:     Storage backend (default: InMemoryBackend).
        summarizer:  Optional SessionSummarizer instance for auto-summarization.
    """

    def __init__(
        self,
        max_turns: int = 10,
        backend: Optional[MemoryBackend] = None,
        summarizer=None,  # Type: Optional[SessionSummarizer] — avoided circular import
    ) -> None:
        self._max_turns = max_turns
        self._backend   = backend or InMemoryBackend()
        self._summarizer = summarizer  # Injected after construction to avoid circular imports
        logger.info(
            "[OK] MemoryManager ready (backend=%s, max_turns=%d).",
            type(self._backend).__name__, max_turns
        )

    def set_summarizer(self, summarizer) -> None:
        """
        Inject the SessionSummarizer after construction.

        Called from AgentController.__init__() to avoid circular imports
        between MemoryManager ↔ SessionSummarizer.
        """
        self._summarizer = summarizer

    # ─────────────────────────────────────────────────────────────────────────
    # Core CRUD operations
    # ─────────────────────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> List[MemoryTurn]:
        """
        Return all stored turns for a session (oldest first).

        Args:
            session_id: The WebSocket session identifier.

        Returns:
            List of MemoryTurn objects, oldest first.
        """
        turns = self._backend.get(session_id)
        logger.debug(
            "[MEMORY] get_session(%s) → %d turns", session_id, len(turns)
        )
        return turns

    def add_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        intent: Optional[str] = None,
        emotion: Optional[str] = None,
    ) -> None:
        """
        Add a completed conversation turn to memory.

        Automatically:
          1. Appends the turn
          2. Prunes to max_turns
          3. Triggers SessionSummarizer every 10 turns (if wired)

        Args:
            session_id:     The WebSocket session identifier.
            user_text:      The student's transcribed speech.
            assistant_text: The full LLM response text.
            intent:         Classified intent (for metadata).
            emotion:        Detected emotion (for metadata).
        """
        turn = MemoryTurn(
            user=user_text,
            assistant=assistant_text,
            intent=intent,
            emotion=emotion,
        )
        self._backend.append(session_id, turn)
        self._backend.prune(session_id, self._max_turns)

        total = self._backend.count(session_id)
        logger.info(
            "[MEMORY] add_turn session=%s total_turns=%d intent=%s emotion=%s",
            session_id, total, intent, emotion
        )

        # Trigger summarization every 10 turns (background, non-blocking)
        if self._summarizer and total > 0 and total % 10 == 0:
            logger.info(
                "[MEMORY] Triggering summarizer at turn %d for session=%s",
                total, session_id
            )
            # Get all history before the window slides for summarization
            full_history = self._backend.get(session_id)
            self._summarizer.schedule_summarize(session_id, full_history, total)

    def get_relevant_history(
        self,
        session_id: str,
        max_turns: Optional[int] = None,
    ) -> List[MemoryTurn]:
        """
        Return the most recent turns for prompt injection.

        Returns turns in chronological order (oldest first) — which is the
        order needed for chat message history in LLM prompts.

        Args:
            session_id: The WebSocket session identifier.
            max_turns:  Override for max turns (defaults to self._max_turns).

        Returns:
            List of MemoryTurn, chronological order (oldest first).
        """
        n = max_turns or self._max_turns
        turns = self._backend.get(session_id)
        # Return the most recent N turns in chronological order
        relevant = turns[-n:] if len(turns) > n else turns
        logger.debug(
            "[MEMORY] get_relevant_history(%s) → %d turns",
            session_id, len(relevant)
        )
        return relevant

    def clear_session(self, session_id: str) -> None:
        """
        Delete all memory for a session.

        Called on WebSocket disconnect or explicit reset.

        Args:
            session_id: The session to clear.
        """
        self._backend.clear(session_id)
        logger.info("[MEMORY] Session cleared: %s", session_id)

    def get_turn_count(self, session_id: str) -> int:
        """
        Return the total number of turns ever added to a session.

        Note: This is the cumulative count, not the current window size.
        Use len(get_session()) for the current window size.

        Args:
            session_id: The session identifier.

        Returns:
            Total turn count (including pruned turns).
        """
        return self._backend.count(session_id)

    def get_context(self, session_id: str) -> str:
        """
        Reconstruct all conversation turns in the session as a single string context.
        """
        turns = self.get_session(session_id)
        context_str = ""
        for turn in turns:
            context_str += f"User: {turn.user}\nAssistant: {turn.assistant}\n"
        return context_str

