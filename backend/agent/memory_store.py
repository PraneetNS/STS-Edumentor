"""
backend/agent/memory_store.py

Shared types for cross-session memory (indexing + retrieval).

Deliberately built against Protocol interfaces for the vector store and
embedding function, not a concrete Qdrant client -- this environment has
no network access to Qdrant or an embedding model, so everything here is
proven against an in-memory fake first (see test_memory_recall.py). Swap
in your real Qdrant async client and embedding model without touching
MemoryIndexer or MemoryRetriever's logic at all.

This uses a SEPARATE collection from your existing course-content RAG
(knowledge_router.py) -- student session memory and course notes are
different data with different sensitivity, and mixing them risks a
course-content query surfacing another student's private session data.
Keep them in different collections even if using the same Qdrant instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class MemoryRecord:
    """One thing worth remembering from a past session. Built from your
    existing session_summarizer.py output, NOT raw turn-by-turn transcript
    -- summaries are shorter, less sensitive, and already the unit your
    system compresses to every 10 turns."""

    student_id: str
    session_id: str
    timestamp: float          # unix seconds
    topic: str                # e.g. "recursion_base_cases" -- matches your weak_areas taxonomy
    summary_text: str         # short human-readable summary, not a verbatim transcript
    was_weak_area: bool       # was this topic a weak area for the student at the time
    resolved: bool            # did the student end up demonstrating mastery in that session


@dataclass
class RecalledMemory:
    topic: str
    summary_text: str
    age_days: float
    relevance_score: float    # post-decay, post-filter score used for ranking


class EmbeddingFn(Protocol):
    async def embed(self, text: str) -> List[float]:
        ...


class VectorStore(Protocol):
    async def upsert(
        self, collection: str, record_id: str, vector: List[float], payload: Dict[str, Any]
    ) -> None:
        ...

    async def search(
        self,
        collection: str,
        vector: List[float],
        filter_payload: Dict[str, Any],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        filter_payload is a hard equality filter (e.g. {"student_id": "..."}),
        applied BEFORE similarity ranking -- this is what guarantees
        isolation between students. A real Qdrant adapter should use
        Qdrant's payload filter (must-match, not just a re-rank), not a
        post-hoc Python filter on results, so a filtered-out record never
        even counts against `limit`.

        Returns a list of {"score": float, "payload": dict}.
        """
        ...
