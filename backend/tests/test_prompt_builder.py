"""
Tests — Prompt Builder

Tests message structure, system prompt sections, and intent template injection.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agent.prompt_builder import PromptBuilder
from agent.models import (
    AgentContext, Emotion, EmotionResult, Intent, KnowledgeRoute,
    MemoryTurn, SessionSummary, StudentProfile,
)


@pytest.fixture
def builder():
    return PromptBuilder()


def make_context(**kwargs) -> AgentContext:
    """Helper to create a minimal AgentContext with overrides."""
    defaults = dict(
        session_id="test-session",
        user_text="What is recursion?",
        intent=Intent.CONCEPT_EXPLANATION,
        emotion=EmotionResult.neutral(),
        history=[],
        session_summary=None,
        profile=None,
        knowledge_route=KnowledgeRoute.no_retrieval(),
        interrupt_state=None,
        retrieved_docs=None,
        safety_flags={},
    )
    defaults.update(kwargs)
    return AgentContext(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Message structure
# ─────────────────────────────────────────────────────────────────────────────

def test_messages_always_start_with_system(builder):
    ctx = make_context()
    messages = builder.build_messages(ctx)
    assert messages[0]["role"] == "system"


def test_messages_end_with_user(builder):
    ctx = make_context(user_text="Explain loops")
    messages = builder.build_messages(ctx)
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Explain loops"


def test_history_injected_as_alternating_roles(builder):
    history = [
        MemoryTurn(user="What is a list?", assistant="A list is a collection of items."),
        MemoryTurn(user="And a tuple?", assistant="A tuple is immutable."),
    ]
    ctx = make_context(history=history)
    messages = builder.build_messages(ctx)
    # static_system (1) + dynamic_system (2) + 2 * history turns (4) + current_user (1) = 7
    assert len(messages) == 7
    assert messages[2]["role"] == "user"
    assert messages[3]["role"] == "assistant"


def test_rag_context_injected_as_system(builder):
    ctx = make_context(retrieved_docs="Page 3: Sorting algorithms include bubble sort.")
    messages = builder.build_messages(ctx)
    rag_messages = [m for m in messages if m["role"] == "system" and "REFERENCE MATERIAL" in m["content"]]
    assert len(rag_messages) == 1


# ─────────────────────────────────────────────────────────────────────────────
# System prompt contents
# ─────────────────────────────────────────────────────────────────────────────

def test_base_system_prompt_always_present(builder):
    ctx = make_context()
    messages = builder.build_messages(ctx)
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "EduMentor" in system
    assert "markdown" in system.lower()


def test_student_profile_injected(builder):
    profile = StudentProfile(name="Praneet", level="beginner")
    ctx = make_context(profile=profile)
    messages = builder.build_messages(ctx)
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "Praneet" in system
    assert "beginner" in system.lower()


def test_level_modifier_injected(builder):
    profile = StudentProfile(level="intermediate")
    ctx = make_context(profile=profile)
    messages = builder.build_messages(ctx)
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "INTERMEDIATE" in system.upper() or "intermediate" in system.lower()


def test_session_summary_injected(builder):
    summary = SessionSummary(
        session_id="test",
        project="Sentiment Analysis",
        goal="Build AI tutor",
        current_topic="recursion",
    )
    ctx = make_context(session_summary=summary)
    messages = builder.build_messages(ctx)
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "Sentiment Analysis" in system


def test_intent_template_injected(builder):
    ctx = make_context(intent=Intent.QUIZ_REQUEST)
    messages = builder.build_messages(ctx)
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "quiz" in system.lower() or "question" in system.lower()


def test_emotion_instruction_injected_for_frustrated(builder):
    emotion = EmotionResult(emotion=Emotion.FRUSTRATED, confidence=0.95, trigger_phrase="I don't get it")
    ctx = make_context(emotion=emotion)
    messages = builder.build_messages(ctx)
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "frustrated" in system.lower() or "patient" in system.lower() or "encouraging" in system.lower()


def test_bridge_instruction_injected_when_present(builder):
    ctx = make_context(safety_flags={"bridge_instruction": "[INTERRUPTION CONTEXT] You were explaining recursion"})
    messages = builder.build_messages(ctx)
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "INTERRUPTION CONTEXT" in system


def test_weak_topics_injected(builder):
    profile = StudentProfile(weak_topics=["Recursion", "Dynamic Programming"])
    ctx = make_context(profile=profile)
    messages = builder.build_messages(ctx)
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "Recursion" in system or "recursion" in system.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Safety refusal messages
# ─────────────────────────────────────────────────────────────────────────────

def test_safety_refusal_messages_structure(builder):
    messages = builder.build_safety_refusal_messages(
        reason="exam_cheating",
        refusal_text="I can help you learn, not do it for you."
    )
    assert messages[0]["role"] == "system"
    assert "I can help you learn" in messages[0]["content"]
    assert messages[1]["role"] == "user"
