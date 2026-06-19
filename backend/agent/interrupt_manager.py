"""
EduMentor Agent Layer — Voice Interruption Manager

Handles smart voice interruption — saving context before cancellation
and restoring it for the next turn so the tutor responds naturally.

Pipeline position (on interruption):
  1. User interrupts mid-speech
  2. main.py receives { type: "interrupt" }
  3. InterruptManager.save_state() is called BEFORE asyncio task cancellation
  4. Pipeline is cancelled (existing mechanism)
  5. Next turn: DialogueManager calls was_interrupted() and get_state()
  6. A bridge instruction is injected into the system prompt
  7. Tutor responds naturally, acknowledging the interruption

This transforms a jarring hard stop into a smooth, human-like transition.

Design notes:
  - In-memory store (dict). Zero persistence cost.
  - States are auto-cleared after use (one-shot pattern).
  - Thread-safe by construction (asyncio single-threaded event loop).
  - All methods are synchronous — no await needed, no blocking.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional

from agent.models import InterruptState

logger = logging.getLogger("edumentor.agent.interrupt")


class InterruptManager:
    """
    Manages interruption state across conversation turns.

    One instance lives for the lifetime of the FastAPI application.
    State is keyed by session_id (one entry per active WebSocket connection).

    Thread safety:
        asyncio is single-threaded by design. All WebSocket events are
        processed on the same event loop, so no locking is needed.
    """

    def __init__(self) -> None:
        # session_id → InterruptState
        self._states: Dict[str, InterruptState] = {}

        # Per-session tracking of total chars generated (for fraction calc)
        # session_id → chars delivered to TTS so far in the current turn
        self._chars_sent: Dict[str, int] = {}

        logger.info("[OK] InterruptManager ready.")

    # ─────────────────────────────────────────────────────────────────────────
    # State save / restore
    # ─────────────────────────────────────────────────────────────────────────

    def save_state(
        self,
        session_id: str,
        partial_response: str,
        topic: str,
        total_response_chars: int = 0,
    ) -> None:
        """
        Save the current pipeline state before cancellation.

        Called from main.py's interrupt handler, BEFORE the asyncio task is
        cancelled. Captures what the tutor was saying so the next turn can
        produce a natural bridge.

        Args:
            session_id:           The WebSocket session identifier.
            partial_response:     Accumulated LLM text that was being generated.
            topic:                The topic being discussed at interrupt time.
            total_response_chars: Total chars in the response so far (for fraction calc).
        """
        chars_sent = self._chars_sent.get(session_id, 0)
        total = max(total_response_chars, chars_sent, 1)
        fraction = min(chars_sent / total, 1.0)

        state = InterruptState(
            session_id=session_id,
            interrupted_response=partial_response[:500],  # Cap length for prompt
            interrupted_at_fraction=fraction,
            topic=topic,
            was_mid_explanation=len(partial_response.strip()) > 20,
            timestamp=time.time(),
        )
        self._states[session_id] = state

        logger.info(
            "[INTERRUPT] state saved session=%s topic=%r fraction=%.2f partial=%r",
            session_id, topic, fraction, partial_response[:60]
        )

    def get_state(self, session_id: str) -> Optional[InterruptState]:
        """
        Retrieve the saved interrupt state for a session (non-destructive).

        Returns None if no interruption was recorded.
        """
        return self._states.get(session_id)

    def clear_state(self, session_id: str) -> None:
        """
        Clear the interrupt state after it has been used by the DialogueManager.

        Called after the bridge instruction has been built to prevent it from
        appearing in every subsequent turn.
        """
        if session_id in self._states:
            del self._states[session_id]
            logger.debug("[INTERRUPT] state cleared for session=%s", session_id)

    def was_interrupted(self, session_id: str) -> bool:
        """
        Check whether the previous turn was interrupted.

        Args:
            session_id: The WebSocket session identifier.

        Returns:
            True if there is a pending interrupt state for this session.
        """
        return session_id in self._states

    # ─────────────────────────────────────────────────────────────────────────
    # Chars-sent tracking (called from main.py as tokens stream)
    # ─────────────────────────────────────────────────────────────────────────

    def track_chars_sent(self, session_id: str, chars: int) -> None:
        """
        Accumulate the number of characters delivered to TTS for this turn.

        Called from _stream_llm_and_tts as each sentence is dispatched.
        Used to calculate interrupted_at_fraction when save_state() is called.

        Args:
            session_id: The session identifier.
            chars:      Number of characters in the sentence just dispatched.
        """
        self._chars_sent[session_id] = self._chars_sent.get(session_id, 0) + chars

    def reset_turn(self, session_id: str) -> None:
        """
        Reset per-turn tracking counters at the start of a new pipeline run.

        Called from main.py at the beginning of each _run_pipeline() call.
        """
        self._chars_sent[session_id] = 0

    # ─────────────────────────────────────────────────────────────────────────
    # Bridge instruction builder
    # ─────────────────────────────────────────────────────────────────────────

    def build_bridge_instruction(
        self,
        session_id: str,
        new_user_text: str,
    ) -> Optional[str]:
        """
        Build a natural-language bridge instruction for the system prompt.

        This is injected by PromptBuilder when was_interrupted() is True.
        After calling this, the state is automatically cleared (one-shot).

        Args:
            session_id:    The session identifier.
            new_user_text: The new question/statement from the student.

        Returns:
            A string instruction to append to the system prompt, or None if
            no interruption was recorded.
        """
        state = self._states.get(session_id)
        if state is None:
            return None

        # Build context-aware bridge text
        if state.was_mid_explanation and state.topic:
            bridge = (
                f"[INTERRUPTION CONTEXT] You were in the middle of explaining '{state.topic}' "
                f"when the student interrupted. "
                f"You had said: \"{state.interrupted_response[:150]}...\" "
                f"The student now asks: \"{new_user_text}\". "
                f"Briefly and naturally acknowledge the interruption "
                f"(one short sentence), then answer their new question. "
                f"Offer to continue your earlier explanation afterwards if relevant."
            )
        else:
            bridge = (
                f"[INTERRUPTION CONTEXT] The student interrupted your previous response. "
                f"They now ask: \"{new_user_text}\". "
                f"Respond naturally and helpfully."
            )

        # Clear state — it's been consumed
        self.clear_state(session_id)

        logger.debug("[INTERRUPT] bridge instruction built for session=%s", session_id)
        return bridge

    # ─────────────────────────────────────────────────────────────────────────
    # Cleanup
    # ─────────────────────────────────────────────────────────────────────────

    def clear_session(self, session_id: str) -> None:
        """
        Fully remove all data for a session (called on WebSocket disconnect).

        Args:
            session_id: The disconnecting session's identifier.
        """
        self._states.pop(session_id, None)
        self._chars_sent.pop(session_id, None)
        logger.debug("[INTERRUPT] session %s fully cleared.", session_id)
