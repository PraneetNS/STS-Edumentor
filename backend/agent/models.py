"""
EduMentor Agent Layer — Core Data Models

All shared dataclasses, enums, and type definitions used across the agent layer.
This module has ZERO external dependencies (stdlib only) and is the foundation
that every other agent module imports from.

Design principles:
  - Plain Python dataclasses (no Pydantic required) for minimal overhead.
  - Enums for all categorical values to prevent typos and enable IDE completion.
  - Every field has a clear docstring or inline comment.
  - All classes are frozen where mutation is undesirable (SafetyResult, IntentResult, EmotionResult).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Intent Enum
# ─────────────────────────────────────────────────────────────────────────────

class Intent(str, Enum):
    """
    All supported dialogue intents recognised by the IntentClassifier.

    Each intent maps to a specific prompting strategy in PromptBuilder
    and a specific context-building strategy in DialogueManager.
    """
    CONCEPT_EXPLANATION = "CONCEPT_EXPLANATION"   # "What is recursion?"
    CODE_HELP           = "CODE_HELP"             # "Help me write a function"
    DEBUGGING           = "DEBUGGING"             # "Why is my code broken?"
    QUIZ_REQUEST        = "QUIZ_REQUEST"          # "Test me on sorting"
    REPEAT_LAST         = "REPEAT_LAST"           # "Can you say that again?"
    SIMPLIFY            = "SIMPLIFY"              # "Explain it simpler"
    FOLLOW_UP           = "FOLLOW_UP"             # "Tell me more about that"
    OFF_TOPIC           = "OFF_TOPIC"             # "What's the weather?"
    GREETING            = "GREETING"              # "Hello!", "Hi there"
    THANKS              = "THANKS"                # "Thank you!"
    PDF_QUESTION        = "PDF_QUESTION"          # "What does page 3 say?"
    PROJECT_HELP        = "PROJECT_HELP"          # "Help me with my project"
    CAREER_GUIDANCE     = "CAREER_GUIDANCE"       # "How do I get a job?"
    UNSAFE              = "UNSAFE"                # Caught by safety guard


# ─────────────────────────────────────────────────────────────────────────────
# Safety Models
# ─────────────────────────────────────────────────────────────────────────────

class SafetyCategory(str, Enum):
    """Categories of unsafe content that the SafetyGuard can detect."""
    SELF_HARM         = "self_harm"
    VIOLENCE          = "violence"
    ADULT             = "adult"
    MALWARE           = "malware"
    CREDENTIAL_THEFT  = "credential_theft"
    PHISHING          = "phishing"
    PRIVACY_ABUSE     = "privacy_abuse"
    EXAM_CHEATING     = "exam_cheating"
    PROMPT_INJECTION  = "prompt_injection"
    JAILBREAK         = "jailbreak_attempt"


@dataclass(frozen=True)
class SafetyResult:
    """
    Result of a safety check (input or output).

    Attributes:
        allowed:  True if content passed safety checks.
        reason:   SafetyCategory name if blocked, else None.
        details:  Optional additional context (matched phrase etc.).
    """
    allowed: bool
    reason:  Optional[str]  = None   # e.g. "credential_theft"
    details: Optional[str]  = None   # e.g. matched phrase

    @classmethod
    def safe(cls) -> "SafetyResult":
        """Convenience constructor for a passing result."""
        return cls(allowed=True)

    @classmethod
    def blocked(cls, reason: SafetyCategory, details: str = "") -> "SafetyResult":
        """Convenience constructor for a blocked result."""
        return cls(allowed=False, reason=reason.value, details=details)


# ─────────────────────────────────────────────────────────────────────────────
# Intent Classification Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IntentResult:
    """
    Result of intent classification.

    Attributes:
        intent:        The detected Intent enum value.
        needs_history: Whether memory context should be injected into the prompt.
        confidence:    Estimated confidence score [0.0, 1.0].
        raw_json:      Raw JSON string returned by the LLM (for debugging).
    """
    intent:        Intent
    needs_history: bool
    confidence:    float
    raw_json:      Optional[str] = None

    @classmethod
    def fallback(cls) -> "IntentResult":
        """Default fallback used when classification fails."""
        return cls(
            intent=Intent.CONCEPT_EXPLANATION,
            needs_history=False,
            confidence=0.0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Conversation State Models
# ─────────────────────────────────────────────────────────────────────────────

class ConversationState(str, Enum):
    """All possible conversation states in the real-time voice pipeline."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    ERROR = "ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# Emotion Detection Models
