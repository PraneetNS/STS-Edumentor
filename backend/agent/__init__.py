"""
EduMentor Agent Layer — Package Init

Exports the primary public API for the agent layer.

Usage from main.py:
    from agent import AgentController, InterruptManager
"""

from agent.controller       import AgentController
from agent.interrupt_manager import InterruptManager
from agent.memory_manager   import MemoryManager, InMemoryBackend, SQLiteBackend, RedisBackend, get_backend
from agent.session_summarizer import SessionSummarizer
from agent.memory_store    import MemoryRecord, RecalledMemory, EmbeddingFn, VectorStore
from agent.memory_indexer  import MemoryIndexer
from agent.memory_retriever import MemoryRetriever, RetrievalConfig, format_recall_context
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
    # Cross-session memory
    "MemoryRecord",
    "RecalledMemory",
    "EmbeddingFn",
    "VectorStore",
    "MemoryIndexer",
    "MemoryRetriever",
    "RetrievalConfig",
    "format_recall_context",
    # Main classes
    "AgentController",
    "InterruptManager",
    "MemoryManager",
    "InMemoryBackend",
    "SQLiteBackend",
    "RedisBackend",
    "get_backend",
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
