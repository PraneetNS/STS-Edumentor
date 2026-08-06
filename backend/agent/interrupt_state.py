from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
import json
import logging

logger = logging.getLogger("edumentor.agent.interrupt_state")

class ThreadStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    RESUMED = "resumed"
    COMPLETED = "completed"

@dataclass
class ConversationThread:
    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_thread_id: Optional[str] = None   # for nested interruptions
    topic: str = ""                          # e.g. "binary search time complexity"
    original_question: str = ""              # the question that started this thread

    spoken_sentences: List[str] = field(default_factory=list)   # fully spoken so far
    cut_sentence: Optional[str] = None        # the sentence TTS was mid-way through
    cut_char_offset: int = 0                  # how far into cut_sentence we got
    remaining_plan: List[str] = field(default_factory=list)      # sentences not yet spoken

    status: ThreadStatus = ThreadStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    paused_at: Optional[datetime] = None

    # what interrupted it, so the resume bridge has something to reference
    interruption_summary: Optional[str] = None

    def remaining_plan_as_text(self) -> str:
        return " ".join(self.remaining_plan)

class InterruptStack:
    """One per active session. Backed by state_store in multi-instance deploys —
    key: f"interrupt_stack:{session_id}", value: LIST of JSON-encoded ConversationThread."""

    def __init__(self, session_id: str, store=None, db_manager=None):
        self.session_id = session_id
        from agent.state_store import get_state_store
        self.store = store or get_state_store()
        self.db_manager = db_manager
        self.key = f"interrupt_stack:{session_id}"

    async def clear(self) -> None:
        await self.store.delete(self.key)

    async def push(self, thread: ConversationThread):
        from config import Config
        thread.status = ThreadStatus.PAUSED
        thread.paused_at = datetime.utcnow()
        
        serialized = json.dumps(self._to_dict(thread))
        await self.store.rpush(self.key, serialized)
        
        # Set/Refresh TTL
        ttl_seconds = Config.RESUME_TTL_HOURS * 3600
        await self.store.expire(self.key, ttl_seconds)

        if self.db_manager:
            import asyncio
            asyncio.create_task(self.db_manager.save_thread(thread, self.session_id))

    async def pop(self) -> Optional[ConversationThread]:
        from config import Config
        serialized = await self.store.rpop(self.key)
        if not serialized:
            return None
            
        thread = self._from_dict(json.loads(serialized))
        thread.status = ThreadStatus.RESUMED
        
        # Refresh TTL if stack still has items
        if await self.store.llen(self.key) > 0:
            ttl_seconds = Config.RESUME_TTL_HOURS * 3600
            await self.store.expire(self.key, ttl_seconds)
            
        if self.db_manager:
            import asyncio
            asyncio.create_task(self.db_manager.update_thread_status(thread.thread_id, "resumed"))
            
        return thread

    async def peek_topic(self) -> Optional[str]:
        elements = await self.store.lrange(self.key, -1, -1)
        if not elements:
            return None
        thread = self._from_dict(json.loads(elements[0]))
        return thread.topic

    async def depth(self) -> int:
        return await self.store.llen(self.key)

    def _to_dict(self, t: ConversationThread) -> Dict[str, Any]:
        return {
            "thread_id": t.thread_id,
            "parent_thread_id": t.parent_thread_id,
            "topic": t.topic,
            "original_question": t.original_question,
            "spoken_sentences": t.spoken_sentences,
            "cut_sentence": t.cut_sentence,
            "cut_char_offset": t.cut_char_offset,
            "remaining_plan": t.remaining_plan,
            "status": t.status.value if hasattr(t.status, 'value') else t.status,
            "created_at": t.created_at.isoformat() if isinstance(t.created_at, datetime) else t.created_at,
            "paused_at": t.paused_at.isoformat() if isinstance(t.paused_at, datetime) else t.paused_at,
            "interruption_summary": t.interruption_summary
        }

    def _from_dict(self, d: Dict[str, Any]) -> ConversationThread:
        return ConversationThread(
            thread_id=d.get("thread_id", str(uuid.uuid4())),
            parent_thread_id=d.get("parent_thread_id"),
            topic=d.get("topic", ""),
            original_question=d.get("original_question", ""),
            spoken_sentences=d.get("spoken_sentences", []),
            cut_sentence=d.get("cut_sentence"),
            cut_char_offset=d.get("cut_char_offset", 0),
            remaining_plan=d.get("remaining_plan", []),
            status=ThreadStatus(d["status"]) if d.get("status") else ThreadStatus.ACTIVE,
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d.get("created_at"), str) else d.get("created_at", datetime.utcnow()),
            paused_at=datetime.fromisoformat(d["paused_at"]) if isinstance(d.get("paused_at"), str) else d.get("paused_at"),
            interruption_summary=d.get("interruption_summary")
        )
