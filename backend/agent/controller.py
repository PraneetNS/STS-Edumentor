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
import uuid
from typing import AsyncIterator, Dict, List, Optional
import numpy as np

from agent.database import DatabaseManager

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
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self._llm             = llm_engine
        self._memory          = memory_manager
        self._summarizer      = session_summarizer
        self._profile_manager = profile_manager
        self._interrupt       = interrupt_manager
        self._safety_enabled  = safety_enabled
        self._db_manager      = db_manager or DatabaseManager()

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

    def _to_uuid(self, val: str) -> uuid.UUID:
        if not val:
            return uuid.uuid4()
        try:
            return uuid.UUID(val)
        except ValueError:
            return uuid.uuid5(uuid.NAMESPACE_DNS, val)

    def _count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    def _run_pre_guardrail(self, text: str) -> tuple[str, bool, Optional[str], Optional[str]]:
        import re
        # PII Detection
        aadhaar_re = re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")
        email_re = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
        phone_re = re.compile(r"\+?\d{1,4}[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{3,4}[-.\s]?\d{4}")

        processed_text = text
        processed_text = email_re.sub("[redacted]", processed_text)
        processed_text = aadhaar_re.sub("[redacted]", processed_text)
        processed_text = phone_re.sub("[redacted]", processed_text)

        # Prompt Injection Detection
        injection_patterns = [
            r"ignore\s+(?:all\s+|your\s+)?(?:previous\s+|prior\s+)?instructions",
            r"disregard\s+(?:all\s+|your\s+)?(?:previous\s+|prior\s+)?instructions",
            r"forget\s+(?:all\s+|your\s+)?(?:previous\s+|prior\s+)?instructions",
            r"you\s+are\s+now\s+(?:a\s+|an\s+)?(?!EduMentor)",
            r"pretend\s+(?:you\s+are|to\s+be)\s+(?!EduMentor)",
            r"act\s+as\s+(?:a\s+|an\s+)?(?!EduMentor|a\s+tutor|a\s+teacher)",
            r"new\s+system\s+prompt",
            r"system:\s*(?:you\s+are|ignore)",
            r"reveal\s+(?:your\s+)?system\s+prompt",
            r"show\s+(?:your\s+)?system\s+prompt",
            r"what\s+is\s+(?:your\s+)?system\s+prompt",
            r"output\s+(?:your\s+)?system\s+prompt",
        ]

        for p in injection_patterns:
            if re.search(p, text, re.IGNORECASE):
                refusal = "I cannot process that request. Ask me about your engineering studies or career and I will help."
                return (processed_text, True, "prompt_injection", refusal)

        return (processed_text, False, None, None)

    def _run_post_guardrail(self, raw_response: str) -> tuple[str, bool, bool, Optional[str], Optional[str]]:
        import re
        from agent.safety_guard import check_output as check_output_guard

        processed_response = raw_response
        output_flagged = False

        # Tag leak detection
        tag_leak_pattern = re.compile(
            r"</?speak[^>]*>|</?show[^>]*>|</?followup[^>]*>|<speak|<show|<followup|<spe\b|<sho\b|<fol\b|<s\b|<f\b",
            re.IGNORECASE
        )
        if tag_leak_pattern.search(raw_response):
            logger.error("[PARSER BUG] Critical error: Raw tag leak detected in response: %r", raw_response)
            processed_response = tag_leak_pattern.sub("", processed_response)

        # Mentor voice compliance
        banned_fillers = [
            r"\bcertainly!\b",
            r"\bcertainly\b",
            r"\bgreat question!\b",
            r"\bgreat question\b",
            r"\bi'd be happy to\b",
            r"\bi would be happy to\b",
        ]
        for pattern in banned_fillers:
            if re.search(pattern, raw_response, re.IGNORECASE):
                logger.info("[SAFETY POST-LLM] Mentor voice non-compliance matched filler: %r", pattern)
                output_flagged = True

        # Safety check
        safety_result = check_output_guard(raw_response)
        if not safety_result.allowed:
            refusal = "I'm not able to help with that particular request. Is there something about programming or computer science I can help you learn?"
            return (processed_response, True, True, safety_result.reason, refusal)

        return (processed_response, False, output_flagged, None, None)

    async def stream(
        self,
        user_text: str,
        session_id: str,
        user_id: Optional[str] = None,
        audio_array: Optional[np.ndarray] = None,
    ) -> AsyncIterator[str]:
        """
        Process a transcript and stream cleaned response tokens.
        """
        start_time = time.perf_counter()
        session_uuid = self._to_uuid(session_id)
        user_uuid = self._to_uuid(user_id or session_id)

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

        log_written = False
        input_flagged = False
        output_flagged = False
        flag_reason = None
        refusal_message = None
        processed_text = user_text

        # ── Subsystem 2: Pre-LLM Guardrail ──────────────────────────────────
        if self._safety_enabled:
            try:
                import inspect
                func = self._run_pre_guardrail
                if inspect.iscoroutinefunction(func):
                    coro = func(user_text)
                else:
                    coro = asyncio.to_thread(func, user_text)
                processed_text, is_blocked, block_reason, refusal = await asyncio.wait_for(
                    coro,
                    timeout=0.2
                )
                if is_blocked:
                    input_flagged = True
                    flag_reason = block_reason
                    refusal_message = refusal
            except asyncio.TimeoutError:
                logger.warning("[SAFETY PRE-LLM] Timeout (200ms) exceeded. Failing open.")
                input_flagged = True
                flag_reason = "timeout"

            if refusal_message:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                asyncio.create_task(
                    self._db_manager.write_log(
                        user_id=user_uuid,
                        session_id=session_uuid,
                        query_text=processed_text,
                        response_text=refusal_message,
                        intent_category="UNSAFE",
                        input_flagged=True,
                        output_flagged=False,
                        flag_reason=flag_reason,
                        latency_ms=latency_ms
                    )
                )
                log_written = True
                async for token in self._stream_refusal(refusal_message, session_id):
                    yield token
                return

        # ── Subsystem 3: Rolling Context Memory ──────────────────────────────
        history_messages = []
        db_rows = await self._db_manager.fetch_history(user_uuid, limit=10)
        db_rows_reversed = list(reversed(db_rows))
        for r in db_rows_reversed:
            history_messages.append({"role": "user", "content": r["query_text"]})
            history_messages.append({"role": "assistant", "content": r["response_text"]})

        def get_total_tokens(msg_list: list) -> int:
            return sum(self._count_tokens(m["content"]) for m in msg_list)

        while get_total_tokens(history_messages) > 1500 and len(history_messages) > 3:
            history_messages.pop(0)

        # ── Intent Classification & RAG Routing ──────────────────────────────
        intent_result: IntentResult = await self._intent_classifier.classify(processed_text)
        full_history = self._memory.get_session(session_id)
        profile = self._profile_manager.get_profile()
        session_summary = self._summarizer.get_summary(session_id)
        knowledge_route = self._knowledge_router.route(intent_result.intent, processed_text)

        retrieved_docs: Optional[str] = None
        if knowledge_route.use_rag:
            retrieved_docs = self._knowledge_router.retrieve(knowledge_route, processed_text)

        audio_emotion = None
        if audio_array is not None:
            try:
                from speech.emotion import detect_audio_emotion
                audio_emotion = detect_audio_emotion(audio_array, processed_text)
            except Exception as exc:
                logger.warning("Failed to detect audio emotion: %s", exc)

        # ── Build Dialogue Context & Prompt ──────────────────────────────────
        context: AgentContext = self._dialogue_manager.build_context(
            session_id      = session_id,
            user_text       = processed_text,
            intent_result   = intent_result,
            history         = full_history,
            session_summary = session_summary,
            profile         = profile,
            knowledge_route = knowledge_route,
            retrieved_docs  = retrieved_docs,
            audio_emotion   = audio_emotion,
        )
        context.history_messages = history_messages
        messages = self._prompt_builder.build_messages(context)

        emotion_result = context.emotion
        topic = self._dialogue_manager.get_topic_from_history(full_history) or processed_text[:50]
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

        # ── Step 11: Call LLM (Retrieve full raw response) ──────────────────
        full_raw_response_list = []
        try:
            async for raw_token in self._llm.stream_tokens_from_messages(messages):
                full_raw_response_list.append(raw_token)
        except Exception as exc:
            logger.exception("LLM generation error: %s", exc)
            full_raw_response_list.append(f"[Error: {exc}]")

        raw_response = "".join(full_raw_response_list)
        post_processed_response = raw_response
        is_blocked = False

        # ── Subsystem 2: Post-LLM Guardrail ─────────────────────────────────
        if self._safety_enabled:
            try:
                import inspect
                func = self._run_post_guardrail
                if inspect.iscoroutinefunction(func):
                    coro = func(raw_response)
                else:
                    coro = asyncio.to_thread(func, raw_response)
                post_processed_response, blocked, flagged, reason, refusal = await asyncio.wait_for(
                    coro,
                    timeout=0.2
                )
                if blocked:
                    is_blocked = True
                    flag_reason = reason
                    refusal_message = refusal
                if flagged:
                    output_flagged = True
            except asyncio.TimeoutError:
                logger.error("[SAFETY POST-LLM] Timeout (200ms) exceeded. Failing closed.")
                is_blocked = True
                flag_reason = "timeout"
                refusal_message = "I'm not able to help with that particular request. Is there something about programming or computer science I can help you learn?"

            if is_blocked:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                asyncio.create_task(
                    self._db_manager.write_log(
                        user_id=user_uuid,
                        session_id=session_uuid,
                        query_text=processed_text,
                        response_text=refusal_message,
                        intent_category=intent_result.intent.value,
                        input_flagged=False,
                        output_flagged=True,
                        flag_reason=flag_reason,
                        latency_ms=latency_ms
                    )
                )
                log_written = True
                async for token in self._stream_refusal(refusal_message, session_id):
                    yield token
                return

        # ── Parse and Send to TTS and Frontend ──────────────────────────────
        cleaned_response = post_processed_response.strip()
        if (cleaned_response.startswith("{") and cleaned_response.endswith("}")) or '"speech":' in cleaned_response:
            try:
                import json
                import re
                json_match = re.search(r"\{.*?\}", cleaned_response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    speech_text = data.get("speech", "")
                    followup_text = data.get("followup", "")
                    
                    reconstructed = ""
                    if speech_text:
                        reconstructed += f"<speak>{speech_text}</speak>"
                    if followup_text and isinstance(followup_text, str) and followup_text.strip().lower() != "null":
                        reconstructed += f"<followup>{followup_text}</followup>"
                        
                    if reconstructed:
                        post_processed_response = reconstructed
                        logger.info("Successfully intercepted and parsed JSON LLM response: %r", data)
            except Exception as json_err:
                logger.warning("Failed to parse response as JSON: %s", json_err)

        from edmentor.confidence_router import StreamingDualParser
        parser = StreamingDualParser()
        events = parser.feed(post_processed_response)
        events += parser.finalize()

        reconstructed_raw = ""
        reconstructed_planned_raw = ""
        for event in events:
            if event["type"] == "text":
                reconstructed_raw += event["content"] + "\n\n"
                reconstructed_planned_raw += event["content"] + " "
            elif event["type"] == "show":
                show_type = event.get("show_type", "")
                lang = event.get("lang", "")
                content = event.get("content", "")
                if show_type == "code" or lang:
                    reconstructed_raw += f"```{lang or 'python'}\n{content}\n```\n\n"
                else:
                    reconstructed_raw += f"{content}\n\n"
            elif event["type"] == "followup":
                reconstructed_raw += event["content"] + "\n\n"
                reconstructed_planned_raw += event["content"] + " "
        
        reconstructed_raw = reconstructed_raw.strip()
        reconstructed_planned_raw = reconstructed_planned_raw.strip()

        # Fallback if no events parsed
        if not events:
            reconstructed_raw = post_processed_response
            reconstructed_planned_raw = post_processed_response

        # Clean planned response for Kokoro TTS
        reconstructed_planned = self._response_planner.plan(
            reconstructed_planned_raw,
            intent=intent_result.intent,
            profile=profile,
            add_comprehension_check=False
        )

        # Yield chunks of reconstructed raw and planned text
        chunk_size = 8
        i = 0
        j = 0
        try:
            while i < len(reconstructed_raw) or j < len(reconstructed_planned):
                raw_chunk = ""
                if i < len(reconstructed_raw):
                    raw_chunk = reconstructed_raw[i:i+chunk_size]
                    i += chunk_size
                planned_chunk = ""
                if j < len(reconstructed_planned):
                    planned_chunk = reconstructed_planned[j:j+chunk_size]
                    j += chunk_size

                self._turn_state[session_id]["partial_response"] += raw_chunk
                self._interrupt.track_chars_sent(session_id, len(raw_chunk))

                yield {"raw": raw_chunk, "planned": planned_chunk}
                await asyncio.sleep(0.002)
        finally:
            # Save memory for local tracking components
            self._memory.add_turn(
                session_id     = session_id,
                user_text      = processed_text,
                assistant_text = post_processed_response,
                intent         = intent_result.intent.value,
                emotion        = emotion_result.emotion.value,
            )

            self._profile_manager.update_from_turn(
                user_text       = processed_text,
                assistant_text  = post_processed_response,
                emotion         = emotion_result.emotion,
            )

            # ── Subsystem 1: Log turns to database ──────────────────────────
            if not log_written:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                asyncio.create_task(
                    self._db_manager.write_log(
                        user_id=user_uuid,
                        session_id=session_uuid,
                        query_text=processed_text,
                        response_text=post_processed_response,
                        intent_category=intent_result.intent.value,
                        input_flagged=input_flagged,
                        output_flagged=output_flagged,
                        flag_reason=flag_reason,
                        latency_ms=latency_ms
                    )
                )

            total_ms = (time.perf_counter() - start_time) * 1000
            agent_logger.info(
                "TURN_END session=%s intent=%s response_chars=%d total_ms=%.0f",
                session_id,
                intent_result.intent.value,
                len(post_processed_response),
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
