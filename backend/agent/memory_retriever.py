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
