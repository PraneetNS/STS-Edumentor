"""
EduMentor Agent Layer — Student Profile Manager

Loads, saves, and automatically updates the persistent student profile.
"""

from __future__ import annotations

import json
import logging
import os
import re
import asyncio
import threading
from typing import List, Optional, Set, Dict, Any

from agent.models import Emotion, StudentProfile
from config import Config

logger = logging.getLogger("edumentor.agent.student_profile")

# Default profile path (relative to backend/ directory)
_DEFAULT_PROFILE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "student_profile.json"
)

# ─────────────────────────────────────────────────────────────────────────────
# Topic keyword map — detect learning topics from conversation
# ─────────────────────────────────────────────────────────────────────────────

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
    "Electrical Engineering": ["electrical", "impedance", "capacitor", "inductor", "resistor", "thevenin", "op-amp"],
    "Electronics Engineering": ["electronics", "antenna", "signal processing", "modulation", "multiplexing", "ece"],
    "Mechanical Engineering": ["mechanical", "torque", "tensile strength", "thermodynamics", "reynolds", "stress-strain"],
    "Civil Engineering": ["civil", "concrete", "structural", "beam", "foundation", "slab", "rcc"],
    "Chemical Engineering": ["chemical", "distillation", "stoichiometry", "mass transfer", "reactor"],
    "Aerospace Engineering": ["aerospace", "aerodynamics", "thrust", "propulsion", "wing", "stall", "lift coefficient"],
}

TOPIC_TO_DISCIPLINE: dict = {
    "Python": "cse",
    "JavaScript": "cse",
    "Data Structures": "cse",
    "Algorithms": "cse",
    "Machine Learning": "cse",
    "Deep Learning": "cse",
    "Web Development": "cse",
    "Databases": "cse",
    "DSA": "cse",
    "Computer Science": "cse",
    "Sentiment Analysis": "cse",
    "System Design": "cse",
    "Git": "cse",
    "Career": "cse",
    "Electrical Engineering": "eee",
    "Electronics Engineering": "ece",
    "Mechanical Engineering": "mech",
    "Civil Engineering": "civil",
    "Chemical Engineering": "chemical",
    "Aerospace Engineering": "aerospace",
}


def _detect_topics(text: str) -> List[str]:
    text_lower = text.lower()
    detected = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        for kw in keywords:
            pattern = r'\b' + re.escape(kw.strip()) + r'\b'
            if kw.endswith(" "):
                pattern = r'\b' + re.escape(kw.strip()) + r'\s'
            if re.search(pattern, text_lower):
                detected.append(topic)
                break
    return detected


def _detect_level(text: str) -> Optional[str]:
    text_lower = text.lower()
    if any(k in text_lower for k in ["i'm a beginner", "im a beginner", "just starting", "new to programming", "never coded"]):
        return "beginner"
    if any(k in text_lower for k in ["intermediate", "some experience", "know the basics", "practiced"]):
        return "intermediate"
    if any(k in text_lower for k in ["advanced", "expert", "professional", "senior", "years of experience"]):
        return "advanced"
    return None


def _detect_style_preference(text: str) -> Optional[str]:
    text_lower = text.lower()
    if any(k in text_lower for k in ["show me an example", "give me an example", "examples please", "use examples"]):
        return "examples"
    if any(k in text_lower for k in ["explain the theory", "theoretical", "why does it work", "how does it work internally"]):
        return "theory"
    if any(k in text_lower for k in ["both", "mixed", "theory and examples"]):
        return "mixed"
    return None


_DEFAULT_PROFILE = {
    "name": "Student",
    "level": "beginner",
    "learning_topics": [],
    "weak_topics": [],
    "preferred_style": "examples",
    "session_count": 0,
    "discipline": "cse",
    "active_topics": [],
    "output_language_preference": "auto",
    "glossary_mode": "english",
}


