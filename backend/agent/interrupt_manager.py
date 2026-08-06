from __future__ import annotations

import logging
import time
from typing import Dict, Optional, List, Any

from agent.models import InterruptState
from agent.interrupt_state import ConversationThread, InterruptStack, ThreadStatus

logger = logging.getLogger("edumentor.agent.interrupt")

RESUME_BRIDGE_SYSTEM_PROMPT = """You are Edi, resuming a paused explanation. You are NOT restarting the explanation and NOT repeating what was already said verbatim.

Write exactly ONE short spoken sentence that:
- naturally references what was being discussed before
- acknowledges time has passed / a question was answered in between
- transitions cleanly into continuing

Do not summarize the whole prior explanation. Do not apologize. Do not say "as I was saying" more than once ever, vary the phrasing.

Context:
- Topic: {topic}
- Last fully spoken sentence before interruption: "{last_sentence}"
- What interrupted it (if anything): {interruption_summary}

Output ONLY the bridge sentence, nothing else."""

class InterruptManager:
    """
    Manages conversation interruption stacks and active thread states.
    """

    def __init__(self, db_manager=None) -> None:
        self.db_manager = db_manager
        # session_id → list of ConversationThread (the stack)
        self._store = {}
        # session_id → active ConversationThread
        self._active_threads: Dict[str, ConversationThread] = {}

        # Legacy backward compatibility fields
        self._states: Dict[str, InterruptState] = {}
        self._chars_sent: Dict[str, int] = {}

        logger.info("[OK] InterruptManager ready.")

    def get_stack(self, session_id: str) -> InterruptStack:
        return InterruptStack(session_id, self._store, self.db_manager)

    async def set_stack(self, session_id: str, threads: List[ConversationThread]) -> None:
        """Sets/overwrites the stack for a session (used on reconnect loading)."""
        stack = self.get_stack(session_id)
        await stack.clear()
        for t in threads:
            await stack.push(t)

    def set_active_thread(self, session_id: str, thread: ConversationThread) -> None:
        self._active_threads[session_id] = thread

    def get_active_thread(self, session_id: str) -> Optional[ConversationThread]:
        return self._active_threads.get(session_id)

    def clear_active_thread(self, session_id: str) -> None:
        self._active_threads.pop(session_id, None)

    async def pop_thread(self, session_id: str) -> Optional[ConversationThread]:
        return await self.get_stack(session_id).pop()

    async def on_barge_in(self, session_id: str, partial_tts_state=None) -> None:
        thread = self._active_threads.get(session_id)
        if not thread:
            # Create a placeholder thread if there wasn't one active
            thread = ConversationThread(
                topic="general",
                original_question=""
            )

        if partial_tts_state:
            thread.spoken_sentences = getattr(partial_tts_state, "completed_sentences", thread.spoken_sentences)
            thread.cut_sentence = getattr(partial_tts_state, "in_flight_sentence", thread.cut_sentence)
            thread.cut_char_offset = getattr(partial_tts_state, "char_offset", thread.cut_char_offset)
            thread.remaining_plan = getattr(partial_tts_state, "unflushed_sentences", thread.remaining_plan)
        else:
            # Estimate character offset in the cut sentence
            if thread.cut_sentence and getattr(thread, "last_sent_time", None):
                elapsed = time.time() - thread.last_sent_time
                thread.cut_char_offset = min(len(thread.cut_sentence), int(elapsed * 15))

        # Push to stack
        await self.get_stack(session_id).push(thread)
        self._active_threads.pop(session_id, None)

        logger.info(
            "[INTERRUPT] on_barge_in completed. Thread pushed to stack for session %s (topic=%r).",
            session_id, thread.topic
        )

    async def generate_resume_bridge(self, thread: ConversationThread) -> str:
        last_sentence = thread.spoken_sentences[-1] if thread.spoken_sentences else thread.original_question
        
        # Clean any HTML/Markdown tags from the last sentence for a cleaner prompt
        import re
        last_sentence_clean = re.sub(r"<[^>]+>", "", last_sentence).strip()
        
        prompt = RESUME_BRIDGE_SYSTEM_PROMPT.format(
            topic=thread.topic,
            last_sentence=last_sentence_clean,
            interruption_summary=thread.interruption_summary or "a quick side question",
        )
        
        try:
            import httpx
            from config import Config
            
            payload = {
                "model": Config.LLM_MODEL_NAME,
                "messages": [
                    {"role": "system", "content": prompt}
                ],
                "stream":      False,
                "max_tokens":  40,
                "temperature": 0.6,
            }
            
            async with httpx.AsyncClient(
                base_url=Config.LLM_BASE_URL,
                timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
                headers={"Content-Type": "application/json"},
            ) as client:
                response = await client.post("/v1/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    bridge = choices[0].get("message", {}).get("content", "").strip()
                    # Clean up quotes if returned
                    bridge = bridge.strip('"\'')
                    return bridge
        except Exception as e:
            logger.error("Failed to generate resume bridge via LLM: %s", e)
            
        # Fallback if LLM call fails
        return f"Alright, let's get back to {thread.topic}."

    # Legacy compatibility methods
    def save_state(
        self,
        session_id: str,
        partial_response: str,
        topic: str,
        total_response_chars: int = 0,
    ) -> None:
        # Keep legacy compatibility by executing on_barge_in synchronously
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.on_barge_in(session_id))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.on_barge_in(session_id))

    def get_state(self, session_id: str) -> Optional[InterruptState]:
        return None

    def clear_state(self, session_id: str) -> None:
        pass

    def was_interrupted(self, session_id: str) -> bool:
        return False

    def track_chars_sent(self, session_id: str, chars: int) -> None:
        pass

    def reset_turn(self, session_id: str) -> None:
        pass

    def clear_session(self, session_id: str) -> None:
        self._active_threads.pop(session_id, None)
        # Clear stack
        key = f"interrupt_stack:{session_id}"
        self._store.pop(key, None)
