import sys
import os
import pytest
from unittest import mock
from datetime import datetime, timezone, timedelta
from fsrs import Card, Rating, State

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.mastery_scheduler import slugify_concept, MasteryScheduler, RecallGrader

def test_slugify_concept():
    # Empty / punctuation-only
    assert slugify_concept("") == "general"
    assert slugify_concept("!!!") == "general"
    # Basic cases
    assert slugify_concept("Data Structures") == "data_structures"
    assert slugify_concept("Machine Learning") == "machine_learning"
    # Mixed punctuation and already slugged
    assert slugify_concept("already_slugged") == "already_slugged"
    assert slugify_concept("  Some...Topic!!!  ") == "some_topic"

@pytest.mark.asyncio
async def test_mastery_scheduler_record_review():
    fake_db = mock.AsyncMock()
    # Mock get_or_create_card_row to return a fresh row (matching DB structure)
    now_tz = datetime.now(timezone.utc)
    fake_row = {
        "id": 42,
        "user_id": "dummy_user",
        "concept_slug": "recursion",
        "state": 1,  # Learning
        "step": 0,
        "stability": 2.0,
        "difficulty": 5.0,
        "due": now_tz,
        "last_review": None,
        "reps": 0
    }
    
    fake_db.get_or_create_card_row.return_value = fake_row
    
    scheduler = MasteryScheduler(fake_db)
    
    # Review: Good
    await scheduler.record_review("dummy_user", "recursion", Rating.Good)
    
    # Verify DB save was called
    fake_db.save_card_review.assert_called_once()
    kwargs = fake_db.save_card_review.call_args[1]
    
    # Reps are handled in SQL query (reps = reps + 1)
    # The new state should be returned from FSRS scheduler.
    assert "state" in kwargs
    assert "due" in kwargs
    
    # The due date should have advanced (due > now)
    assert kwargs["due"] > now_tz

@pytest.mark.asyncio
async def test_due_timestamp_advancement():
    fake_db = mock.AsyncMock()
    now_tz = datetime.now(timezone.utc)
    fake_row = {
        "id": 42,
        "user_id": "dummy_user",
        "concept_slug": "recursion",
        "state": 1,
        "step": 0,
        "stability": 2.0,
        "difficulty": 5.0,
        "due": now_tz,
        "last_review": now_tz - timedelta(days=1),
        "reps": 1
    }
    
    fake_db.get_or_create_card_row.return_value = fake_row
    scheduler = MasteryScheduler(fake_db)
    
    # Review: Again (wrong answer)
    await scheduler.record_review("dummy_user", "recursion", Rating.Again)
    fake_db.save_card_review.assert_called_once()
    again_due = fake_db.save_card_review.call_args[1]["due"]
    
    fake_db.reset_mock()
    
    # Review: Good
    await scheduler.record_review("dummy_user", "recursion", Rating.Good)
    good_due = fake_db.save_card_review.call_args[1]["due"]
    
    # due advances further for Good than Again
    assert good_due > again_due

@pytest.mark.asyncio
async def test_recall_grader():
    mock_llm = mock.AsyncMock()
    grader = RecallGrader(mock_llm)
    
    # Test Again
    mock_llm.get_completion.return_value = "Again"
    assert await grader.grade("Q", "A") == Rating.Again
    
    # Test Hard
    mock_llm.get_completion.return_value = "hard"
    assert await grader.grade("Q", "A") == Rating.Hard
    
    # Test Good
    mock_llm.get_completion.return_value = "good "
    assert await grader.grade("Q", "A") == Rating.Good
    
    # Test Easy
    mock_llm.get_completion.return_value = " EASY"
    assert await grader.grade("Q", "A") == Rating.Easy
    
    # Test fallback
    mock_llm.get_completion.return_value = "garbage content"
    assert await grader.grade("Q", "A") == Rating.Hard
    
    mock_llm.get_completion.return_value = ""
    assert await grader.grade("Q", "A") == Rating.Hard

@pytest.mark.asyncio
async def test_boredom_triggers_recall():
    import uuid
    from agent.controller import AgentController
    
    mock_llm = mock.AsyncMock()
    async def mock_stream(*args, **kwargs):
        yield "response "
        yield "token"
    mock_llm.stream_tokens_from_messages = mock_stream
    mock_llm.last_usage = {"prompt_tokens": 10, "prompt_tokens_details": {"cached_tokens": 5}}
    mock_memory = mock.MagicMock()
    mock_summarizer = mock.MagicMock()
    mock_profile = mock.MagicMock()
    mock_interrupt = mock.MagicMock()
    mock_db = mock.AsyncMock()
    # Set pool to None so AccessControl falls back to memory
    mock_db.pool = None
    
    # Enable mastery scheduler
    with mock.patch("config.Config.MASTERY_SCHEDULER_ENABLED", True), \
         mock.patch("config.Config.MASTERY_DUE_CHECK_LIMIT", 1), \
         mock.patch("agent.access_control.AccessControl.verify_session_ownership", return_value=True):
         
        controller = AgentController(
            llm_engine=mock_llm,
            memory_manager=mock_memory,
            session_summarizer=mock_summarizer,
            profile_manager=mock_profile,
            interrupt_manager=mock_interrupt,
            db_manager=mock_db
        )
        
        # When session has history, but student is bored:
        from agent.models import MemoryTurn
        mock_memory.get_session.return_value = [
            MemoryTurn(user="hello", assistant="world", intent="CONCEPT_EXPLANATION", emotion="NEUTRAL")
        ]
        
        # Setup mastery mock returning a due concept
        controller._mastery = mock.AsyncMock()
        controller._mastery.get_due_concepts.return_value = [{"concept_slug": "arrays"}]
        
        # Mock dialogue manager build_context to return a real AgentContext
        from agent.models import AgentContext, EmotionResult, Intent, Emotion
        dummy_context = AgentContext(
            session_id="session_bored",
            user_text="this is so boring",
            intent=Intent.CONCEPT_EXPLANATION,
            emotion=EmotionResult(emotion=Emotion.BORED, confidence=1.0),
            history=[],
            session_summary=None,
            profile=None,
            knowledge_route=mock.MagicMock(),
            interrupt_state=None,
            retrieved_docs=None,
            is_interrupted=False,
            safety_flags={},
            voice_style=None
        )
        controller._dialogue_manager = mock.MagicMock()
        controller._dialogue_manager.build_context.return_value = dummy_context
        
        # Classify and run stream (we mock _run_pre_guardrail and classify to keep it isolated)
        controller._run_pre_guardrail = mock.AsyncMock(return_value=("this is boring", False, None, None))
        controller._intent_classifier.classify = mock.AsyncMock()
        
        # We need to mock database and user UUIDs
        controller._to_uuid = mock.MagicMock(return_value=uuid.uuid4())
        controller._db_manager.fetch_history = mock.AsyncMock(return_value=[])
        
        # Run stream and check if get_due_concepts is called
        async for chunk in controller.stream("this is boring", "session_bored", user_id="user_bored"):
            pass
            
        controller._mastery.get_due_concepts.assert_called_once()
