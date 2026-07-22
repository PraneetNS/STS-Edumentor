"""
EduMentor Agent Layer — Mastery Scheduler (FSRS-backed spaced repetition)

Wraps py-fsrs's Scheduler. concept_mastery rows in Postgres ARE the
source of truth; fsrs.Card objects are reconstructed per-call, never
held in memory between requests.

Concept slugs come from agent.student_profile._detect_topics(), called
directly and per-request — NOT from StudentProfileManager.get_active_topic(),
which is a shared process-wide singleton unsafe for concurrent users
(see TODO(mastery) note in controller.py).
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional

from fsrs import Scheduler, Card, Rating, State

_scheduler = Scheduler()  # DEFAULT_PARAMETERS; consider fsrs.Optimizer once enough review_logs accumulate


def slugify_concept(topic: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", topic.strip().lower()).strip("_")
    return s or "general"


def _row_to_card(row: dict) -> Card:
    return Card(
        card_id=row["id"],
        state=State(row["state"]),
        step=row["step"],
        stability=row["stability"],
        difficulty=row["difficulty"],
        due=row["due"],
        last_review=row["last_review"],
    )


class MasteryScheduler:
    def __init__(self, db_manager) -> None:
        self._db = db_manager

    async def get_due_concepts(self, user_id, limit: int = 3):
        return await self._db.get_due_concepts(user_id, limit=limit)

    async def record_review(self, user_id, concept_topic: str, rating: Rating) -> None:
        slug = slugify_concept(concept_topic)
        row = await self._db.get_or_create_card_row(user_id, slug)
        if not row:
            return
        card = _row_to_card(row)
        updated_card, _log = _scheduler.review_card(
            card, rating, review_datetime=datetime.now(timezone.utc)
        )
        await self._db.save_card_review(
            row_id=row["id"],
            state=int(updated_card.state),
            step=updated_card.step,
            stability=updated_card.stability,
            difficulty=updated_card.difficulty,
            due=updated_card.due,
            last_review=updated_card.last_review,
        )

    async def touch_concept(self, user_id, topic: str) -> None:
        """Register a concept that came up but wasn't quizzed on, so it
        enters the FSRS queue with a first `due` date for future review."""
        await self._db.get_or_create_card_row(user_id, slugify_concept(topic))


_GRADE_SYSTEM = (
    "You grade a student's spoken answer to a quick recall check. "
    "Return ONLY one word: Again, Hard, Good, or Easy. "
    "Again = wrong/no answer. Hard = partially right, hesitant. "
    "Good = correct. Easy = correct and confident/detailed."
)
_GRADE_TEMPLATE = 'Question: "{question}"\nStudent answered: "{answer}"\n\nRating:'


class RecallGrader:
    """
    Grades a student's recall-check answer via a tiny LLM call.

    Uses LLMEngine.get_completion() — the existing non-streaming,
    timeout-bound, circuit-breaker-protected method already used for the
    STT correction pass — rather than opening a second raw httpx client
    (that's what IntentClassifier does, and it's the outlier: it bypasses
    the circuit breaker entirely; don't copy that part of its pattern).
    """
    def __init__(self, llm_engine) -> None:
        self._llm = llm_engine

    async def grade(self, question: str, answer: str) -> Rating:
        messages = [
            {"role": "system", "content": _GRADE_SYSTEM},
            {"role": "user", "content": _GRADE_TEMPLATE.format(
                question=question[:200], answer=answer[:300])},
        ]
        text = await self._llm.get_completion(messages, max_tokens=5, timeout=2.0)
        text = (text or "").strip().lower()
        for name, val in (("again", Rating.Again), ("hard", Rating.Hard),
                          ("easy", Rating.Easy), ("good", Rating.Good)):
            if name in text:
                return val
        return Rating.Hard  # fail-safe default on empty/unparseable grading