# ─────────────────────────────────────────────────────────────────────────────

class Emotion(str, Enum):
    """All detectable emotional states from transcribed speech."""
    FRUSTRATED = "frustrated"
    CONFUSED   = "confused"
    CONFIDENT  = "confident"
    HAPPY      = "happy"
    BORED      = "bored"
    NEUTRAL    = "neutral"


@dataclass(frozen=True)
class EmotionResult:
    """
    Result of emotion detection on user text.

    Attributes:
        emotion:        Detected emotional state.
        confidence:     Match confidence [0.0, 1.0].
        trigger_phrase: The exact phrase or pattern that triggered detection.
    """
    emotion:        Emotion
    confidence:     float
    trigger_phrase: str = ""
    features:       Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def neutral(cls) -> "EmotionResult":
        """Default neutral emotion when nothing is detected."""
        return cls(emotion=Emotion.NEUTRAL, confidence=1.0, trigger_phrase="")


# ─────────────────────────────────────────────────────────────────────────────
# Interruption Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InterruptState:
    """
    Saved state from a mid-speech interruption.

    This is stored before cancelling the LLM pipeline so the next
    DialogueManager call can inject a natural bridge instruction.

    Attributes:
        session_id:              The session that was interrupted.
        interrupted_response:    Partial LLM text that was being spoken.
        interrupted_at_fraction: How far through the response (0.0–1.0).
        topic:                   The topic being discussed at interruption time.
        was_mid_explanation:     True if the tutor was in the middle of explaining.
        timestamp:               Unix timestamp of the interruption.
    """
    session_id:              str
    interrupted_response:    str
    interrupted_at_fraction: float
    topic:                   str
    was_mid_explanation:     bool
    timestamp:               float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
