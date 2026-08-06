"""
backend/agent/hesitation_composer.py

Composes context-aware help offers or generic fallbacks when pure filler/hesitation
is detected. Avoids immediate repetition and respects session-level cooldowns.
"""

from __future__ import annotations

import time
import random
from dataclasses import dataclass
from typing import Dict, List, Optional
from agent.hesitation_detector import HesitationSignal


@dataclass
class HesitationConfig:
    enabled: bool = False
    cooldown_s: float = 8.0
    recent_history_size: int = 4


class HesitationComposer:
    def __init__(self, config: Optional[HesitationConfig] = None) -> None:
        self.config = config or HesitationConfig()
        self.last_hesitation_time: Dict[str, float] = {}
        self.recent_phrases: Dict[str, List[str]] = {}

        # Curated list of generic fallback helper phrases
        self.generic_phrases = [
            "No worries, want me to explain it a different way?",
            "Would a visual help?",
            "Take your time! What part can I clear up?",
            "Need a hand with where to start?",
        ]

        # Topic to subtopics mapping for disambiguation offers
        self.topic_subtopics = {
            "recursion": ["the base case", "the stack frames", "how the calls unwind"],
            "sorting": ["the partition logic", "the swap operations", "the recursive division"],
            "linked_lists": ["node traversal", "pointer manipulation", "memory allocation"],
            "trees": ["root nodes", "traversal algorithms", "balancing height"],
            "graphs": ["depth-first search", "breadth-first search", "adjacency lists"],
        }

        # Templates for topic-specific hesitation offers
        self.topic_templates = [
            "No worries, is it the {sub1} part or {sub2}?",
            "Take your time! Are you thinking about {sub1} or {sub2}?",
            "No problem, do you want to talk about {sub1} or {sub2}?",
        ]

    def compose(
        self,
        session_id: str,
        signal: HesitationSignal,
        current_topic: Optional[str] = None,
        candidate_subtopics: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Compose a response guiding the student based on active topic or low-specificity fallback.
        Respects cooldown constraints.
        """
        if not self.config.enabled:
            return None

        if not signal.detected:
            return None

        now = time.time()
        last_time = self.last_hesitation_time.get(session_id, 0.0)
        if now - last_time < self.config.cooldown_s:
            return None

        # Check topic-specific availability
        subtopics = None
        if candidate_subtopics and len(candidate_subtopics) >= 2:
            subtopics = candidate_subtopics
        elif current_topic:
            norm_topic = current_topic.lower().strip().replace(" ", "_").replace("-", "_")
            if norm_topic in self.topic_subtopics:
                subtopics = self.topic_subtopics[norm_topic]

        phrase = None
        if subtopics and len(subtopics) >= 2:
            # Pick 2 distinct subtopics
            chosen_subs = random.sample(subtopics, 2)
            sub1, sub2 = chosen_subs[0], chosen_subs[1]
            
            # Pick a template
            template = random.choice(self.topic_templates)
            phrase = template.format(sub1=sub1, sub2=sub2)
        else:
            # Fallback to generic phrase pool
            pool = self.generic_phrases
            history = self.recent_phrases.setdefault(session_id, [])
            available_phrases = [p for p in pool if p not in history]
            if not available_phrases:
                available_phrases = pool
            phrase = random.choice(available_phrases)
            
            # Anti-repetition tracking
            history.append(phrase)
            if len(history) > self.config.recent_history_size:
                history.pop(0)

        # Update last fired time
        self.last_hesitation_time[session_id] = now
        return phrase

    def remove_session(self, session_id: str) -> None:
        """Remove session data to prevent memory leak."""
        self.last_hesitation_time.pop(session_id, None)
        self.recent_phrases.pop(session_id, None)
