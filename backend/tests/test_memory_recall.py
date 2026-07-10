"""
backend/tests/test_memory_recall.py

Run with: pytest backend/tests/test_memory_recall.py -v

Uses an in-memory fake vector store + a deterministic bag-of-words
"embedding" (real cosine similarity math, fake vectors) so these tests
run without Qdrant or an embedding model. Swap in real implementations
of EmbeddingFn/VectorStore later -- MemoryIndexer and MemoryRetriever's
logic doesn't change.

The two properties tested most heavily, because they're the ones that
matter if this is wrong in production:
  - ISOLATION: student A's memories must never surface for student B,
    even when content is near-identical.
  - STALENESS: a resolved weak area that's no longer current must not
    be resurfaced as if the student still struggles with it.
"""

import math
import time
from collections import defaultdict
from typing import Any, Dict, List

import pytest

from agent.memory_indexer import MemoryIndexer
from agent.memory_retriever import MemoryRetriever, RetrievalConfig, format_recall_context
from agent.memory_store import MemoryRecord

# Note: pytest.ini sets asyncio_mode = auto, so async def tests are
# auto-detected -- no module-level pytestmark needed, and none applied
# here so the two synchronous formatting tests below don't get an
# irrelevant asyncio marker.


# ---------------------------------------------------------------------------
# Fakes: deterministic, dependency-free stand-ins for real infra.
# ---------------------------------------------------------------------------

class FakeEmbeddingFn:
    """Bag-of-words hashing into a fixed-size vector. Not a real embedding
    model -- just deterministic enough that similar text produces similar
    vectors, so relevance ranking logic can be tested meaningfully."""

    def __init__(self, dim: int = 64):
        self.dim = dim

    async def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for word in text.lower().split():
            idx = hash(word) % self.dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FakeVectorStore:
    """In-memory store with a real equality pre-filter (matching how a
    real Qdrant payload filter should behave) followed by cosine
    similarity ranking."""

    def __init__(self):
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    async def upsert(self, collection, record_id, vector, payload):
        self._data[collection][record_id] = {"vector": vector, "payload": payload}

    async def search(self, collection, vector, filter_payload, limit):
        candidates = []
        for record_id, entry in self._data[collection].items():
            payload = entry["payload"]
            # Hard equality filter BEFORE ranking -- matches how a real
            # Qdrant payload filter works, and is what isolation relies on.
            if all(payload.get(k) == v for k, v in filter_payload.items()):
                score = _cosine(vector, entry["vector"])
                candidates.append({"score": score, "payload": payload})
        candidates.sort(key=lambda c: -c["score"])
        return candidates[:limit]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot  # both already unit-normalized in FakeEmbeddingFn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    return FakeVectorStore()


@pytest.fixture
def embed():
    return FakeEmbeddingFn()


@pytest.fixture
def indexer(store, embed):
    return MemoryIndexer(store, embed)


@pytest.fixture
def retriever(store, embed):
    return MemoryRetriever(
        store,
        embed,
        RetrievalConfig(
            enabled=True,
            top_k=3,
            max_age_days=90.0,
            recency_half_life_days=14.0,
            min_relevance_score=0.05,  # low, so ranking differences are visible in tests
        ),
    )


def days_ago(n: float) -> float:
    return time.time() - n * 86400.0


# --- Disabled is a true no-op -----------------------------------------------

async def test_disabled_returns_nothing(store, embed, indexer):
    retriever = MemoryRetriever(store, embed, RetrievalConfig(enabled=False))
    await indexer.index(MemoryRecord(
        student_id="s1", session_id="sess1", timestamp=days_ago(1),
        topic="recursion", summary_text="worked through recursion base cases",
        was_weak_area=True, resolved=True,
    ))
    result = await retriever.retrieve("s1", "recursion base cases", current_weak_areas=set())
    assert result == []


# --- Isolation: the property that matters most -----------------------------

async def test_students_never_see_each_others_memories(indexer, retriever):
    await indexer.index(MemoryRecord(
        student_id="student-A", session_id="sessA", timestamp=days_ago(2),
        topic="recursion", summary_text="student worked through recursion base cases",
        was_weak_area=True, resolved=False,
    ))
    await indexer.index(MemoryRecord(
        student_id="student-B", session_id="sessB", timestamp=days_ago(2),
        topic="recursion", summary_text="student worked through recursion base cases",
        was_weak_area=True, resolved=False,
    ))

    results_a = await retriever.retrieve("student-A", "recursion base cases", current_weak_areas={"recursion"})
    results_b = await retriever.retrieve("student-B", "recursion base cases", current_weak_areas={"recursion"})

    assert len(results_a) == 1
    assert len(results_b) == 1
    # Both retrieved successfully but each only sees their OWN record --
    # verified indirectly here since content is identical; the isolation
    # test that actually matters is the next one.


async def test_one_student_with_no_memories_gets_nothing_even_if_another_students_content_matches(
    indexer, retriever
):
    await indexer.index(MemoryRecord(
        student_id="student-A", session_id="sessA", timestamp=days_ago(1),
        topic="pointers", summary_text="deep dive into pointer arithmetic and dangling pointers",
        was_weak_area=True, resolved=False,
    ))

    # student-B has no memories at all -- even though their query is
    # highly semantically similar to student-A's indexed content, they
    # must get zero results.
    results_b = await retriever.retrieve(
        "student-B", "pointer arithmetic and dangling pointers", current_weak_areas={"pointers"}
    )
    assert results_b == []
