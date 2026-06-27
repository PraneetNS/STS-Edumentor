"""
EduMentor Agent Layer — Package Init

Exports the primary public API for the agent layer.

Usage from main.py:
    from agent import AgentController, InterruptManager
"""

from agent.controller       import AgentController
from agent.interrupt_manager import InterruptManager
from agent.memory_manager   import MemoryManager
from agent.session_summarizer import SessionSummarizer
from agent.student_profile  import StudentProfileManager
from agent.models           import (
    AgentContext,
    AgentResponse,
    Intent,
    Emotion,
    SafetyResult,
    IntentResult,
    EmotionResult,
    InterruptState,
    SessionSummary,
    StudentProfile,
    MemoryTurn,
    KnowledgeRoute,
)

# Security modules
from agent.access_control   import AccessControl
from agent.integrity_check  import (
    verify_model_integrity,
    verify_requirements_pinned,
    IntegrityError,
)
from agent.knowledge_router import sanitize_rag_content, ContentRejectedError

__all__ = [
    # Main classes
    "AgentController",
    "InterruptManager",
    "MemoryManager",
    "SessionSummarizer",
    "StudentProfileManager",
    # Data models
    "AgentContext",
    "AgentResponse",
    "Intent",
    "Emotion",
    "SafetyResult",
    "IntentResult",
    "EmotionResult",
    "InterruptState",
    "SessionSummary",
    "StudentProfile",
    "MemoryTurn",
    "KnowledgeRoute",
    # Security
    "AccessControl",
    "verify_model_integrity",
    "verify_requirements_pinned",
    "IntegrityError",
    "sanitize_rag_content",
    "ContentRejectedError",
]
