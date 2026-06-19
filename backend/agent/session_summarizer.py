"""
EduMentor Agent Layer — Session Summarizer

Compresses conversation history every 10 turns into a structured JSON summary
that persists for the entire session, regardless of turn count.

This solves the critical "long conversation amnesia" problem:
  - Without summarizer: context window = last 10 turns only
  - With summarizer:    project, goals, struggles, topics = ALWAYS available

Design:
  - Uses the existing GGUF LLM (via LLMEngine) for summarization
  - Runs in a background ThreadPoolExecutor — ZERO added latency to current turn
  - Summaries saved to disk (data/session_summaries/<session_id>.json)
  - Robust JSON parsing with regex fallback
  - Graceful degradation — if summarizer fails, main pipeline is unaffected

Pipeline position:
  MemoryManager.add_turn() → [every 10 turns] → SessionSummarizer.schedule_summarize()
                                                    ↓ (background thread)
                              LLMEngine (compressed prompt ~100 tokens)
                                                    ↓
                              SessionSummary saved to disk + cached in memory
                                                    ↓
  PromptBuilder.build_system_prompt() → get_summary() → injected into every prompt
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

    Handles:
      - Clean JSON response
      - JSON embedded in markdown code blocks
      - JSON embedded in other text (regex extraction)
    """
    if not raw:
        return None

    # Strip markdown code fences if present
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip()

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to extract first JSON object via regex
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


# ─────────────────────────────────────────────────────────────────────────────
# SessionSummarizer
# ─────────────────────────────────────────────────────────────────────────────

