"""
backend/agent/memory_indexer.py

Writes MemoryRecords into the vector store after each session (or after
each session_summarizer.py compression cycle). Deliberately thin -- the
interesting logic is in retrieval (memory_retriever.py), not indexing.
"""

from __future__ import annotations

from agent.memory_store import EmbeddingFn, MemoryRecord, VectorStore

COLLECTION_NAME = "student_session_memory"


class MemoryIndexer:
    def __init__(
        self,
        vector_store: VectorStore,
        embedding_fn: EmbeddingFn,
        collection: str = COLLECTION_NAME,
    ):
        self.vector_store = vector_store
        self.embedding_fn = embedding_fn
        self.collection = collection

    async def index(self, record: MemoryRecord) -> None:
        vector = await self.embedding_fn.embed(record.summary_text)
        record_id = f"{record.student_id}:{record.session_id}:{int(record.timestamp)}"
        payload = {
            "student_id": record.student_id,
            "session_id": record.session_id,
            "timestamp": record.timestamp,
            "topic": record.topic,
            "summary_text": record.summary_text,
            "was_weak_area": record.was_weak_area,
            "resolved": record.resolved,
        }
        await self.vector_store.upsert(self.collection, record_id, vector, payload)
