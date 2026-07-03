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
from agent.access_control import AccessControl

logger = logging.getLogger("edumentor.agent.controller")

# ─────────────────────────────────────────────────────────────────────────────
# Structured agent logger (separate from the main pipeline logger)
# ─────────────────────────────────────────────────────────────────────────────

agent_logger = logging.getLogger("edumentor.agent.events")


def get_max_tokens_for_intent(user_text: str, intent: Intent) -> int:
    query = user_text.lower()
    needs_silent = (
        intent in (Intent.CODE_HELP, Intent.DEBUGGING) or
        any(w in query for w in ("code", "write", "implement", "script", "program", "function", "class")) or
        any(w in query for w in ("roadmap", "workflow", "diagram", "table", "checklist", "comparison", "list"))
    )
    if needs_silent:
        return 512  # Raise token ceiling for visual/code requests
    return 150      # Keep voice-only or short replies compact and fast


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

        # Prompt Injection Detection — comprehensive patterns
        injection_patterns = [
            # Classic instruction override
            r"ignore\s+(?:all\s+|your\s+)?(?:previous\s+|prior\s+)?instructions",
            r"disregard\s+(?:all\s+|your\s+)?(?:previous\s+|prior\s+)?instructions",
            r"forget\s+(?:all\s+|your\s+)?(?:previous\s+|prior\s+)?instructions",
            r"override\s+(?:all\s+|your\s+)?(?:previous\s+|prior\s+)?instructions",
            r"bypass\s+(?:all\s+|your\s+)?(?:previous\s+|prior\s+)?(?:instructions|rules|guidelines|filters|safety)",
            # Identity hijacking
            r"you\s+are\s+now\s+(?:a\s+|an\s+)?(?!EduMentor)",
            r"pretend\s+(?:you\s+are|to\s+be)\s+(?!EduMentor)",
            r"act\s+as\s+(?:a\s+|an\s+)?(?!EduMentor|a\s+tutor|a\s+teacher)",
            r"roleplay\s+as",
            r"from\s+now\s+on\s+you\s+are",
            r"switch\s+(?:to|into)\s+(?:a\s+|an\s+)?(?:new|different)\s+(?:mode|persona|role)",
            # System prompt extraction
            r"new\s+system\s+prompt",
            r"system:\s*(?:you\s+are|ignore)",
            r"reveal\s+(?:your\s+)?system\s+prompt",
            r"show\s+(?:your\s+)?system\s+prompt",
            r"what\s+is\s+(?:your\s+)?system\s+prompt",
            r"output\s+(?:your\s+)?system\s+prompt",
            r"print\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions)",
            r"repeat\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions)\s+(?:back|verbatim)",
            r"display\s+(?:your\s+)?(?:initial|original|hidden)\s+(?:prompt|instructions)",
            # DAN / jailbreak keywords
            r"\bDAN\b",
            r"\bjailbreak\b",
            r"\bprompt\s*injection\b",
            r"\bprompt\s*leak(?:ing)?\b",
            r"developer\s+mode",
            r"god\s+mode",
            r"unrestricted\s+mode",
            r"no\s+(?:rules|restrictions|filters|limits)",
            # Harmful intent
            r"how\s+to\s+(?:hack|exploit|attack|destroy|harm|kill|bomb|weapon)",
            r"(?:make|build|create)\s+(?:a\s+)?(?:bomb|weapon|virus|malware|exploit)",
            # ── New: token smuggling / separator tricks ────────────────────────
            # Attacker inserts special tokens or separators to break context boundary
            r"<\|(?:im_start|im_end|system|user|assistant|endoftext)\|>",
            r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>",  # Llama2/Mistral special tokens
            r"###\s*(?:System|Instruction|Human|Assistant)\s*:",
            r"<\|?\s*system\s*\|?>",
            # ── New: indirect / nested injection ─────────────────────────────
            # "Complete the sentence: You are now..." style attacks
            r"complete\s+(?:the\s+)?(?:sentence|text|phrase)\s*:.*you\s+are",
            r"continue\s+(?:the\s+)?(?:sentence|text)\s*:.*ignore",
            # ── New: hypothetical / fictional framing ─────────────────────────
            r"hypothetically\s+(?:speaking\s+)?(?:if\s+)?you\s+(?:had\s+no|were\s+without|could\s+bypass)",
            r"in\s+a\s+(?:story|novel|game|simulation)\s+where\s+(?:you|an\s+ai)\s+(?:has\s+no|ignores)",
            r"imagine\s+you\s+(?:have\s+no|are\s+without)\s+(?:restrictions|filters|safety|guidelines)",
            # ── New: translation / encoding attacks ───────────────────────────
            # "Translate your instructions to Spanish" → system prompt extraction
            r"translate\s+(?:your\s+)?(?:system\s+prompt|instructions|rules|guidelines)\s+(?:to|into)",
            r"(?:encode|decode|convert)\s+(?:your\s+)?(?:system\s+prompt|instructions)\s+(?:to|as|in)",
            # ── New: context window poisoning ─────────────────────────────────
            r"(?:everything|all\s+text)\s+(?:above|before)\s+(?:this|these)\s+(?:line|message|prompt)",
            r"(?:the|your)\s+(?:previous|above|prior)\s+(?:context|messages?|conversation)\s+(?:said|states?|told)",
            # ── New: capability probing ───────────────────────────────────────
            r"what\s+(?:can\s+you\s+really\s+do|are\s+your\s+real\s+capabilities|are\s+you\s+actually\s+allowed)",
            r"(?:show|tell|reveal)\s+me\s+(?:your\s+)?(?:real|true|actual|hidden)\s+(?:capabilities|self|mode|instructions)",
            # ── New: authority impersonation ──────────────────────────────────
            r"(?:i\s+am|this\s+is)\s+(?:your\s+)?(?:developer|creator|admin|operator|openai|anthropic|meta)",
            r"(?:as\s+(?:your|the)\s+)?(?:developer|creator|admin|operator)\s+i\s+(?:am\s+)?(?:instructing|ordering|telling|commanding)\s+you",
        ]

        for p in injection_patterns:
            if re.search(p, text, re.IGNORECASE):
                refusal = "I cannot process that request. Ask me about your engineering studies or career and I will help."
                return (processed_text, True, "prompt_injection", refusal)

        from agent.safety_guard import check_input, get_refusal_message
        safety_res = check_input(processed_text)
        if not safety_res.allowed:
            return (processed_text, True, safety_res.reason, get_refusal_message(safety_res))

        return (processed_text, False, None, None)

    def _run_post_guardrail(self, raw_response: str) -> tuple[str, bool, bool, Optional[str], Optional[str]]:
        import re
        from agent.safety_guard import check_output as check_output_guard

        processed_response = raw_response
        output_flagged = False

        # Tag leak detection (only matches incomplete/cut-off tag fragments)
        tag_leak_pattern = re.compile(
            r"<spe\b(?!ak>)|<sho\b(?!w\b)|<fol\b(?!lowup>)|<s\b(?!peak>|how\b)|<f\b(?!ollowup>)",
            re.IGNORECASE
        )
        if tag_leak_pattern.search(raw_response):
            logger.warning("[SAFETY POST-LLM] Incomplete tag fragment detected: %r", raw_response)
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
        ip_address: Optional[str] = None,
        voice_style: Optional[str] = None,
    ) -> AsyncIterator[dict]:
        """
        Process a transcript and stream cleaned response tokens.
        """
        start_time = time.perf_counter()
        session_uuid = self._to_uuid(session_id)
        user_id = user_id or session_id
        user_uuid = self._to_uuid(user_id)
        ip_address = ip_address or "unknown"

        # ── STEP 0: Session ownership verification (LLM08) ───────────────────
        # This MUST be first — before safety checks, memory reads, or intent
        # classification, all of which touch per-student data.
        # Runs on EVERY request, not just at WebSocket connection time.
        db_pool = getattr(self._db_manager, "pool", None)
        session_owned = await AccessControl.verify_session_ownership(
            session_id, user_id, db_pool
        )
        if not session_owned:
            from agent.security_logger import log_security_event
            asyncio.create_task(log_security_event(
                user_id, ip_address, "session_ownership_violation",
                f"session {session_id!r} claimed by mismatched student_id {user_id!r}"
            ))
            refusal = (
                "Something's off with this session. "
                "Please refresh and try again."
            )
            async for token in self._stream_refusal(refusal, session_id):
                yield token
            return

        # Multi-turn jailbreak state tracking (Part 3C)
        from agent.safety_guard import multi_turn_tracker
        if multi_turn_tracker.check_escalation(session_id, user_text):
            from agent.security_logger import log_security_event
            await log_security_event(
                user_id, ip_address, "multi_turn_jailbreak_detected",
                f"escalation signals across last {multi_turn_tracker.window} turns"
            )
            multi_turn_tracker.clear_session(session_id)  # reset the window
            refusal = "Let's get back to engineering topics. What are you working on?"
            async for token in self._stream_refusal(refusal, session_id):
                yield token
            return

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
        _skip_db_log = False  # Set True for any blocked input — prevents history poisoning

        # Redact PII in user input (existing logic)
        from agent.safety_guard import EMAIL_RE, AADHAAR_RE, PHONE_RE, SSN_RE
        pii_flagged = False
        original_text = user_text
        if EMAIL_RE.search(original_text) or AADHAAR_RE.search(original_text) or PHONE_RE.search(original_text) or SSN_RE.search(original_text):
            pii_flagged = True

        processed_text = original_text
        processed_text = EMAIL_RE.sub("[redacted]", processed_text)
        processed_text = AADHAAR_RE.sub("[redacted]", processed_text)
        processed_text = PHONE_RE.sub("[redacted]", processed_text)
        processed_text = SSN_RE.sub("[redacted]", processed_text)

        if pii_flagged:
            from agent.security_logger import log_security_event
            asyncio.create_task(log_security_event(user_id, ip_address, "pii_detected", "PII detected and redacted in user input"))

        # 1. Safety check on input (existing + Component 3 hardening)
        if self._safety_enabled:
            try:
                import inspect
                func = self._run_pre_guardrail
                if inspect.iscoroutinefunction(func):
                    coro = func(processed_text)
                else:
                    coro = asyncio.to_thread(func, processed_text)
                processed_text, pre_blocked, pre_reason, pre_refusal = await asyncio.wait_for(
                    coro,
                    timeout=0.2
                )
                if pre_blocked:
                    input_flagged = True
                    flag_reason = pre_reason
                    refusal_message = pre_refusal
            except asyncio.TimeoutError:
                logger.warning("[SAFETY PRE-LLM] Timeout (200ms) exceeded. Failing open.")
                input_flagged = True
                flag_reason = "timeout"
            except Exception as pre_exc:
                logger.error("Pre-LLM safety guardrail error: %s", pre_exc)

            if input_flagged and flag_reason != "timeout":
                from agent.security_logger import log_security_event
                from agent.rate_limiter import rate_limiter
                from agent.safety_guard import DB_DISCARD_CATEGORIES

                asyncio.create_task(log_security_event(
                    user_id, ip_address, "jailbreak_attempt", flag_reason or "unsafe_input"
                ))

                violation_count = rate_limiter.record_violation(user_id)
                if violation_count >= 3:
                    rate_limiter.apply_strict_limit(user_id, duration_seconds=3600)
                    asyncio.create_task(log_security_event(
                        user_id, ip_address, "repeated_violation",
                        f"{violation_count} violations in 10 min"
                    ))

                # Mark as must-not-log: prompt injections and jailbreak attempts
                # must never enter conversation_logs or memory (history poisoning).
                if flag_reason in DB_DISCARD_CATEGORIES or flag_reason == "prompt_injection":
                    _skip_db_log = True

                async for token in self._stream_refusal(refusal_message, session_id):
                    yield token
                # ── DO NOT write to conversation_logs ─────────────────────────
                # Storing jailbreak/injection attempts in history would:
                #   1. Pollute the student's conversation context and memory
                #   2. Allow the injected text to resurface in future prompts
                #      (history poisoning via the memory manager)
                #   3. Create a record that could be replayed in RAG retrieval
                # Security event is already logged via log_security_event() above.
                return
        # 2. Non-Latin / off-topic routing (Component 3)
        from agent.safety_guard import get_non_latin_ratio
        non_latin_ratio = get_non_latin_ratio(processed_text)
        intent_result = await self._intent_classifier.classify(processed_text)

        if non_latin_ratio > 0.4 and intent_result.intent == Intent.OFF_TOPIC:
            from agent.security_logger import log_security_event
            asyncio.create_task(log_security_event(
                user_id, ip_address, "jailbreak_attempt",
                f"Non-Latin script ratio {non_latin_ratio:.2f} with off-topic intent"
            ))
            # Route to manual review: flag and block
            refusal_message = "I noticed something unusual in that message. Let me flag this for review and get back to you."
            # Blocked input — do NOT store in DB to prevent history poisoning
            async for token in self._stream_refusal(refusal_message, session_id):
                yield token
            return
        # 3. Token budget check (Component 4) — before context assembly
        from agent.token_budget import token_budget
        if not token_budget.check_daily_budget(user_id):
            from agent.security_logger import log_security_event
            asyncio.create_task(log_security_event(
                user_id, ip_address, "daily_limit_hit", "Daily token budget exceeded"
            ))
            refusal_message = "You've used up your question budget for today. Come back tomorrow or ask your instructor about extending it."
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            asyncio.create_task(
                self._db_manager.write_log(
                    user_id=user_uuid,
                    session_id=session_uuid,
                    query_text=original_text,
                    response_text=refusal_message,
                    intent_category="UNSAFE",
                    input_flagged=True,
                    output_flagged=False,
                    flag_reason="daily_token_budget_exceeded",
                    latency_ms=latency_ms
                )
            )
            async for token in self._stream_refusal(refusal_message, session_id):
                yield token
            return

        # Get context string and enforce limit
        context_str = self._memory.get_context(session_id)
        enforced_context_str = token_budget.enforce_context_limit(context_str)

        # Retrieve history messages
        history_messages = []
        db_rows = await self._db_manager.fetch_history(user_uuid, session_id=session_uuid, limit=10)
        db_rows_reversed = list(reversed(db_rows))
        for r in db_rows_reversed:
            history_messages.append({"role": "user", "content": r["query_text"]})
            history_messages.append({"role": "assistant", "content": r["response_text"]})

        # Assemble dialogue context and prompt
        profile = self._profile_manager.get_profile()
        session_summary = self._summarizer.get_summary(session_id)
        knowledge_route = self._knowledge_router.route(intent_result.intent, processed_text)

        retrieved_docs = None
        if knowledge_route.use_rag:
            retrieved_docs = self._knowledge_router.retrieve(knowledge_route, processed_text)

        audio_emotion = None
        if audio_array is not None:
            try:
                from speech.emotion import detect_audio_emotion
                audio_emotion = detect_audio_emotion(audio_array, processed_text)
            except Exception as exc:
                logger.warning("Failed to detect audio emotion: %s", exc)

        context_obj = self._dialogue_manager.build_context(
            session_id      = session_id,
            user_text       = processed_text,
            intent_result   = intent_result,
            history         = self._memory.get_session(session_id),
            session_summary = session_summary,
            profile         = profile,
            knowledge_route = knowledge_route,
            retrieved_docs  = retrieved_docs,
            audio_emotion   = audio_emotion,
            voice_style     = voice_style,
        )
        context_obj.history_messages = history_messages
        messages = self._prompt_builder.build_messages(context_obj)

        # Truncate prompt context if total tokens exceeds budget by popping oldest turns
        while len(history_messages) > 3:
            msg_text = "\n".join(m["content"] for m in messages)
            total_est_tokens = token_budget.estimate_tokens(msg_text)
            if total_est_tokens <= token_budget.MAX_CONTEXT_TOKENS:
                break
            history_messages.pop(0)
            context_obj.history_messages = history_messages
            messages = self._prompt_builder.build_messages(context_obj)

        emotion_result = context_obj.emotion
        topic = self._dialogue_manager.get_topic_from_history(self._memory.get_session(session_id)) or processed_text[:50]
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

        # 4. LLM call through circuit breaker (Component 5) & 5. Streaming PII filter (Component 6)
        from agent.safety_guard import StreamingPIIFilter
        pii_filter = StreamingPIIFilter()
        
        from agent.realtime_parser import RealtimeStreamingParser
        parser = RealtimeStreamingParser()
        
        full_raw_response_list = []
        is_blocked = False

        try:
            # We call the wrapped LLM engine which implements CircuitBreaker internally.
            # session_id is forwarded so the engine pins this request to a deterministic
            # KV cache slot, ensuring the cached system-prompt prefix accumulates across
            # turns instead of being scattered or evicted by other sessions.
            max_tokens = get_max_tokens_for_intent(processed_text, intent_result.intent)
            async for raw_token in self._llm.stream_tokens_from_messages(
                messages, session_id=session_id, max_tokens=max_tokens
            ):
                full_raw_response_list.append(raw_token)
                
                # Filter PII across token boundaries
                safe_text = pii_filter.process_token(raw_token)
                if safe_text:
                    for event in parser.feed(safe_text):
                        raw_chunk = event["raw"]
                        planned_chunk = event["planned"]
                        followup_chunk = event.get("followup", "")
                        
                        if raw_chunk or planned_chunk or followup_chunk:
                            self._turn_state[session_id]["partial_response"] += raw_chunk
                            self._interrupt.track_chars_sent(session_id, len(raw_chunk))
                            cleaned_planned = self._response_planner._clean_token(planned_chunk) if planned_chunk else ""
                            yield {"raw": raw_chunk, "planned": cleaned_planned, "followup": followup_chunk}
        except Exception as exc:
            logger.exception("LLM generation error in controller: %s", exc)
            err_msg = f"I encountered an error while processing your request: {exc}. Please try again."
            yield {"raw": err_msg, "planned": err_msg}

        # Flush the PII filter
        final_safe = pii_filter.flush()
        if final_safe:
            for event in parser.feed(final_safe):
                raw_chunk = event["raw"]
                planned_chunk = event["planned"]
                followup_chunk = event.get("followup", "")
                if raw_chunk or planned_chunk or followup_chunk:
                    self._turn_state[session_id]["partial_response"] += raw_chunk
                    self._interrupt.track_chars_sent(session_id, len(raw_chunk))
                    cleaned_planned = self._response_planner._clean_token(planned_chunk) if planned_chunk else ""
                    yield {"raw": raw_chunk, "planned": cleaned_planned, "followup": followup_chunk}
            
        # Finalize the parser
        for event in parser.finalize():
            raw_chunk = event["raw"]
            planned_chunk = event["planned"]
            followup_chunk = event.get("followup", "")
            if raw_chunk or planned_chunk or followup_chunk:
                self._turn_state[session_id]["partial_response"] += raw_chunk
                self._interrupt.track_chars_sent(session_id, len(raw_chunk))
                cleaned_planned = self._response_planner._clean_token(planned_chunk) if planned_chunk else ""
                yield {"raw": raw_chunk, "planned": cleaned_planned, "followup": followup_chunk}

        full_raw_response = "".join(full_raw_response_list)
        post_processed_response = full_raw_response

        # Check if PII was redacted in output
        from agent.safety_guard import redact_pii
        if redact_pii(full_raw_response) != full_raw_response:
            from agent.security_logger import log_security_event
            asyncio.create_task(log_security_event(user_id, ip_address, "pii_detected", "PII detected and redacted in LLM response"))

        # 6. Record token usage (Component 4)
        prompt_tokens = 0
        completion_tokens = 0
        last_usage = getattr(self._llm, "last_usage", None)
        if last_usage:
            prompt_tokens = last_usage.get("prompt_tokens", 0)
            completion_tokens = last_usage.get("completion_tokens", 0)
        else:
            # Fallback estimation
            prompt_tokens = token_budget.estimate_tokens("\n".join(m["content"] for m in messages))
            completion_tokens = token_budget.estimate_tokens(full_raw_response)
        token_budget.record_usage(user_id, prompt_tokens, completion_tokens)

        # 7. Hedging check on full assembled response (Component 6)
        from agent.safety_guard import check_hedging, check_output_for_system_leak
        hedge_reason = check_hedging(full_raw_response)
        if hedge_reason:
            asyncio.create_task(
                self._db_manager.log_low_confidence_response(
                    student_id=user_id,
                    session_id=session_id,
                    response_text=full_raw_response,
                    matched_hedging=hedge_reason
                )
            )

        # 7b. Output-stage system prompt leak detection (LLM07)
        # Catches system config extraction regardless of how the input was crafted:
        # roleplay, translation, hypothetical, or direct ask all land here.
        if self._safety_enabled and check_output_for_system_leak(full_raw_response):
            from agent.security_logger import log_security_event
            asyncio.create_task(log_security_event(
                user_id, ip_address, "system_leak_attempt",
                f"input preview: {user_text[:200]!r}"
            ))
            leak_refusal = (
                "<speak>I am Edi, your AI engineering mentor at EduMentor. "
                "Let's get back to what you're working on.</speak>"
                "<followup>What engineering topic would you like to explore?</followup>"
            )
            yield {"raw": leak_refusal, "planned": leak_refusal}
            # Log the blocked turn and return — do not continue to post-guardrail
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            asyncio.create_task(
                self._db_manager.write_log(
                    user_id=user_uuid,
                    session_id=session_uuid,
                    query_text=processed_text,
                    response_text=leak_refusal,
                    intent_category="UNSAFE",
                    input_flagged=False,
                    output_flagged=True,
                    flag_reason="system_leak_detected",
                    latency_ms=latency_ms
                )
            )
            return

        # Post-LLM safety checks (existing guardrail compliance)
        try:
            if self._safety_enabled:
                import inspect
                func = self._run_post_guardrail
                if inspect.iscoroutinefunction(func):
                    coro = func(full_raw_response)
                else:
                    coro = asyncio.to_thread(func, full_raw_response)
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
            logger.warning("[SAFETY POST-LLM] Timeout (200ms) exceeded. Failing closed.")
            is_blocked = True
            flag_reason = "timeout"
            refusal_message = "I'm not able to help with that particular request. Is there something about programming or computer science I can help you learn?"
        except Exception as safety_exc:
            logger.error("Post-LLM safety guardrail error: %s", safety_exc)

        if is_blocked and refusal_message:
            post_processed_response = refusal_message
            yield {"raw": refusal_message, "planned": refusal_message}

        # Save memory for local tracking components.
        # Skip for blocked inputs — injected text must never enter the memory
        # window where it could be included in future LLM context.
        if not _skip_db_log:
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

        # Log turns to database — skip entirely for blocked/jailbreak inputs to
        # prevent history poisoning (injected text never enters conversation_logs).
        if not log_written and not _skip_db_log:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            asyncio.create_task(
                self._db_manager.write_log(
                    user_id=user_uuid,
                    session_id=session_uuid,
                    query_text=processed_text,
                    response_text=post_processed_response,
                    intent_category=intent_result.intent.value,
                    input_flagged=input_flagged,
                    output_flagged=output_flagged or is_blocked,
                    flag_reason=flag_reason,
                    latency_ms=latency_ms
                )
            )
            
            # Increment session stats asynchronously (Part 2)
            active_topic = "General"
            if self._profile_manager:
                active_topic = self._profile_manager.get_active_topic(str(user_uuid))
            
            # Heuristic to detect if turn is self-initiated
            is_self_initiated = True
            if self._memory:
                history = self._memory.get_session(session_id)
                if history:
                    last_turn = history[-1]
                    if last_turn and last_turn.assistant:
                        assistant_text = last_turn.assistant
                        if "<followup>" in assistant_text or "{followup}" in assistant_text:
                            if len(processed_text.split()) < 8 and "?" not in processed_text:
                                is_self_initiated = False

            # Map active topic to discipline category (cse, mech, eee, civil, chemical, aerospace)
            from agent.student_profile import TOPIC_TO_DISCIPLINE
            discipline = TOPIC_TO_DISCIPLINE.get(active_topic, "cse")
            if discipline == "ece":
                discipline = "eee"

            if hasattr(self._db_manager, "increment_session_stats"):
                asyncio.create_task(
                    self._db_manager.increment_session_stats(
                        user_id=user_uuid,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        discipline=discipline,
                        intent=intent_result.intent.value,
                        active_topic=active_topic,
                        query_text=processed_text,
                        is_self_initiated=is_self_initiated,
                        input_flagged=input_flagged,
                        output_flagged=output_flagged or is_blocked
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
