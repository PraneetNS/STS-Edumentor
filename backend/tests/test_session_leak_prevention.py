import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from agent.celebration_composer import CelebrationComposer, CelebrationConfig
from agent.positive_signal_detector import PositiveSignal, PositiveEmotion
from agent.controller import AgentController
from agent.memory_manager import MemoryManager
from agent.models import StudentProfile


def test_celebration_composer_leak_and_cleanup():
    composer = CelebrationComposer(
        CelebrationConfig(
            enabled=True,
            min_speed_boost=0.03,
            max_speed_boost=0.12,
            cooldown_s=0.2,
            recent_history_size=2,
        )
    )

    # 1. Simulate session activity
    sig = PositiveSignal(emotion=PositiveEmotion.EXCITED, intensity=0.8, reason="test")
    composer.compose("session_A", sig)
    composer.compose("session_B", sig)

    # Assert that states have accumulated for both sessions (leak before fix)
    assert "session_A" in composer.last_celebration_time
    assert "session_B" in composer.last_celebration_time
    assert "session_A" in composer.recent_phrases
    assert "session_B" in composer.recent_phrases

    # 2. Cleanup session A
    composer.remove_session("session_A")

    # Assert session A is deleted but session B remains (cleanup verification)
    assert "session_A" not in composer.last_celebration_time
    assert "session_B" in composer.last_celebration_time
    assert "session_A" not in composer.recent_phrases
    assert "session_B" in composer.recent_phrases

    # 3. Cleanup session B
    composer.remove_session("session_B")
    assert "session_B" not in composer.last_celebration_time
    assert "session_B" not in composer.recent_phrases


def test_agent_controller_leak_and_cleanup():
    # Build mocked dependencies
    mock_llm = MagicMock()
    mock_memory = MagicMock()
    mock_summarizer = MagicMock()
    mock_profile = MagicMock()
    mock_interrupt = MagicMock()
    mock_db = MagicMock()

    ctrl = AgentController(
        llm_engine=mock_llm,
        memory_manager=mock_memory,
        session_summarizer=mock_summarizer,
        profile_manager=mock_profile,
        interrupt_manager=mock_interrupt,
        intent_enabled=False,
        safety_enabled=False,
        db_manager=mock_db,
    )

    # Populate session state
    ctrl._turn_state["session_1"] = {"last_topic": "recursion", "partial_response": "ok"}
    ctrl._session_names["session_1"] = "Edi-Tutor"
    ctrl._turn_state["session_2"] = {"last_topic": "sorting", "partial_response": "yes"}
    ctrl._session_names["session_2"] = "Edi-Mentor"

    assert "session_1" in ctrl._turn_state
    assert "session_2" in ctrl._turn_state
    assert "session_1" in ctrl._session_names
    assert "session_2" in ctrl._session_names

    # Remove session 1
    ctrl.remove_session("session_1")

    assert "session_1" not in ctrl._turn_state
    assert "session_2" in ctrl._turn_state
    assert "session_1" not in ctrl._session_names
    assert "session_2" in ctrl._session_names

    # Remove session 2
    ctrl.remove_session("session_2")

    assert "session_2" not in ctrl._turn_state
    assert "session_2" not in ctrl._session_names