# Session Summary Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SessionSummary:
    """
    Rolling compressed summary of the conversation history.

    Generated by SessionSummarizer every 10 turns. Injected into every
    prompt so context never disappears even after many turns.

    Attributes:
        session_id:       The session identifier.
        last_updated:     ISO timestamp of last summarization.
        turn_count:       Total number of turns processed so far.
        project:          Student's current project (if mentioned).
        goal:             Student's stated learning or project goal.
        progress:         Current progress on the goal.
        topics_covered:   List of topics already discussed.
        current_topic:    Most recently active topic.
        student_struggles: Topics/concepts the student is finding difficult.
        agreements:       Teaching style agreements made during the session.
    """
    session_id:        str
    last_updated:      str                    = ""
    turn_count:        int                    = 0
    project:           Optional[str]          = None
    goal:              Optional[str]          = None
    progress:          Optional[str]          = None
    topics_covered:    List[str]              = field(default_factory=list)
    current_topic:     Optional[str]          = None
    student_struggles: List[str]              = field(default_factory=list)
    agreements:        List[str]              = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict for JSON persistence."""
        return {
            "session_id":        self.session_id,
            "last_updated":      self.last_updated,
            "turn_count":        self.turn_count,
            "project":           self.project,
            "goal":              self.goal,
            "progress":          self.progress,
            "topics_covered":    self.topics_covered,
            "current_topic":     self.current_topic,
            "student_struggles": self.student_struggles,
            "agreements":        self.agreements,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSummary":
        """Deserialise from a plain dict (loaded from JSON)."""
        return cls(
            session_id        = data.get("session_id", ""),
            last_updated      = data.get("last_updated", ""),
            turn_count        = data.get("turn_count", 0),
            project           = data.get("project"),
            goal              = data.get("goal"),
            progress          = data.get("progress"),
            topics_covered    = data.get("topics_covered", []),
            current_topic     = data.get("current_topic"),
            student_struggles = data.get("student_struggles", []),
            agreements        = data.get("agreements", []),
        )

    def to_prompt_block(self) -> str:
        """
        Render the summary as a concise, LLM-readable context block.
        Injected near the top of the system prompt by PromptBuilder.
        """
        lines = ["[SESSION MEMORY]"]
        if self.project:
            lines.append(f"Student's project: {self.project}")
        if self.goal:
            lines.append(f"Goal: {self.goal}")
        if self.progress:
            lines.append(f"Progress so far: {self.progress}")
        if self.current_topic:
            lines.append(f"Current topic: {self.current_topic}")
        if self.topics_covered:
            lines.append(f"Topics already covered: {', '.join(self.topics_covered)}")
        if self.student_struggles:
            lines.append(f"Student struggles with: {', '.join(self.student_struggles)}")
        if self.agreements:
            lines.append(f"Teaching agreements: {'; '.join(self.agreements)}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Student Profile Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StudentProfile:
    """
    Persistent student profile loaded from / saved to disk.

    Attributes:
        name:             Student's name (personalizes responses).
        level:            Skill level: "beginner" | "intermediate" | "advanced"
        learning_topics:  Topics the student is actively learning.
        weak_topics:      Topics the student struggles with (auto-inferred).
        preferred_style:  Response style: "examples" | "theory" | "mixed"
        session_count:    Total number of sessions completed.
        discipline:       Selected discipline (e.g. cse, mech, eee)
        active_topics:    List of topics active in the current session
    """
    name:             str        = "Student"
    level:            str        = "beginner"
    learning_topics:  List[str]  = field(default_factory=list)
    weak_topics:      List[str]  = field(default_factory=list)
    preferred_style:  str        = "examples"
    session_count:    int        = 0
    discipline:       str        = "cse"
    active_topics:    List[str]  = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":            self.name,
            "level":           self.level,
            "learning_topics": self.learning_topics,
            "weak_topics":     self.weak_topics,
            "preferred_style": self.preferred_style,
            "session_count":   self.session_count,
            "discipline":      self.discipline,
            "active_topics":   self.active_topics,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudentProfile":
        return cls(
            name            = data.get("name", "Student"),
            level           = data.get("level", "beginner"),
            learning_topics = data.get("learning_topics", []),
            weak_topics     = data.get("weak_topics", []),
            preferred_style = data.get("preferred_style", "examples"),
            session_count   = data.get("session_count", 0),
            discipline      = data.get("discipline", "cse"),
            active_topics   = data.get("active_topics", []),
        )

    def to_prompt_block(self) -> str:
        """Render as a concise system-prompt block for PromptBuilder."""
        parts = [f"Student: {self.name}", f"Level: {self.level}"]
        if self.learning_topics:
            parts.append(f"Learning: {', '.join(self.learning_topics)}")
        if self.weak_topics:
            parts.append(f"Struggles with: {', '.join(self.weak_topics)}")
        parts.append(f"Preferred style: {self.preferred_style}")
        return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Memory Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MemoryTurn:
    """
    A single conversation turn stored in memory.

    Attributes:
        user:      The student's transcribed utterance.
        assistant: The assistant's full response text.
        timestamp: Unix timestamp of the turn.
        intent:    The classified intent for this turn (optional).
        emotion:   The detected emotion for this turn (optional).
    """
    user:      str
    assistant: str
    timestamp: float = field(default_factory=time.time)
    intent:    Optional[str] = None
    emotion:   Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user":      self.user,
            "assistant": self.assistant,
            "timestamp": self.timestamp,
            "intent":    self.intent,
            "emotion":   self.emotion,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Routing Models
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeSource(str, Enum):
    """Available external knowledge sources for retrieval."""
    NONE        = "none"
    PDF         = "pdf"
    NOTES       = "notes"
    WEB_SEARCH  = "web_search"   # Future
    VECTOR_DB   = "vector_db"    # Future


@dataclass(frozen=True)
class KnowledgeRoute:
    """
    Decision from the KnowledgeRouter about whether to retrieve external context.

    Attributes:
        use_rag: True if retrieval-augmented generation is needed.
        source:  Which knowledge source to query.
        query:   The reformulated retrieval query (may differ from user text).
    """
    use_rag: bool
    source:  KnowledgeSource = KnowledgeSource.NONE
    query:   Optional[str]   = None

    @classmethod
    def no_retrieval(cls) -> "KnowledgeRoute":
        return cls(use_rag=False, source=KnowledgeSource.NONE)


# ─────────────────────────────────────────────────────────────────────────────
# Agent Context — assembled by DialogueManager, consumed by PromptBuilder
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentContext:
    """
    Full assembled context passed from DialogueManager to PromptBuilder.

    This is the single object that carries all the information needed to
    construct the final prompt. Nothing else should be passed directly.

    Attributes:
        session_id:       WebSocket session identifier.
        user_text:        Raw user transcript.
        intent:           Classified intent.
        emotion:          Detected emotion.
        history:          Relevant memory turns (last N turns).
        session_summary:  Rolling session summary (may be None early in session).
        profile:          Student profile.
        knowledge_route:  Routing decision (RAG or not).
        interrupt_state:  Saved state from a prior interruption (may be None).
        retrieved_docs:   Retrieved text from RAG (may be None).
        safety_flags:     Dict of pre-computed safety signals (for borderline cases).
        is_interrupted:   True if this turn follows an interruption.
    """
    session_id:      str
    user_text:       str
    intent:          Intent                    = Intent.CONCEPT_EXPLANATION
    emotion:         EmotionResult             = field(default_factory=EmotionResult.neutral)
    history:         List[MemoryTurn]          = field(default_factory=list)
    session_summary: Optional[SessionSummary]  = None
    profile:         Optional[StudentProfile]  = None
    knowledge_route: KnowledgeRoute            = field(default_factory=KnowledgeRoute.no_retrieval)
    interrupt_state: Optional[InterruptState]  = None
    retrieved_docs:  Optional[str]             = None
    safety_flags:    Dict[str, Any]            = field(default_factory=dict)
    is_interrupted:  bool                      = False
    history_messages: List[Dict[str, str]]     = field(default_factory=list)
    voice_style:     Optional[str]             = None
    custom_name:     Optional[str]             = None



# ─────────────────────────────────────────────────────────────────────────────
# Agent Response — returned by AgentController
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentResponse:
    """
    Final response metadata returned by AgentController.

    The actual text content is streamed via AsyncIterator[str] separately.
    This carries the metadata about the turn for logging and memory saving.

    Attributes:
        session_id:      Session that produced this response.
        intent:          The intent used for this turn.
        emotion:         The emotion detected this turn.
        was_safe:        True if both input and output passed safety checks.
        safety_reason:   Blocked category if not safe.
        latency_ms:      Total time from transcript to first token (ms).
        full_text:       Accumulated full response text (set after streaming).
        used_rag:        Whether external retrieval was performed.
        was_interrupted: Whether this turn followed an interruption.
    """
    session_id:      str
    intent:          Intent          = Intent.CONCEPT_EXPLANATION
    emotion:         Emotion         = Emotion.NEUTRAL
    was_safe:        bool            = True
    safety_reason:   Optional[str]   = None
    latency_ms:      float           = 0.0
    full_text:       str             = ""
    used_rag:        bool            = False
    was_interrupted: bool            = False
