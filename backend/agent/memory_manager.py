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

import logging
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
# SQLite Backend (stub — future implementation)
# ─────────────────────────────────────────────────────────────────────────────

class SQLiteBackend(MemoryBackend):
    """
    SQLite-backed memory backend for cross-restart persistence.

    TODO: Implement using sqlite3 stdlib module.
    Schema:
        CREATE TABLE memory_turns (
            session_id TEXT,
            user_text  TEXT,
            assistant_text TEXT,
            timestamp  REAL,
            intent     TEXT,
            emotion    TEXT
        );
    """

    def __init__(self, db_path: str = "data/memory.db") -> None:
        raise NotImplementedError(
            "SQLiteBackend is not yet implemented. "
            "Use InMemoryBackend (default) or implement this class."
        )

    def get(self, session_id: str) -> List[MemoryTurn]: ...
    def append(self, session_id: str, turn: MemoryTurn) -> None: ...
    def prune(self, session_id: str, max_turns: int) -> None: ...
    def clear(self, session_id: str) -> None: ...
    def count(self, session_id: str) -> int: ...


# ─────────────────────────────────────────────────────────────────────────────
# Redis Backend (stub — future implementation)
# ─────────────────────────────────────────────────────────────────────────────

class RedisBackend(MemoryBackend):
    """
    Redis-backed memory backend for distributed / multi-instance deployments.

    TODO: Implement using redis-py (pip install redis).
    Pattern:
        key = f"edumentor:memory:{session_id}"
        Store as Redis list of JSON-encoded MemoryTurn dicts.
        LTRIM to implement pruning.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        raise NotImplementedError(
            "RedisBackend is not yet implemented. "
            "Set MEMORY_BACKEND=memory (default) in .env to use InMemoryBackend."
        )

    def get(self, session_id: str) -> List[MemoryTurn]: ...
    def append(self, session_id: str, turn: MemoryTurn) -> None: ...
    def prune(self, session_id: str, max_turns: int) -> None: ...
    def clear(self, session_id: str) -> None: ...
    def count(self, session_id: str) -> int: ...


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

