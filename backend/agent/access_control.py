"""
EduMentor Agent Layer — Access Control (LLM08: Session & Data Isolation)

Provides session ownership verification and ChromaDB query scoping to prevent
one student's session or data from being accessed by another.

Design:
  - verify_session_ownership() is Step 0 in every handle_turn / stream() call.
    It must fire BEFORE any safety check, intent classification, or memory
    retrieval — because those steps may themselves read per-student data.

  - When PostgreSQL is available, ownership is verified against the
    conversation_logs table (authoritative, persistent across restarts).

  - When PostgreSQL is disabled (POSTGRES_ENABLED=false), the method falls
    back to an in-memory session registry (_session_owner_map). This avoids
    the permissive-failure anti-pattern (returning True unconditionally when
    the DB is offline), which would silently disable GAP 1 in any deployment
    not running Postgres.

  NOTE — Single-instance caveat (in-memory path):
    _session_owner_map is process-local. In a horizontally scaled deployment
    (multiple FastAPI workers), a session registered in worker A is not
    visible to worker B. For multi-instance deployments, replace the in-memory
    map with a shared Redis key-value store using the same SETNX pattern.
    This is the same limitation as rate_limiter.py's in-memory tracking.

ChromaDB Isolation:
  - scope_chromadb_query() injects a mandatory student_id metadata filter
    into every ChromaDB query dict. Never allow an unscoped query.

  - See ChromaDBIsolationAudit below for the highest-risk configuration flag.

Pipeline position:
  controller.stream() → Step 0: AccessControl.verify_session_ownership()
  knowledge_router.retrieve() → AccessControl.scope_chromadb_query()
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger("edumentor.agent.access_control")

# ─────────────────────────────────────────────────────────────────────────────
# In-memory session registry (fallback when PostgreSQL is disabled)
# ─────────────────────────────────────────────────────────────────────────────

# session_id → first student_id that claimed it
# This is process-local. See module docstring for multi-instance caveat.
_session_owner_map: Dict[str, str] = {}


# ─────────────────────────────────────────────────────────────────────────────
# ChromaDB Isolation Audit
# ─────────────────────────────────────────────────────────────────────────────


class ChromaDBIsolationAudit:
    """
    Documents the ChromaDB isolation risk and recommended collection layout.

    SHARED KNOWLEDGE (course content, DSA concepts, engineering topics):
      - Collection: "edumentor_shared_knowledge"
      - NOT student-scoped — this is intentional. All students query the same
        collection. No student_id filter is needed or desired here.

    STUDENT-PRIVATE DATA (conversation summaries, embedded profile notes):
      - If any per-student text is ever embedded and indexed into ChromaDB,
        it MUST go into a SEPARATE collection from shared knowledge.
      - Recommended naming: "edumentor_student_{student_id}"
      - Alternatively, a shared private collection with a MANDATORY
        student_id metadata filter on every query (enforced via
        AccessControl.scope_chromadb_query()).

    HIGHEST-RISK CONFIGURATION — FLAG:
      Storing student-private embeddings in the SAME collection as shared
      knowledge, relying solely on metadata filters for isolation, is the
      riskiest layout. A single missed filter in one query path leaks
      all students' private data. Separate collections are strongly preferred.

    CURRENT STATE (as of this audit):
      The KnowledgeRouter uses a stub RAGBackend returning None — no real
      ChromaDB integration exists yet. This class documents the constraints
      that must be enforced when a real backend is wired.
    """
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Access Control
# ─────────────────────────────────────────────────────────────────────────────


class AccessControl:
    """
    Enforces session ownership and ChromaDB query scoping.

    All methods are static — no instance state. The module-level
    _session_owner_map is shared across all calls (in-memory fallback path).
    """

    @staticmethod
    async def verify_session_ownership(
        session_id: str,
        claimed_student_id: str,
        db_pool: Any,  # asyncpg.Pool | None
    ) -> bool:
        """
        Confirm that session_id actually belongs to claimed_student_id.

        Call this on EVERY request — not just at WebSocket connection time.
        Sessions can be replayed, guessed, or injected in WebSocket frames
        mid-stream.

        Args:
            session_id:          The session ID from the incoming request.
            claimed_student_id:  The student ID the request claims to own.
            db_pool:             asyncpg connection pool, or None if DB is off.

        Returns:
            True  → ownership confirmed (or new session, registered now).
            False → ownership violation detected.
        """
        if not session_id or not claimed_student_id:
            logger.warning(
                "[ACCESS_CONTROL] Missing session_id or student_id. "
                "session_id=%r claimed=%r", session_id, claimed_student_id
            )
            return False

        # ── Path A: PostgreSQL is available ───────────────────────────────────
        if db_pool is not None:
            return await AccessControl._verify_via_postgres(
                session_id, claimed_student_id, db_pool
            )

        # ── Path B: PostgreSQL is disabled — in-memory registry ───────────────
        return AccessControl._verify_via_memory(session_id, claimed_student_id)

    @staticmethod
    async def _verify_via_postgres(
        session_id: str,
        claimed_student_id: str,
        db_pool: Any,
    ) -> bool:
        """
        Check conversation_logs: does any row for this session_id belong to a
        different student_id? If yes → violation. If no rows exist → new
        session, allowed.
        """
        try:
            # Normalise to UUID for the query
            try:
                session_uuid = uuid.UUID(session_id)
            except ValueError:
                session_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, session_id)

            try:
                student_uuid = uuid.UUID(claimed_student_id)
            except ValueError:
                student_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, claimed_student_id)

            query = """
                SELECT COUNT(*) AS mismatch_count
                FROM conversation_logs
                WHERE session_id = $1
                  AND user_id    != $2
                LIMIT 1;
            """
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, session_uuid, student_uuid)
                mismatch_count = row["mismatch_count"] if row else 0

            if mismatch_count > 0:
                logger.warning(
                    "[ACCESS_CONTROL] Session ownership violation (postgres). "
                    "session_id=%r claimed_student=%r mismatch_rows=%d",
                    session_id, claimed_student_id, mismatch_count
                )
                return False

            logger.debug(
                "[ACCESS_CONTROL] Session ownership confirmed (postgres). "
                "session_id=%r student=%r", session_id, claimed_student_id
            )
            return True

        except Exception as exc:
            # DB error: fail closed (deny access) rather than permissive
            logger.error(
                "[ACCESS_CONTROL] PostgreSQL ownership check failed: %s. "
                "Failing closed — denying access.", exc
            )
            return False

    @staticmethod
    def _verify_via_memory(session_id: str, claimed_student_id: str) -> bool:
        """
        In-memory fallback: register the session owner on first use, then
        reject any subsequent claim from a different student_id.

        This is NOT permissive — it enforces isolation within a single
        process lifetime, which covers the primary attack surface of
        session ID guessing or header injection within an active server.
        """
        existing_owner = _session_owner_map.get(session_id)

        if existing_owner is None:
            # First claim: register this student as the owner
            _session_owner_map[session_id] = claimed_student_id
            logger.debug(
                "[ACCESS_CONTROL] Session registered in memory. "
                "session_id=%r owner=%r", session_id, claimed_student_id
            )
            return True

        if existing_owner != claimed_student_id:
            logger.warning(
                "[ACCESS_CONTROL] Session ownership violation (in-memory). "
                "session_id=%r registered_owner=%r claimed=%r",
                session_id, existing_owner, claimed_student_id
            )
            return False

        return True

    @staticmethod
    def scope_chromadb_query(query_filter: dict, student_id: str) -> dict:
        """
        Inject a mandatory student_id metadata filter into a ChromaDB query.

        Every ChromaDB query against student-private collections (conversation
        summaries, embedded profile notes) MUST be scoped with this filter.
        Shared-knowledge queries (course content, DSA concepts) are exempt —
        that data is intentionally cross-student.

        Args:
            query_filter:  The existing ChromaDB where-clause dict (may be {}).
            student_id:    The verified student_id from verify_session_ownership.

        Returns:
            The query_filter dict with student_id injected.

        Example:
            # Before: {"topic": "sorting"}
            # After:  {"topic": "sorting", "student_id": "stu_abc123"}
        """
        if not student_id:
            raise ValueError(
                "scope_chromadb_query() called with empty student_id. "
                "This would produce an unscoped query — rejected."
            )
        query_filter["student_id"] = student_id
        return query_filter

    @staticmethod
    def release_session(session_id: str) -> None:
        """
        Remove a session from the in-memory registry on disconnect.

        Call this in main.py's WebSocket disconnect handler. Prevents the
        in-memory map from growing unboundedly in long-running servers.
        """
        removed = _session_owner_map.pop(session_id, None)
        if removed:
            logger.debug(
                "[ACCESS_CONTROL] Session released from memory. "
                "session_id=%r", session_id
            )
