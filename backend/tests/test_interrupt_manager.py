"""
Tests — Interrupt Manager

Tests conversation stack push/pop, active thread tracking, and LLM bridge generation.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from agent.interrupt_manager import InterruptManager
from agent.interrupt_state import ConversationThread, ThreadStatus


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.enabled = True
    db.save_thread = AsyncMock()
    db.load_threads = AsyncMock(return_value=[])
    db.update_thread_status = AsyncMock()
    return db


@pytest.fixture
def manager(mock_db):
    return InterruptManager(db_manager=mock_db)


@pytest.mark.asyncio
async def test_active_thread_tracking(manager):
    session_id = "session-1"
    assert manager.get_active_thread(session_id) is None

    thread = ConversationThread(
        topic="recursion",
        original_question="what is recursion"
    )
    manager.set_active_thread(session_id, thread)

    assert manager.get_active_thread(session_id) == thread
    manager.clear_active_thread(session_id)
    assert manager.get_active_thread(session_id) is None


@pytest.mark.asyncio
async def test_barge_in_pushes_to_stack(manager, mock_db):
    session_id = "session-2"
    thread = ConversationThread(
        topic="stack depth",
        original_question="explain stack depth"
    )
    manager.set_active_thread(session_id, thread)

    await manager.on_barge_in(session_id)

    # Active thread is cleared after barge-in
    assert manager.get_active_thread(session_id) is None

    # Stack depth should be 1
    stack = manager.get_stack(session_id)
    assert await stack.depth() == 1
    assert await stack.peek_topic() == "stack depth"
    assert mock_db.save_thread.called


@pytest.mark.asyncio
async def test_pop_thread_restores_from_stack(manager, mock_db):
    session_id = "session-3"
    thread1 = ConversationThread(
        topic="topic-1",
        original_question="explain topic-1"
    )
    thread2 = ConversationThread(
        topic="topic-2",
        original_question="explain topic-2"
    )

    stack = manager.get_stack(session_id)
    await stack.push(thread1)
    await stack.push(thread2)

    assert await stack.depth() == 2
    
    popped = await manager.pop_thread(session_id)
    assert popped.topic == "topic-2"
    assert await stack.depth() == 1

    popped2 = await manager.pop_thread(session_id)
    assert popped2.topic == "topic-1"
    assert await stack.depth() == 0



@pytest.mark.asyncio
async def test_generate_resume_bridge_fallback(manager):
    thread = ConversationThread(
        topic="binary search",
        original_question="how does binary search work"
    )
    bridge = await manager.generate_resume_bridge(thread)
    # Since HTTP mock isn't configured, it should fallback safely
    assert "binary search" in bridge