class SessionSummarizer:
    """
    Generates and maintains a rolling structured summary of each conversation.

    One instance lives for the lifetime of the FastAPI application.
    The LLMEngine is injected at construction time.

    Summarization is triggered by MemoryManager every 10 turns and runs
    in a background daemon thread — completely transparent to the main pipeline.

    Args:
        llm_engine:   The existing LLMEngine instance (reused, no new model loaded).
        summary_dir:  Directory to persist summary JSON files.
    """

    def __init__(self, llm_engine, summary_dir: str = _SUMMARY_DIR) -> None:
        self._llm = llm_engine
        self._summary_dir = summary_dir

        # In-memory cache: session_id → SessionSummary
        self._cache: Dict[str, SessionSummary] = {}

        # Threading lock for cache writes (background thread + main thread)
        self._lock = threading.Lock()

        # Background worker thread pool (daemon=True so it doesn't block shutdown)
        self._executor = None  # Lazy init to avoid event loop issues at startup

        # Ensure summary directory exists
        os.makedirs(self._summary_dir, exist_ok=True)

        logger.info("[OK] SessionSummarizer ready. Summary dir: %s", self._summary_dir)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def schedule_summarize(
        self,
        session_id: str,
        history: List[MemoryTurn],
        turn_count: int,
    ) -> None:
        """
        Schedule a background summarization run.

        This returns IMMEDIATELY — the LLM call happens in a background thread.
        Called by MemoryManager after every 10th turn.

        Args:
            session_id:  The session to summarize.
            history:     Current conversation turns (window before pruning).
            turn_count:  Total turns processed (for the summary's turn_count field).
        """
        # Snapshot the history to avoid mutation in the background thread
        history_snapshot = list(history)
        previous = self.get_summary(session_id)

        thread = threading.Thread(
            target=self._run_summarize,
            args=(session_id, history_snapshot, previous, turn_count),
            daemon=True,
            name=f"summarizer-{session_id[:8]}",
        )
        thread.start()
        logger.info(
            "[SUMMARIZER] Background summarization scheduled for session=%s turn=%d",
            session_id, turn_count
        )

    def get_summary(self, session_id: str) -> Optional[SessionSummary]:
        """
        Retrieve the latest summary for a session.

        Checks in-memory cache first, then disk.

        Args:
            session_id: The session identifier.

        Returns:
            SessionSummary if available, None if no summary yet.
        """
        with self._lock:
            if session_id in self._cache:
                return self._cache[session_id]

        # Try loading from disk (covers restart scenarios if using a persistent filesystem)
        return self._load_from_disk(session_id)

    def update_field(self, session_id: str, key: str, value) -> None:
        """
        Manually update a single field in the session summary.

        Useful for profile updates that happen outside the summarization cycle
        (e.g. student mentions their project name mid-turn).

        Args:
            session_id: The session identifier.
            key:        Field name (must match SessionSummary attributes).
            value:      New value.
        """
        with self._lock:
            summary = self._cache.get(session_id)
            if summary and hasattr(summary, key):
                setattr(summary, key, value)
                self._save_to_disk(summary)
                logger.debug(
                    "[SUMMARIZER] Field updated: session=%s %s=%r",
                    session_id, key, value
                )

    def clear_summary(self, session_id: str) -> None:
        """
        Remove the summary for a session (called on session reset/disconnect).
        """
        with self._lock:
            self._cache.pop(session_id, None)

        path = self._summary_path(session_id)
        if os.path.exists(path):
            os.remove(path)
        logger.debug("[SUMMARIZER] Summary cleared for session=%s", session_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: LLM summarization (runs in background thread)
    # ─────────────────────────────────────────────────────────────────────────

    def _run_summarize(
        self,
        session_id: str,
        history: List[MemoryTurn],
        previous: Optional[SessionSummary],
        turn_count: int,
    ) -> None:
        """
        Perform the actual LLM summarization call.

        This runs in a daemon background thread. All errors are caught and
        logged — a summarization failure never crashes the main pipeline.
        """
        start = time.perf_counter()
        logger.info("[SUMMARIZER] Starting summarization for session=%s", session_id)

        try:
            history_text = _build_history_text(history)
            prev_block = _build_previous_summary_block(previous)
            user_content = _SUMMARIZE_USER_TEMPLATE.format(
                history=history_text,
                previous_summary=prev_block,
            )

            # Build the payload for LLMEngine's HTTP client
            payload = {
                "model":       "local",
                "messages": [
                    {"role": "system",  "content": _SUMMARIZE_SYSTEM},
                    {"role": "user",    "content": user_content},
                ],
                "stream":      False,        # We need the full response
                "max_tokens":  300,          # Summary should be concise
                "temperature": 0.1,          # Deterministic extraction
            }

            # Run sync HTTP call via a new event loop in this background thread
            raw_response = self._call_llm_sync(payload)

            if not raw_response:
                logger.warning(
                    "[SUMMARIZER] Empty response from LLM for session=%s", session_id
                )
                return

            parsed = _parse_summary_json(raw_response, session_id)
            if parsed is None:
                return

            # Build and cache the new summary
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

    def _call_llm_sync(self, payload: dict) -> Optional[str]:
        """
        Make a synchronous (non-streaming) HTTP call to the LLM server.

        Creates a new event loop in the background thread since asyncio
        loops are not shareable across threads.
        """
        import asyncio
        import httpx

        async def _fetch() -> Optional[str]:
            try:
                async with httpx.AsyncClient(
                    base_url=self._llm.base_url,
                    timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
                    headers={"Content-Type": "application/json"},
                ) as client:
                    response = await client.post(
                        "/v1/chat/completions", json=payload
                    )
                    response.raise_for_status()
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
            except Exception as exc:
                logger.exception("[SUMMARIZER] LLM HTTP error: %s", exc)
            return None

        # Run in a fresh event loop for this thread
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_fetch())
        finally:
            loop.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Disk persistence helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _summary_path(self, session_id: str) -> str:
        # Sanitise session_id for use as a filename
        safe_id = re.sub(r"[^\w\-.]", "_", session_id)
        return os.path.join(self._summary_dir, f"{safe_id}.json")

    def _save_to_disk(self, summary: SessionSummary) -> None:
        """Persist summary to disk. Errors are logged but not raised."""
        try:
            path = self._summary_path(summary.session_id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(summary.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug("[SUMMARIZER] Saved to disk: %s", path)
        except Exception as exc:
            logger.warning("[SUMMARIZER] Disk save failed: %s", exc)

    def _load_from_disk(self, session_id: str) -> Optional[SessionSummary]:
        """Load summary from disk (restart recovery). Returns None if not found."""
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
