"""
EduMentor Agent Layer — Knowledge Router

Decides whether external knowledge retrieval (RAG) is needed before
generating an LLM response.

Current implementation:
  - Rule-based routing (intent + keyword signals)
  - Zero latency — no LLM call
  - retrieve() stub ready for future RAG integration

Routing logic:
  - Most intents (CONCEPT_EXPLANATION, CODE_HELP, etc.) need NO retrieval
  - PDF_QUESTION, PROJECT_HELP with doc keywords → use RAG
  - retrieve() returns None until a RAG backend is wired up

Future upgrade:
  Implement a concrete RAGBackend (ChromaDB, Qdrant, etc.) and call
  retrieve() with the reformulated query. The KnowledgeRouter interface
  remains unchanged.

Pipeline position:
  AgentController → KnowledgeRouter.route() → KnowledgeRoute
  If use_rag: KnowledgeRouter.retrieve() → retrieved_docs → PromptBuilder
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from agent.models import Intent, KnowledgeRoute, KnowledgeSource

logger = logging.getLogger("edumentor.agent.knowledge_router")


# ─────────────────────────────────────────────────────────────────────────────
# RAG Backend Protocol (future)
# ─────────────────────────────────────────────────────────────────────────────

class RAGBackend:
    """
    Abstract base class for retrieval backends.

    To add RAG support:
      1. Subclass RAGBackend
      2. Implement retrieve()
      3. Set it via KnowledgeRouter.set_backend()
    """

    def retrieve(self, query: str, source: KnowledgeSource) -> Optional[str]:
        """
        Retrieve relevant text chunks for a query.

        Args:
            query:  Reformulated retrieval query.
            source: Which data source to query.

        Returns:
            Retrieved text (may be multi-chunk), or None if unavailable.
        """
        # Stub — returns None until a real backend is wired
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Intents that always require retrieval
# ─────────────────────────────────────────────────────────────────────────────

# These intents unconditionally trigger RAG (when a backend is available)
_ALWAYS_RAG_INTENTS = {
    Intent.PDF_QUESTION,
}

# These intents conditionally use RAG based on keyword signals
_CONDITIONAL_RAG_INTENTS = {
    Intent.PROJECT_HELP,
    Intent.FOLLOW_UP,
}

# Keywords in user text that suggest document retrieval is needed
_DOCUMENT_KEYWORDS = re.compile(
    r"\b(pdf|document|my notes|my file|uploaded|page \d+|in the doc|"
    r"from the file|according to|you can see|the attachment)\b",
    re.IGNORECASE,
)

# Keywords suggesting project-specific knowledge retrieval
_PROJECT_KEYWORDS = re.compile(
    r"\b(my project|my code|my file|my repository|my repo|"
    r"the codebase|our system|our app|my app)\b",
    re.IGNORECASE,
)


class KnowledgeRouter:
    """
    Routes queries to the appropriate knowledge source.

    Determines whether RAG retrieval is needed and, if so,
    reformulates the query and retrieves relevant documents.

    Usage:
        router = KnowledgeRouter()
        route  = router.route(intent, user_text)
        docs   = router.retrieve(route, user_text) if route.use_rag else None
    """

    def __init__(self) -> None:
        self._backend: RAGBackend = RAGBackend()  # No-op stub by default
        logger.info("[OK] KnowledgeRouter ready (RAG backend: stub).")

    def set_backend(self, backend: RAGBackend) -> None:
        """
        Swap in a real RAG backend.

        Args:
            backend: A concrete RAGBackend implementation.
        """
        self._backend = backend
        logger.info("KnowledgeRouter backend upgraded to: %s", type(backend).__name__)

    # ─────────────────────────────────────────────────────────────────────────
    # Routing Decision
    # ─────────────────────────────────────────────────────────────────────────

    def route(self, intent: Intent, user_text: str) -> KnowledgeRoute:
        """
        Decide whether external retrieval is needed for this query.

        Args:
            intent:    The classified intent for this turn.
            user_text: The raw user transcript.

        Returns:
            KnowledgeRoute indicating whether RAG is needed and what source.
        """
        # ── Unconditional RAG intents ────────────────────────────────────────
        if intent in _ALWAYS_RAG_INTENTS:
            source = self._detect_source(user_text)
            query  = self._reformulate_query(user_text, intent)
            logger.info(
                "[ROUTE] intent=%s → use_rag=True source=%s",
                intent.value, source.value
            )
            return KnowledgeRoute(use_rag=True, source=source, query=query)

        # ── Conditional RAG intents (keyword-gated) ──────────────────────────
        if intent in _CONDITIONAL_RAG_INTENTS:
            if _DOCUMENT_KEYWORDS.search(user_text) or _PROJECT_KEYWORDS.search(user_text):
                source = self._detect_source(user_text)
                query  = self._reformulate_query(user_text, intent)
                logger.info(
                    "[ROUTE] intent=%s + keyword → use_rag=True source=%s",
                    intent.value, source.value
                )
                return KnowledgeRoute(use_rag=True, source=source, query=query)

        # ── No retrieval needed ──────────────────────────────────────────────
        logger.debug("[ROUTE] intent=%s → use_rag=False", intent.value)
        return KnowledgeRoute.no_retrieval()

    # ─────────────────────────────────────────────────────────────────────────
    # Retrieval (calls backend)
    # ─────────────────────────────────────────────────────────────────────────

    def retrieve(self, route: KnowledgeRoute, user_text: str) -> Optional[str]:
        """
        Retrieve relevant documents using the configured backend.

        Returns None if route.use_rag is False or backend returns nothing.

        Args:
            route:     The routing decision (must have use_rag=True).
            user_text: Original user text (for logging).

        Returns:
            Retrieved text string, or None.
        """
        if not route.use_rag:
            return None

        query = route.query or user_text
        logger.info(
            "[RETRIEVE] source=%s query=%r",
            route.source.value, query[:60]
        )

        try:
            docs = self._backend.retrieve(query, route.source)
            if docs:
                logger.info("[RETRIEVE] Got %d chars of context.", len(docs))
            else:
                logger.info("[RETRIEVE] Backend returned no documents.")
            return docs
        except Exception as exc:
            logger.exception("[RETRIEVE] Backend error: %s", exc)
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_source(self, user_text: str) -> KnowledgeSource:
        """Heuristically determine which source to query."""
        text_lower = user_text.lower()

        if any(k in text_lower for k in ["pdf", "document", "page", "from the file", "uploaded"]):
            return KnowledgeSource.PDF

        if any(k in text_lower for k in ["my notes", "notes", "my file"]):
            return KnowledgeSource.NOTES

        # Default to PDF for project/general RAG
        return KnowledgeSource.PDF

    def _reformulate_query(self, user_text: str, intent: Intent) -> str:
        """
        Optionally reformulate the user query for better retrieval.

        For now, returns the user text as-is. Future: use LLM to
        rewrite the query for better semantic search.
        """
        # Future: "explain page 3" → "content of page 3"
        return user_text.strip()