class StudentProfileManager:
    def __init__(self, profile_path: str = _DEFAULT_PROFILE_PATH, db_manager=None) -> None:
        self._path = profile_path
        self._lock = threading.Lock()
        self.db_manager = db_manager
        self._profile: StudentProfile = self._load()
        logger.info(
            "[OK] StudentProfileManager ready. Default Profile: name=%s level=%s",
            self._profile.name, self._profile.level
        )

    async def get_profile(self, session_id: Optional[str] = None) -> StudentProfile:
        if not session_id:
            return self._profile

        from agent.state_store import get_state_store
        store = get_state_store()
        key = f"student_profile:{session_id}"

        fields = await store.hgetall(key)
        if fields:
            try:
                profile_dict = {
                    "name": fields.get("name", "Student"),
                    "level": fields.get("level", "beginner"),
                    "learning_topics": json.loads(fields.get("learning_topics", "[]")),
                    "weak_topics": json.loads(fields.get("weak_topics", "[]")),
                    "preferred_style": fields.get("preferred_style", "examples"),
                    "session_count": int(fields.get("session_count", "0")),
                    "discipline": fields.get("discipline", "cse"),
                    "active_topics": json.loads(fields.get("active_topics", "[]")),
                    "output_language_preference": fields.get("output_language_preference", "auto"),
                    "glossary_mode": fields.get("glossary_mode", "english"),
                }
                return StudentProfile.from_dict(profile_dict)
            except Exception as e:
                logger.error("Failed to parse student profile from state store: %s", e)

        # Fallback database load
        if self.db_manager:
            db_profile = await self.db_manager.load_student_profile(session_id)
            if db_profile:
                await self.save_to_state_store(session_id, db_profile)
                return StudentProfile.from_dict(db_profile)

        # Fallback to local default profile
        return self._profile

    async def save_to_state_store(self, session_id: str, profile_dict: dict) -> None:
        from agent.state_store import get_state_store
        store = get_state_store()
        key = f"student_profile:{session_id}"
        
        mapping = {
            "name": str(profile_dict.get("name", "Student")),
            "level": str(profile_dict.get("level", "beginner")),
            "learning_topics": json.dumps(profile_dict.get("learning_topics", [])),
            "weak_topics": json.dumps(profile_dict.get("weak_topics", [])),
            "preferred_style": str(profile_dict.get("preferred_style", "examples")),
            "session_count": str(profile_dict.get("session_count", 0)),
            "discipline": str(profile_dict.get("discipline", "cse")),
            "active_topics": json.dumps(profile_dict.get("active_topics", [])),
            "output_language_preference": str(profile_dict.get("output_language_preference", "auto")),
            "glossary_mode": str(profile_dict.get("glossary_mode", "english")),
        }
        for f_name, val in mapping.items():
            await store.hset(key, f_name, val)
        await store.expire(key, Config.REDIS_SESSION_TTL_SECONDS)

    async def get_active_topic(self, session_id: Optional[str] = None) -> str:
        profile = await self.get_profile(session_id)
        if profile.active_topics:
            return profile.active_topics[0]
        elif profile.learning_topics:
            return profile.learning_topics[-1]
        return "general"

    async def get_discipline(self, session_id: Optional[str] = None) -> str:
        profile = await self.get_profile(session_id)
        return profile.discipline or "cse"

    async def update_from_turn(
        self,
        user_text: str,
        assistant_text: str,
        emotion: Optional[Emotion] = None,
        session_id: Optional[str] = None,
    ) -> None:
        profile = await self.get_profile(session_id)
        changed = False
        combined = f"{user_text} {assistant_text}"

        new_topics = _detect_topics(combined)
        existing = set(profile.learning_topics)
        for topic in new_topics:
            if topic not in existing:
                profile.learning_topics.append(topic)
                existing.add(topic)
                changed = True
                logger.info("[PROFILE] New topic detected: %s", topic)

        if new_topics:
            profile.active_topics = new_topics
            for t in new_topics:
                disc = TOPIC_TO_DISCIPLINE.get(t)
                if disc:
                    if profile.discipline != disc:
                        profile.discipline = disc
                        logger.info("[PROFILE] Discipline updated: %s", disc)
                    break
            changed = True

        if emotion in (Emotion.FRUSTRATED, Emotion.CONFUSED):
            weak_set: Set[str] = set(profile.weak_topics)
            for topic in new_topics:
                if topic not in weak_set:
                    profile.weak_topics.append(topic)
                    weak_set.add(topic)
                    changed = True
                    logger.info("[PROFILE] Weak topic marked: %s", topic)

        detected_level = _detect_level(user_text)
        if detected_level and detected_level != profile.level:
            profile.level = detected_level
            changed = True
            logger.info("[PROFILE] Level updated: %s", detected_level)

        detected_style = _detect_style_preference(user_text)
        if detected_style and detected_style != profile.preferred_style:
            profile.preferred_style = detected_style
            changed = True
            logger.info("[PROFILE] Style preference updated: %s", detected_style)

        if changed or not session_id:
            if not session_id:
                self._profile = profile
                self._save()
            else:
                profile_dict = profile.to_dict()
                await self.save_to_state_store(session_id, profile_dict)
                if self.db_manager:
                    import asyncio
                    asyncio.create_task(self.db_manager.save_student_profile(session_id, profile_dict))

    async def update_name(self, name: str, session_id: Optional[str] = None) -> None:
        profile = await self.get_profile(session_id)
        if name and name != profile.name:
            profile.name = name
            if not session_id:
                self._profile = profile
                self._save()
            else:
                profile_dict = profile.to_dict()
                await self.save_to_state_store(session_id, profile_dict)
                if self.db_manager:
                    import asyncio
                    asyncio.create_task(self.db_manager.save_student_profile(session_id, profile_dict))
            logger.info("[PROFILE] Name updated: %s", name)

    async def increment_session_count(self, session_id: Optional[str] = None) -> None:
        profile = await self.get_profile(session_id)
        profile.session_count += 1
        if not session_id:
            self._profile = profile
            self._save()
        else:
            profile_dict = profile.to_dict()
            await self.save_to_state_store(session_id, profile_dict)
            if self.db_manager:
                import asyncio
                asyncio.create_task(self.db_manager.save_student_profile(session_id, profile_dict))

    async def set_level(self, level: str, session_id: Optional[str] = None) -> None:
        if level in ("beginner", "intermediate", "advanced"):
            profile = await self.get_profile(session_id)
            profile.level = level
            if not session_id:
                self._profile = profile
                self._save()
            else:
                profile_dict = profile.to_dict()
                await self.save_to_state_store(session_id, profile_dict)
                if self.db_manager:
                    import asyncio
                    asyncio.create_task(self.db_manager.save_student_profile(session_id, profile_dict))
            logger.info("[PROFILE] Level manually set: %s", level)

    def _load(self) -> StudentProfile:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("[PROFILE] Loaded from: %s", self._path)
                return StudentProfile.from_dict(data)
        except Exception as exc:
            logger.warning("[PROFILE] Load failed (%s), using defaults.", exc)
        profile = StudentProfile.from_dict(_DEFAULT_PROFILE)
        self._profile = profile
        self._save()
        logger.info("[PROFILE] Default profile created at: %s", self._path)
        return profile

    def _save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(self._profile.to_dict(), f, indent=2, ensure_ascii=False)
                logger.debug("[PROFILE] Saved to: %s", self._path)
            except Exception as exc:
                logger.warning("[PROFILE] Save failed: %s", exc)
