"""
EduMentor Agent Layer — Session Summarizer

Compresses conversation history every 10 turns into a structured JSON summary
that persists for the entire session, regardless of turn count.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agent.models import MemoryTurn, SessionSummary
from config import Config

logger = logging.getLogger("edumentor.agent.summarizer")

# Default directory for summary files
_SUMMARY_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "session_summaries")


# ─────────────────────────────────────────────────────────────────────────────
# Summarization Prompt Template
# ─────────────────────────────────────────────────────────────────────────────

_SUMMARIZE_SYSTEM = (
    "You are a conversation analyzer for an AI tutoring system. "
    "Extract key information from the conversation history below. "
    "Return ONLY a valid JSON object. No extra text."
)

_SUMMARIZE_USER_TEMPLATE = """Conversation history:
{history}

{previous_summary}

Extract and return this JSON (use null for unknown fields):
{{
  "project": "the student's project name or null",
  "goal": "the student's learning or project goal or null",
  "progress": "current progress summary or null",
  "topics_covered": ["list", "of", "topics", "discussed"],
  "current_topic": "most recent topic or null",
  "student_struggles": ["topics the student found hard"],
  "agreements": ["any teaching style agreements made"]
}}"""


def _build_history_text(turns: List[MemoryTurn], max_chars: int = 1500) -> str:
    """
    Convert memory turns to a compact text representation for the LLM prompt.
    Truncates oldest turns first if needed to stay within max_chars.
    """
    lines = []
    for turn in turns:
        lines.append(f"Student: {turn.user}")
        lines.append(f"Tutor: {turn.assistant[:200]}")  # Cap individual response length
        lines.append("")

    full = "\n".join(lines)
    if len(full) <= max_chars:
        return full

    # Truncate from the front (oldest content)
    return "...[earlier context truncated]...\n" + full[-max_chars:]


def _build_previous_summary_block(summary: Optional[SessionSummary]) -> str:
    """Format previous summary for injection into the next summarization prompt."""
    if not summary:
        return ""
    return f"Previous summary to update:\n{json.dumps(summary.to_dict(), indent=2)}"


def _parse_summary_json(raw: str, session_id: str) -> Optional[dict]:
    """
    Extract a JSON object from the LLM response.
    """
    if not raw:
        return None

    raw = re.sub(r"```(?:json)?\s*", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning(
        "[SUMMARIZER] Failed to parse JSON for session=%s raw=%r",
        session_id, raw[:200]
    )
    return None


class SessionSummarizer:
    """
    Generates and maintains a rolling structured summary of each conversation.
    """

    def __init__(self, llm_engine, summary_dir: str = _SUMMARY_DIR) -> None:
        self._llm = llm_engine
        self._summary_dir = summary_dir
        self._cache: Dict[str, SessionSummary] = {}
        self._lock = threading.Lock()
        os.makedirs(self._summary_dir, exist_ok=True)
        logger.info("[OK] SessionSummarizer ready. Summary dir: %s", self._summary_dir)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def save_turn_to_buffer(self, session_id: str, turn: MemoryTurn) -> None:
        """Save a raw turn to Redis turn_buffer:session_id."""
        from agent.state_store import get_state_store
        store = get_state_store()
        key = f"turn_buffer:{session_id}"
        
        turn_dict = turn.to_dict() if hasattr(turn, 'to_dict') else turn
        await store.rpush(key, json.dumps(turn_dict))
        await store.ltrim(key, -10, -1)  # Keep last 10 turns
        await store.expire(key, Config.REDIS_SESSION_TTL_SECONDS)

    def schedule_summarize(
        self,
        session_id: str,
        history: List[MemoryTurn],
        turn_count: int,
    ) -> None:
        """
        Schedule a background summarization run.
        """
        asyncio.create_task(self._run_summarize_async(session_id, history, turn_count))

    async def get_summary(self, session_id: str) -> Optional[SessionSummary]:
        """
        Retrieve the latest summary for a session.
        """
        from agent.state_store import get_state_store
        store = get_state_store()
        key = f"session_summary:{session_id}"

        # 1. Try loading from Redis/state_store
        data = await store.get(key)
        if data:
            try:
                return SessionSummary.from_dict(json.loads(data))
            except Exception as e:
                logger.error("Failed to parse session summary from state store: %s", e)

        # 2. Try cache
        with self._lock:
            if session_id in self._cache:
                return self._cache[session_id]

        # 3. Try disk
        summary = self._load_from_disk(session_id)
        if summary:
            await store.set(key, json.dumps(summary.to_dict()), ex=Config.REDIS_SESSION_TTL_SECONDS)
            return summary

        return None

    async def update_field(self, session_id: str, key: str, value) -> None:
        """
        Manually update a single field in the session summary.
        """
        from agent.state_store import get_state_store
        store = get_state_store()

        summary = await self.get_summary(session_id)
        if summary and hasattr(summary, key):
            setattr(summary, key, value)
            
            # Save to Redis
            skey = f"session_summary:{session_id}"
            await store.set(skey, json.dumps(summary.to_dict()), ex=Config.REDIS_SESSION_TTL_SECONDS)

            with self._lock:
                self._cache[session_id] = summary
            self._save_to_disk(summary)
            logger.debug(
                "[SUMMARIZER] Field updated: session=%s %s=%r",
                session_id, key, value
            )

    async def clear_summary(self, session_id: str) -> None:
        """
        Remove the summary for a session (called on session reset/disconnect).
        """
        from agent.state_store import get_state_store
        store = get_state_store()
        await store.delete(f"session_summary:{session_id}")
        await store.delete(f"turn_buffer:{session_id}")

        with self._lock:
            self._cache.pop(session_id, None)

        path = self._summary_path(session_id)
        if os.path.exists(path):
            os.remove(path)
        logger.debug("[SUMMARIZER] Summary cleared for session=%s", session_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: LLM summarization (runs in background async task)
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_summarize_async(
        self,
        session_id: str,
        history: List[MemoryTurn],
        turn_count: int,
    ) -> None:
        """
        Perform the actual LLM summarization call asynchronously.
        """
        start = time.perf_counter()
        logger.info("[SUMMARIZER] Starting summarization for session=%s", session_id)

        try:
            history_text = _build_history_text(history)
            previous = await self.get_summary(session_id)
            prev_block = _build_previous_summary_block(previous)
            user_content = _SUMMARIZE_USER_TEMPLATE.format(
                history=history_text,
                previous_summary=prev_block,
            )

            payload = {
                "model":       "local",
                "messages": [
                    {"role": "system",  "content": _SUMMARIZE_SYSTEM},
                    {"role": "user",    "content": user_content},
                ],
                "stream":      False,
                "max_tokens":  300,
                "temperature": 0.1,
            }

            import httpx
            base_url = self._llm.base_url if hasattr(self._llm, 'base_url') else Config.LLM_BASE_URL
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0)) as client:
                response = await client.post(f"{base_url}/v1/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                raw_response = choices[0].get("message", {}).get("content", "") if choices else ""

            if not raw_response:
                logger.warning(
                    "[SUMMARIZER] Empty response from LLM for session=%s", session_id
                )
                return

            parsed = _parse_summary_json(raw_response, session_id)
            if parsed is None:
                return

            summary = SessionSummary(
                session_id        = session_id,
                last_updated      = datetime.now(timezone.utc).isoformat(),
                turn_count        = turn_count,
                project           = parsed.get("project") or (previous.project if previous else None),
                goal              = parsed.get("goal") or (previous.goal if previous else None),
                progress          = parsed.get("progress"),
                topics_covered    = parsed.get("topics_covered", []),
                current_topic     = parsed.get("current_topic"),
                student_struggles = parsed.get("student_struggles", []),
                agreements        = parsed.get("agreements", []),
            )

            from agent.state_store import get_state_store
            store = get_state_store()
            key = f"session_summary:{session_id}"
            await store.set(key, json.dumps(summary.to_dict()), ex=Config.REDIS_SESSION_TTL_SECONDS)

            with self._lock:
                self._cache[session_id] = summary
            self._save_to_disk(summary)

            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                "[SUMMARIZER] Done session=%s turn=%d elapsed=%.0fms summary=%s",
                session_id, turn_count, elapsed,
                json.dumps(summary.to_dict(), ensure_ascii=False)[:200]
            )

        except Exception as exc:
            logger.exception(
                "[SUMMARIZER] Failed for session=%s: %s", session_id, exc
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Disk persistence helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _summary_path(self, session_id: str) -> str:
        safe_id = re.sub(r"[^\w\-.]", "_", session_id)
        return os.path.join(self._summary_dir, f"{safe_id}.json")

    def _save_to_disk(self, summary: SessionSummary) -> None:
        try:
            path = self._summary_path(summary.session_id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(summary.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug("[SUMMARIZER] Saved to disk: %s", path)
        except Exception as exc:
            logger.warning("[SUMMARIZER] Disk save failed: %s", exc)

    def _load_from_disk(self, session_id: str) -> Optional[SessionSummary]:
        try:
            path = self._summary_path(session_id)
            if not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            summary = SessionSummary.from_dict(data)
            with self._lock:
                self._cache[session_id] = summary
            logger.info("[SUMMARIZER] Loaded from disk: %s", path)
            return summary
        except Exception as exc:
            logger.warning("[SUMMARIZER] Disk load failed: %s", exc)
            return None
