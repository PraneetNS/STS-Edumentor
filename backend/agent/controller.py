"""
EduMentor Agent Layer — Agent Controller

The central orchestrator of the entire agent pipeline.
This is the SINGLE ENTRY POINT that main.py calls instead of
calling LLMEngine.stream_tokens() directly.

Full pipeline (in order):
  1.  receive(transcript, session_id)
  2.  input_safety_check()        → block if UNSAFE
  3.  classify_intent()           → IntentResult
  4.  retrieve_memory()           → list[MemoryTurn]
  5.  retrieve_profile()          → StudentProfile
  6.  get_session_summary()       → SessionSummary | None
  7.  route_knowledge()           → KnowledgeRoute
  8.  retrieve_documents()        → str | None (if RAG)
  9.  build_dialogue_context()    → AgentContext
  10. build_prompt()              → messages list
  11. stream_llm()                → AsyncIterator[str] (existing LLMEngine unchanged)
  12. plan_response() per token   → cleaned tokens
  13. output_safety_check()       → filter if needed
  14. save_memory()               → update MemoryManager
  15. update_profile()            → update StudentProfile
  16. return AgentResponse + token stream

All dependencies are injected at construction time (no global state).
The controller is stateless between turns (session state lives in MemoryManager).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Dict, List, Optional
import numpy as np

from agent.dialogue_manager import DialogueManager
from agent.emotion_detector import detect as detect_emotion
from agent.intent_classifier import IntentClassifier
from agent.interrupt_manager import InterruptManager
from agent.knowledge_router import KnowledgeRouter
from agent.memory_manager import MemoryManager
from agent.models import (
    AgentContext,
    AgentResponse,
    Emotion,
    Intent,
    IntentResult,
)
from agent.prompt_builder import PromptBuilder
from agent.response_planner import ResponsePlanner
from agent.safety_guard import check_input, check_output, get_refusal_message
from agent.session_summarizer import SessionSummarizer
from agent.student_profile import StudentProfileManager

logger = logging.getLogger("edumentor.agent.controller")

# ─────────────────────────────────────────────────────────────────────────────
# Structured agent logger (separate from the main pipeline logger)
# ─────────────────────────────────────────────────────────────────────────────

agent_logger = logging.getLogger("edumentor.agent.events")


class AgentController:
    """
    Central orchestrator for the EduMentor agentic pipeline.

    One instance lives for the lifetime of the FastAPI server.
    It is stateless itself — all session state is managed by the
    injected MemoryManager and InterruptManager.

    Args:
        llm_engine:          The existing LLMEngine from main.py.
        memory_manager:      Manages conversation history.
        session_summarizer:  Generates rolling session summaries.
        profile_manager:     Loads/saves student profile.
        interrupt_manager:   Manages interruption state.
        intent_enabled:      If False, skip intent classification (faster).
        safety_enabled:      If False, skip safety checks (not recommended).
    """

    def __init__(
        self,
        llm_engine,
        memory_manager: MemoryManager,
        session_summarizer: SessionSummarizer,
        profile_manager: StudentProfileManager,
        interrupt_manager: InterruptManager,
        intent_enabled: bool = True,
        safety_enabled: bool = True,
    ) -> None:
        self._llm             = llm_engine
        self._memory          = memory_manager
        self._summarizer      = session_summarizer
        self._profile_manager = profile_manager
        self._interrupt       = interrupt_manager
        self._safety_enabled  = safety_enabled

        # Inject summarizer into memory manager (circular dep resolved here)
        self._memory.set_summarizer(session_summarizer)

        # Build sub-components
        self._intent_classifier = IntentClassifier(llm_engine, enabled=intent_enabled)
        self._dialogue_manager  = DialogueManager(interrupt_manager)
        self._prompt_builder    = PromptBuilder()
        self._response_planner  = ResponsePlanner()
        self._knowledge_router  = KnowledgeRouter()

        # Per-session turn tracking (for interrupt state and logging)
        # session_id → {"last_topic": str, "partial_response": str, "start_time": float}
        self._turn_state: Dict[str, Dict] = {}

        logger.info(
            "[OK] AgentController ready. intent_enabled=%s safety_enabled=%s",
            intent_enabled, safety_enabled
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public: streaming interface (used by main.py)
    # ─────────────────────────────────────────────────────────────────────────

    async def stream(
        self,
        user_text: str,
        session_id: str,
        audio_array: Optional[np.ndarray] = None,
    ) -> AsyncIterator[str]:
        """
        Process a transcript and stream cleaned response tokens.

        This is the primary method called by main.py's _stream_llm_and_tts().
        It replaces the direct llm_engine.stream_tokens() call.

        The returned async iterator yields cleaned, TTS-ready token strings.
        The full pipeline runs before the first token is yielded.

        Args:
            user_text:  The transcribed student speech.
            session_id: The WebSocket session identifier.
            audio_array: Optional raw user speech audio.

        Yields:
            Cleaned token strings for TTS and frontend display.
        """
        start_time = time.perf_counter()

        # Initialize turn tracking
        self._turn_state[session_id] = {
            "last_topic":       "general",
            "partial_response": "",
            "start_time":       start_time,
        }

        # Reset interrupt tracking for new turn
        self._interrupt.reset_turn(session_id)

        # Reset response planner for new turn
        self._response_planner.reset()

        # ── Step 1: Input Safety ─────────────────────────────────────────────
        if self._safety_enabled:
            safety_result = check_input(user_text)
            if not safety_result.allowed:
                refusal = get_refusal_message(safety_result)
                agent_logger.warning(
                    "SAFETY_BLOCK session=%s reason=%s text=%r",
                    session_id, safety_result.reason, user_text[:60]
                )
                async for token in self._stream_refusal(refusal, session_id):
                    yield token
                return

        # ── Step 2: Intent Classification ────────────────────────────────────
        intent_result: IntentResult = await self._intent_classifier.classify(user_text)

        # ── Step 3: Retrieve Memory ───────────────────────────────────────────
        full_history = self._memory.get_session(session_id)

        # ── Step 4: Retrieve Profile ──────────────────────────────────────────
        profile = self._profile_manager.get_profile()

        # ── Step 5: Get Session Summary ───────────────────────────────────────
        session_summary = self._summarizer.get_summary(session_id)

        # ── Step 6: Knowledge Routing ─────────────────────────────────────────
        knowledge_route = self._knowledge_router.route(intent_result.intent, user_text)

        # ── Step 7: Document Retrieval (if needed) ────────────────────────────
        retrieved_docs: Optional[str] = None
        if knowledge_route.use_rag:
            retrieved_docs = self._knowledge_router.retrieve(knowledge_route, user_text)

        # ── Step 7.5: Detect audio emotion ────────────────────────────────────
        audio_emotion = None
        if audio_array is not None:
            try:
                from speech.emotion import detect_audio_emotion
                audio_emotion = detect_audio_emotion(audio_array, user_text)
            except Exception as exc:
                logger.warning("Failed to detect audio emotion: %s", exc)

        # ── Step 8: Build Dialogue Context ────────────────────────────────────
        context: AgentContext = self._dialogue_manager.build_context(
            session_id      = session_id,
            user_text       = user_text,
            intent_result   = intent_result,
            history         = full_history,
            session_summary = session_summary,
            profile         = profile,
            knowledge_route = knowledge_route,
            retrieved_docs  = retrieved_docs,
            audio_emotion   = audio_emotion,
        )

        # ── Step 9: Build Prompt ──────────────────────────────────────────────
        messages = self._prompt_builder.build_messages(context)

        # ── Step 10: Detect emotion (for profile update later) ────────────────
        emotion_result = context.emotion

        # Update turn state with detected topic (used by interrupt handler)
        topic = self._dialogue_manager.get_topic_from_history(full_history) or user_text[:50]
        self._turn_state[session_id]["last_topic"] = topic

        latency_ms = (time.perf_counter() - start_time) * 1000
        agent_logger.info(
            "TURN_START session=%s intent=%s emotion=%s rag=%s latency_ms=%.0f",
            session_id,
            intent_result.intent.value,
            emotion_result.emotion.value,
            knowledge_route.use_rag,
            latency_ms,
        )

        # ── Step 11 + 12: Stream LLM + Plan Response ──────────────────────────
        full_raw_parts: List[str] = []
        full_planned_parts: List[str] = []
        output_blocked = False

        try:
            async for raw_token in self._llm.stream_tokens_from_messages(messages):
                # Track partial response for interrupt save
                self._turn_state[session_id]["partial_response"] += raw_token

                # Track chars sent (for interrupt fraction calculation)
                self._interrupt.track_chars_sent(session_id, len(raw_token))

                # ── Step 12: Response planning (clean for TTS) ────────────────
                planned_token = self._response_planner.process_token(raw_token)

                # ── Step 13: Output Safety (lightweight — just token-level) ───
                if self._safety_enabled and full_planned_parts:
                    # Check accumulated response every 50 tokens
                    accumulated = "".join(full_planned_parts)
                    if len(accumulated) % 200 < len(planned_token or ""):
                        out_safety = check_output(accumulated)
                        if not out_safety.allowed:
                            output_blocked = True
                            agent_logger.warning(
                                "OUTPUT_BLOCK session=%s reason=%s",
                                session_id, out_safety.reason
                            )
                            yield {
                                "raw": " I need to stop there. Let me try a different approach.",
                                "planned": " I need to stop there. Let me try a different approach."
                            }
                            break

                full_raw_parts.append(raw_token)
                if planned_token:
                    full_planned_parts.append(planned_token)
                
                yield {"raw": raw_token, "planned": planned_token or ""}

        except asyncio.CancelledError:
            logger.info(
                "[CONTROLLER] Stream cancelled for session=%s (interruption)",
                session_id
            )
            raise

        finally:
            # ── Step 14: Save to Memory ───────────────────────────────────────
            if not output_blocked:
                raw_response = "".join(full_raw_parts)
                if raw_response and user_text:
                    self._memory.add_turn(
                        session_id     = session_id,
                        user_text      = user_text,
                        assistant_text = raw_response,
                        intent         = intent_result.intent.value,
                        emotion        = emotion_result.emotion.value,
                    )

                    # ── Step 15: Update Profile ───────────────────────────────
                    self._profile_manager.update_from_turn(
                        user_text       = user_text,
                        assistant_text  = raw_response,
                        emotion         = emotion_result.emotion,
                    )

            total_ms = (time.perf_counter() - start_time) * 1000
            agent_logger.info(
                "TURN_END session=%s intent=%s response_chars=%d total_ms=%.0f",
                session_id,
                intent_result.intent.value,
                len("".join(full_raw_parts)),
                total_ms,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Interrupt state access (called from main.py's interrupt handler)
    # ─────────────────────────────────────────────────────────────────────────

    def get_current_topic(self, session_id: str) -> str:
        """
        Return the topic being discussed in the current turn.

        Called by main.py before saving interrupt state.
        """
        state = self._turn_state.get(session_id, {})
        return state.get("last_topic", "the current topic")

    def get_partial_response(self, session_id: str) -> str:
        """
        Return the LLM text generated so far in the current turn.

        Called by main.py to save interrupt state.
        """
        state = self._turn_state.get(session_id, {})
        return state.get("partial_response", "")

    def clear_turn_state(self, session_id: str) -> None:
        """Clear per-turn state on disconnect or reset."""
        self._turn_state.pop(session_id, None)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: safety refusal stream
    # ─────────────────────────────────────────────────────────────────────────

    async def _stream_refusal(
        self,
        refusal_text: str,
        session_id: str,
    ) -> AsyncIterator[dict]:
        """
        Stream a safety refusal message as individual word tokens.

        Yields dict with raw and planned fields so the existing TTS pipeline works correctly.
        """
        words = refusal_text.split()
        for i, word in enumerate(words):
            separator = " " if i > 0 else ""
            token = separator + word
            yield {"raw": token, "planned": token}
            # Small delay to simulate natural streaming (not required but looks better)
            await asyncio.sleep(0.005)
