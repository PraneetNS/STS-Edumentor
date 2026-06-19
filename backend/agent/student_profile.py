"""
EduMentor Agent Layer — Student Profile Manager

Loads, saves, and automatically updates the persistent student profile.

The profile personalizes every response — the tutor knows the student's name,
skill level, preferred learning style, and weak topics without the student
having to repeat themselves each session.

Storage: backend/data/student_profile.json (created automatically on first run)
Format:  JSON flat object matching StudentProfile dataclass fields

Features:
  - Auto-inference of topics from conversation (keyword detection)
  - Auto-marking of weak topics when frustration/confusion is detected
  - Level progression detection
  - Style preference detection
  - Thread-safe disk writes

Pipeline position:
  AgentController → StudentProfileManager.get_profile() → StudentProfile
  AgentController → StudentProfileManager.update_from_turn() (post-turn)
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import List, Optional, Set

from agent.models import Emotion, StudentProfile

logger = logging.getLogger("edumentor.agent.student_profile")

# Default profile path (relative to backend/ directory)
_DEFAULT_PROFILE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "student_profile.json"
)

# ─────────────────────────────────────────────────────────────────────────────
# Topic keyword map — detect learning topics from conversation
# ─────────────────────────────────────────────────────────────────────────────

# Maps canonical topic names to lists of keywords that imply that topic
_TOPIC_KEYWORDS: dict = {
    "Python":              ["python", "py", "def ", "import ", "list comprehension"],
    "JavaScript":          ["javascript", "js", "node.js", "react", "typescript"],
    "Data Structures":     ["array", "linked list", "stack", "queue", "hash map", "tree", "graph", "heap"],
    "Algorithms":          ["sorting", "searching", "recursion", "dynamic programming", "greedy", "backtracking"],
    "Machine Learning":    ["machine learning", "ml", "neural network", "training", "model", "dataset", "ai"],
    "Deep Learning":       ["deep learning", "cnn", "rnn", "lstm", "transformer", "pytorch", "tensorflow"],
    "Web Development":     ["html", "css", "frontend", "backend", "api", "rest", "fastapi", "flask", "django"],
    "Databases":           ["sql", "database", "mongodb", "postgres", "mysql", "query", "join"],
    "DSA":                 ["dsa", "leetcode", "interview", "time complexity", "space complexity", "big o"],
    "Computer Science":    ["operating system", "os", "process", "thread", "memory", "cpu", "compiler"],
    "Sentiment Analysis":  ["sentiment", "nlp", "natural language", "bert", "text classification"],
    "System Design":       ["system design", "scalability", "microservices", "load balancer", "cache"],
    "Git":                 ["git", "github", "commit", "branch", "pull request", "merge"],
    "Career":              ["job", "resume", "interview", "career", "salary", "company", "hiring"],
}


def _detect_topics(text: str) -> List[str]:
    """
    Detect programming/CS topics mentioned in a text string.

    Args:
        text: User or assistant text.

    Returns:
        List of canonical topic names detected.
    """
    text_lower = text.lower()
    detected = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            detected.append(topic)
    return detected


def _detect_level(text: str) -> Optional[str]:
    """
    Attempt to detect student self-described level from text.

    Returns 'beginner', 'intermediate', or 'advanced' if detected, else None.
    """
    text_lower = text.lower()
    if any(k in text_lower for k in ["i'm a beginner", "im a beginner", "just starting", "new to programming", "never coded"]):
        return "beginner"
    if any(k in text_lower for k in ["intermediate", "some experience", "know the basics", "practiced"]):
        return "intermediate"
    if any(k in text_lower for k in ["advanced", "expert", "professional", "senior", "years of experience"]):
        return "advanced"
    return None


def _detect_style_preference(text: str) -> Optional[str]:
    """
    Detect preferred teaching style from explicit student statements.

    Returns 'examples', 'theory', or 'mixed' if detected, else None.
    """
    text_lower = text.lower()
    if any(k in text_lower for k in ["show me an example", "give me an example", "examples please", "use examples"]):
        return "examples"
    if any(k in text_lower for k in ["explain the theory", "theoretical", "why does it work", "how does it work internally"]):
        return "theory"
    if any(k in text_lower for k in ["both", "mixed", "theory and examples"]):
        return "mixed"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Profile Manager
# ─────────────────────────────────────────────────────────────────────────────

# Default profile data used when no file exists yet
_DEFAULT_PROFILE = {
    "name": "Student",
    "level": "beginner",
    "learning_topics": [],
    "weak_topics": [],
    "preferred_style": "examples",
    "session_count": 0,
}


class StudentProfileManager:
    """
    Manages the persistent student profile.

    Loads from disk on startup and saves back after each update.
    In-memory cache is the primary read path (fast).
    Disk writes are serialized via a threading.Lock for safety.

    Args:
        profile_path: Path to the student_profile.json file.
    """

    def __init__(self, profile_path: str = _DEFAULT_PROFILE_PATH) -> None:
        self._path = profile_path
        self._lock = threading.Lock()
        self._profile: StudentProfile = self._load()
        logger.info(
            "[OK] StudentProfileManager ready. Profile: name=%s level=%s",
            self._profile.name, self._profile.level
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def get_profile(self) -> StudentProfile:
        """
        Return the current student profile (in-memory, fast).

        Returns:
            StudentProfile dataclass instance.
        """
        return self._profile

    def update_from_turn(
        self,
        user_text: str,
        assistant_text: str,
        emotion: Optional[Emotion] = None,
    ) -> None:
        """
        Automatically update the profile based on a completed turn.

        Infers topics, level, and style preferences from the conversation.
        Also marks weak topics when frustration/confusion is detected.

        Args:
            user_text:      Student's transcribed speech.
            assistant_text: Tutor's response (for topic detection).
            emotion:        Detected emotion (marks weak topics if frustrated/confused).
        """
        changed = False
        combined = f"{user_text} {assistant_text}"

        # ── Topic detection ───────────────────────────────────────────────────
        new_topics = _detect_topics(combined)
        existing = set(self._profile.learning_topics)
        for topic in new_topics:
            if topic not in existing:
                self._profile.learning_topics.append(topic)
                existing.add(topic)
                changed = True
                logger.info("[PROFILE] New topic detected: %s", topic)

        # ── Weak topic detection (frustrated/confused emotion) ────────────────
        if emotion in (Emotion.FRUSTRATED, Emotion.CONFUSED):
            # Mark currently discussed topics as weak
            weak_set: Set[str] = set(self._profile.weak_topics)
            for topic in new_topics:
                if topic not in weak_set:
                    self._profile.weak_topics.append(topic)
                    weak_set.add(topic)
                    changed = True
                    logger.info(
                        "[PROFILE] Weak topic marked (emotion=%s): %s",
                        emotion.value, topic
                    )

        # ── Level detection ───────────────────────────────────────────────────
        detected_level = _detect_level(user_text)
        if detected_level and detected_level != self._profile.level:
            self._profile.level = detected_level
            changed = True
            logger.info("[PROFILE] Level updated: %s", detected_level)

        # ── Style preference detection ────────────────────────────────────────
        detected_style = _detect_style_preference(user_text)
        if detected_style and detected_style != self._profile.preferred_style:
            self._profile.preferred_style = detected_style
            changed = True
            logger.info("[PROFILE] Style preference updated: %s", detected_style)

        # Save to disk only if something changed (avoid unnecessary writes)
        if changed:
            self._save()

    def update_name(self, name: str) -> None:
        """
        Update the student's name.

        Args:
            name: New name to set.
        """
        if name and name != self._profile.name:
            self._profile.name = name
            self._save()
            logger.info("[PROFILE] Name updated: %s", name)

    def increment_session_count(self) -> None:
        """Increment the total session counter (call at session start)."""
        self._profile.session_count += 1
        self._save()

    def set_level(self, level: str) -> None:
        """
        Manually set the student's skill level.

        Args:
            level: 'beginner' | 'intermediate' | 'advanced'
        """
        if level in ("beginner", "intermediate", "advanced"):
            self._profile.level = level
            self._save()
            logger.info("[PROFILE] Level manually set: %s", level)

    # ─────────────────────────────────────────────────────────────────────────
    # Disk I/O
    # ─────────────────────────────────────────────────────────────────────────

    def _load(self) -> StudentProfile:
        """Load profile from disk or create default if not found."""
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("[PROFILE] Loaded from: %s", self._path)
                return StudentProfile.from_dict(data)
        except Exception as exc:
            logger.warning("[PROFILE] Load failed (%s), using defaults.", exc)

        # Create default profile and persist it
        profile = StudentProfile.from_dict(_DEFAULT_PROFILE)
        self._profile = profile
        self._save()
        logger.info("[PROFILE] Default profile created at: %s", self._path)
        return profile

    def _save(self) -> None:
        """Write current profile to disk. Errors are logged, not raised."""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(self._profile.to_dict(), f, indent=2, ensure_ascii=False)
                logger.debug("[PROFILE] Saved to: %s", self._path)
            except Exception as exc:
                logger.warning("[PROFILE] Save failed: %s", exc)
