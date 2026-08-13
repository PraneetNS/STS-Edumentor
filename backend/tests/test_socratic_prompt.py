import pytest
import uuid
import logging
from unittest.mock import MagicMock
from agent.models import AgentContext, StudentProfile, SessionSummary
from agent.prompt_builder import PromptBuilder

@pytest.fixture
def builder():
    return PromptBuilder()

def test_socratic_prompt_fallback_defaults(builder):
    # Context with no course context or profile details
    context = AgentContext(
        session_id="test_session",
        user_text="hello",
        profile=None,
        session_summary=None
    )
    
    prompt = builder._render_socratic_prompt(context)
    
    # Check default placeholders are replaced correctly
    assert "{{student_name}}" not in prompt
    assert "{{course_title}}" not in prompt
    assert "{{course_code}}" not in prompt
    assert "{{current_module}}" not in prompt
    assert "{{module_number}}" not in prompt
    assert "{{last_session_summary}}" not in prompt
    
    # Defaults should be present
    assert "Student" in prompt
    assert "CYBERSEC101" in prompt
    assert "Cybersecurity Fundamentals" in prompt
    assert "Module 3: Network Security" in prompt
    assert "Firewalls: weak" in prompt
    assert "No recent session summary." in prompt

def test_socratic_prompt_custom_context(builder):
    profile = StudentProfile(name="Alice")
    # Correctly initialize SessionSummary with existing attributes
    session_summary = SessionSummary(
        session_id="test_session",
        current_topic="Reviewed basic network concepts."
    )
    student_course_ctx = [
        {
            "course_code": "CSE404",
            "course_title": "Distributed Systems",
            "current_module": "Module 1: Consensus",
            "module_number": 1,
            "kp_name": "Paxos Consensus",
            "status": "developing",
            "p_mastery": 0.65
        },
        {
            "course_code": "CSE404",
            "course_title": "Distributed Systems",
            "current_module": "Module 1: Consensus",
            "module_number": 1,
            "kp_name": "Raft Consensus",
            "status": "weak",
            "p_mastery": 0.35
        }
    ]
    
    context = AgentContext(
        session_id="test_session",
        user_text="hello",
        profile=profile,
        session_summary=session_summary,
        student_course_ctx=student_course_ctx
    )
    
    prompt = builder._render_socratic_prompt(context)
    
    assert "Alice" in prompt
    assert "CSE404" in prompt
    assert "Distributed Systems" in prompt
    assert "Module 1: Consensus" in prompt
    assert "Paxos Consensus: developing (mastery 0.65)" in prompt
    assert "Raft Consensus: weak (mastery 0.35)" in prompt
    assert "Current topic: Reviewed basic network concepts." in prompt

@pytest.mark.asyncio
async def test_database_schema_initialization(monkeypatch):
    # Monkeypatch logger.error to raise any exception caught in create_tables()
    # so we see the exact traceback in pytest failure logs
    def mock_log_error(msg, *args):
        formatted = msg % args if args else msg
        print(f"\nDB CREATE_TABLES EXCEPTION: {formatted}")
        raise Exception(formatted)
        
    monkeypatch.setattr(logging.getLogger("edumentor.agent.database"), "error", mock_log_error)

    # Mock pool and connection to check execute queries
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    
    # Mock connection acquire context manager
    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_conn
        async def __aexit__(self, exc_type, exc, tb):
            pass
            
    mock_pool.acquire.return_value = AsyncContextManagerMock()
    
    from agent.database import DatabaseManager
    db = DatabaseManager()
    db.pool = mock_pool
    db.enabled = True
    
    # We will spy on executed SQL strings
    executed_queries = []
    async def mock_execute(query, *args):
        executed_queries.append(query)
        
    mock_conn.execute = mock_execute
    
    # Directly test create_tables schema verification
    await db.create_tables()
    
    # Verify that new tables are created during initialization
    kp_created = any("CREATE TABLE IF NOT EXISTS knowledge_points" in q for q in executed_queries)
    mastery_created = any("CREATE TABLE IF NOT EXISTS student_mastery" in q for q in executed_queries)
    courses_created = any("CREATE TABLE IF NOT EXISTS courses" in q for q in executed_queries)
    modules_created = any("CREATE TABLE IF NOT EXISTS course_modules" in q for q in executed_queries)
    enrollments_created = any("CREATE TABLE IF NOT EXISTS enrollments" in q for q in executed_queries)
    view_created = any("CREATE OR REPLACE VIEW student_course_context" in q for q in executed_queries)
    
    assert kp_created is True
    assert mastery_created is True
    assert courses_created is True
    assert modules_created is True
    assert enrollments_created is True
    assert view_created is True
