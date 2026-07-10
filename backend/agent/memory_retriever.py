"""
backend/agent/memory_retriever.py

Retrieves relevant past-session memories for the CURRENT student, to feed
into the prompt as recall context ("last time you worked through X").

Two properties matter more than relevance ranking here, and both are
hard gates, not scoring inputs:

  1. ISOLATION. A memory belongs to exactly one student_id. The vector
     store's filter_payload does an equality filter BEFORE similarity
     search (see memory_store.py's VectorStore protocol docstring) --
     this module never even sees another student's records, let alone
     ranks them. Tested explicitly in test_memory_recall.py.

  2. NO STALE CALLBACKS. If a memory says "this was a weak area" but the
     student's CURRENT profile no longer lists that topic as weak (i.e.
     they've since mastered it) and the session where it was logged
     showed resolution, that memory is excluded from recall entirely --
     not down-weighted, excluded. Telling a student "you used to
     struggle with X" when the record shows they already fixed it reads
     as either stale or backhanded. If the topic is STILL a current weak
     area, the memory is surfaced regardless of whether that particular
     session ended in resolution (still relevant either way).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import List, Optional, Set

from agent.memory_store import EmbeddingFn, RecalledMemory, VectorStore

COLLECTION_NAME = "student_session_memory"


@dataclass
class RetrievalConfig:
    """Configuration knobs for the memory retriever.

    Shipped disabled by default (enabled=False) -- flip to True only after
    validating that your real Qdrant payload filter produces correct
    isolation in staging. A disabled retriever is a strict no-op.
    """
    enabled: bool = False
    top_k: int = 3
    overfetch_multiplier: int = 4       # fetch more than top_k before filtering/re-ranking
    max_age_days: float = 90.0          # hard cutoff regardless of relevance
    recency_half_life_days: float = 14.0
    min_relevance_score: float = 0.3    # post-decay floor


class MemoryRetriever:
    """Retrieves and ranks past-session memories for a single student.

    Enforces two hard gates before any ranking occurs:
      1. Student-ID isolation via the vector store's pre-filter.
      2. Staleness exclusion for resolved weak areas no longer current.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_fn: EmbeddingFn,
        config: Optional[RetrievalConfig] = None,
        collection: str = COLLECTION_NAME,
    ):
        self.vector_store = vector_store
        self.embedding_fn = embedding_fn
        self.config = config or RetrievalConfig()
        self.collection = collection

    async def retrieve(
        self,
        student_id: str,
        current_topic_query: str,
        current_weak_areas: Set[str],
        now: Optional[float] = None,
    ) -> List[RecalledMemory]:
        if not self.config.enabled:
            return []

        now = now if now is not None else time.time()
        vector = await self.embedding_fn.embed(current_topic_query)

        hits = await self.vector_store.search(
            self.collection,
            vector,
            filter_payload={"student_id": student_id},  # hard isolation filter
            limit=self.config.top_k * self.config.overfetch_multiplier,
        )

        scored: List[RecalledMemory] = []
        for hit in hits:
            payload = hit["payload"]

            # Defense in depth: even though the store's filter should
            # already guarantee this, never trust a single layer for
            # cross-student isolation.
            if payload.get("student_id") != student_id:
                continue

            age_days = (now - payload["timestamp"]) / 86400.0
            if age_days > self.config.max_age_days:
                continue

            # Hard exclude: resolved weak area that's no longer a
            # current weak area is stale, not just less relevant.
            if (
                payload.get("was_weak_area")
                and payload.get("resolved")
                and payload["topic"] not in current_weak_areas
            ):
                continue

            recency_weight = 0.5 ** (age_days / self.config.recency_half_life_days)
            final_score = hit["score"] * recency_weight

            if final_score < self.config.min_relevance_score:
                continue

            scored.append(
                RecalledMemory(
                    topic=payload["topic"],
                    summary_text=payload["summary_text"],
                    age_days=age_days,
                    relevance_score=final_score,
                )
            )

        scored.sort(key=lambda m: -m.relevance_score)
        return scored[: self.config.top_k]


def format_recall_context(memories: List[RecalledMemory]) -> str:
    """
    Turns recalled memories into a short prompt-injection blurb. Kept
    deliberately terse -- this is context for the LLM to draw on
    naturally, not a script to read verbatim to the student.
    """
    if not memories:
        return ""

    lines = ["Relevant context from past sessions with this student:"]
    for m in memories:
        age_desc = _describe_age(m.age_days)
        lines.append(f"- ({age_desc}) {m.summary_text}")
    return "\n".join(lines)


def _describe_age(age_days: float) -> str:
    if age_days < 1:
        return "earlier today"
    if age_days < 2:
        return "yesterday"
    if age_days < 14:
        return f"{int(age_days)} days ago"
    if age_days < 60:
        return f"{int(age_days / 7)} weeks ago"
    return f"{int(age_days / 30)} months ago"
