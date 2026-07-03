"""
EduMentor Agent Layer — Dialogue Manager

Assembles the complete AgentContext from all available signals:
  - Intent (from IntentClassifier)
  - Emotion (from EmotionDetector)
  - Memory (from MemoryManager)
  - Session summary (from SessionSummarizer)
  - Student profile (from StudentProfileManager)
  - Interruption state (from InterruptManager)
  - Knowledge route (from KnowledgeRouter)

The AgentContext is the single object passed to PromptBuilder —
nothing else needs to flow between components.

Design responsibilities:
  1. Read intent → decide how much history to inject
  2. Read emotion → set style modifiers
  3. Read profile → personalize tone/depth
  4. Read session summary → inject long-term context
  5. Check for interruption → set bridge flag
  6. Package everything into AgentContext

Pipeline position:
  AgentController → DialogueManager.build_context() → AgentContext → PromptBuilder
"""

from __future__ import annotations

import logging
from typing import List, Optional

from agent.emotion_detector import detect as detect_emotion, get_style_for_emotion
from agent.interrupt_manager import InterruptManager
from agent.models import (
    AgentContext,
    Emotion,
    EmotionResult,
    Intent,
    IntentResult,
    InterruptState,
    KnowledgeRoute,
    MemoryTurn,
    SessionSummary,
    StudentProfile,
)

logger = logging.getLogger("edumentor.agent.dialogue")


# ─────────────────────────────────────────────────────────────────────────────
# Intent → context configuration
# ─────────────────────────────────────────────────────────────────────────────

# How many history turns to inject for each intent.
# Intents that reference prior content need more history.
_INTENT_HISTORY_TURNS: dict = {
    Intent.CONCEPT_EXPLANATION: 2,
    Intent.CODE_HELP:           2,
    Intent.DEBUGGING:           4,   # Need to see prior code/errors
    Intent.QUIZ_REQUEST:        3,
    Intent.REPEAT_LAST:         4,   # Need to see what was said
    Intent.SIMPLIFY:            4,   # Need to see the previous explanation
    Intent.FOLLOW_UP:           5,   # Need most of the recent conversation
    Intent.OFF_TOPIC:           0,
    Intent.GREETING:            0,
    Intent.THANKS:              2,
    Intent.PDF_QUESTION:        2,
    Intent.PROJECT_HELP:        5,   # Need full project context
    Intent.CAREER_GUIDANCE:     1,
    Intent.UNSAFE:              0,
}

# Intents where the last assistant message should be explicitly referenced
_REFERENCE_LAST_RESPONSE = {
    Intent.REPEAT_LAST,
    Intent.SIMPLIFY,
    Intent.FOLLOW_UP,
}


class DialogueManager:
    """
    Assembles AgentContext by combining all signal sources.

    This is a pure builder — no I/O, no LLM calls, no async.
    All inputs are already computed by the time build_context() is called.

    Args:
        interrupt_manager: InterruptManager instance for checking/clearing interrupt state.
    """

    def __init__(self, interrupt_manager: InterruptManager) -> None:
        self._interrupt_manager = interrupt_manager
        logger.info("[OK] DialogueManager ready.")

    def build_context(
        self,
        session_id: str,
        user_text: str,
        intent_result: IntentResult,
        history: List[MemoryTurn],
        session_summary: Optional[SessionSummary],
        profile: Optional[StudentProfile],
        knowledge_route: KnowledgeRoute,
        retrieved_docs: Optional[str] = None,
        audio_emotion: Optional[EmotionResult] = None,
        voice_style: Optional[str] = None,
    ) -> AgentContext:
        """
        Build the complete AgentContext for this turn.

        Args:
            session_id:      WebSocket session identifier.
            user_text:       Raw student transcript.
            intent_result:   Result from IntentClassifier.
            history:         Full memory window (all stored turns).
            session_summary: Rolling summary (may be None early in session).
            profile:         Student profile.
            knowledge_route: RAG routing decision.
            retrieved_docs:  Retrieved text from RAG (may be None).
            audio_emotion:   Detected emotion result (optional).
            voice_style:     Voice/persona style name (optional).

        Returns:
            Fully populated AgentContext ready for PromptBuilder.
        """
        intent = intent_result.intent

        # ── 1. Detect emotion from user text or audio features ────────────────
        if audio_emotion is not None:
            emotion_result = audio_emotion
        else:
            emotion_result = detect_emotion(user_text)
        logger.info(
            "[DIALOGUE] session=%s intent=%s emotion=%s",
            session_id, intent.value, emotion_result.emotion.value
        )

        # ── 2. Trim history to intent-appropriate window ──────────────────────
        n_turns = _INTENT_HISTORY_TURNS.get(intent, 2)
        # Override with needs_history=False → no history
        if not intent_result.needs_history:
            n_turns = 0
        relevant_history = history[-n_turns:] if n_turns > 0 else []

        # ── 3. Check for pending interruption ─────────────────────────────────
        is_interrupted = self._interrupt_manager.was_interrupted(session_id)

        # Build bridge instruction (this also clears the interrupt state)
        bridge_instruction = None
        interrupt_state = None
        if is_interrupted:
            # Retrieve state BEFORE building bridge (bridge call clears it)
            interrupt_state = self._interrupt_manager.get_state(session_id)
            bridge_instruction = self._interrupt_manager.build_bridge_instruction(
                session_id, user_text
            )
            logger.info(
                "[DIALOGUE] Interruption bridge built for session=%s topic=%r",
                session_id,
                interrupt_state.topic if interrupt_state else "unknown"
            )

        # ── 4. Log style modifiers for emotion ────────────────────────────────
        if emotion_result.emotion != Emotion.NEUTRAL:
            style = get_style_for_emotion(emotion_result.emotion)
            logger.info(
                "[DIALOGUE] Emotion style: tone=%s use_examples=%s simplify=%s",
                style.get("tone"), style.get("use_examples"), style.get("simplify")
            )

        # ── 5. Assemble and return AgentContext ───────────────────────────────
        ctx = AgentContext(
            session_id      = session_id,
            user_text       = user_text,
            intent          = intent,
            emotion         = emotion_result,
            history         = relevant_history,
            session_summary = session_summary,
            profile         = profile,
            knowledge_route = knowledge_route,
            interrupt_state = interrupt_state,
            retrieved_docs  = retrieved_docs,
            is_interrupted  = is_interrupted,
            safety_flags    = {
                "bridge_instruction": bridge_instruction,  # Passed through to PromptBuilder
            },
            voice_style     = voice_style,
        )

        return ctx

    def get_topic_from_history(self, history: List[MemoryTurn]) -> Optional[str]:
        """
        Infer the most recent topic from conversation history.

        Used by InterruptManager.save_state() to record what was being discussed.
        Looks at the intent and content of the last few turns.

        Args:
            history: Recent memory turns.

        Returns:
            A brief topic string, or None if not detectable.
        """
        if not history:
            return None

        # Simple heuristic: extract first noun phrase from last assistant turn
        last = history[-1]
        # Look for "What is X", "X is a", "explains X" patterns
        patterns = [
            r"(?:what is|about|explain|discussing|topic:)\s+([A-Z][a-z]+(?:\s+[a-z]+){0,3})",
            r"([A-Z][a-z]+(?:\s+[a-z]+){0,2})\s+is\s+(?:a|an|the)",
        ]
        import re
        for pattern in patterns:
            m = re.search(pattern, last.user, re.IGNORECASE)
            if m:
                return m.group(1).strip()[:50]

        # Fallback: use the last intent if stored
        if last.intent:
            return last.intent.replace("_", " ").title()

        return None
