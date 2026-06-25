import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from agent.database import DatabaseManager

@pytest.mark.asyncio
async def test_database_manager_disabled():
    # Test that DatabaseManager handles disabled state gracefully
    db = DatabaseManager()
    db.enabled = False
    
    await db.initialize()
    assert db.pool is None
    
    # Operations should fail open or return empty collections
    result = await db.fetch_user_corrections(uuid.uuid4())
    assert result == []

@pytest.mark.asyncio
async def test_write_speech_correction_mocked():
    # Test that write_speech_correction executes the correct SQL query when mocked
    db = DatabaseManager()
    db.enabled = True
    db.pool = AsyncMock()
    
    # Mock pool.acquire() context manager and connection
    conn = AsyncMock()
    db.pool.acquire = MagicMock()
    db.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    db.pool.acquire.return_value.__aexit__ = AsyncMock()
    
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    original = "segment haitian fault"
    corrected = "segmentation fault"
    
    await db.write_speech_correction(user_id, session_id, original, corrected)
    
    # Check that conn.execute was called with correct INSERT query
    conn.execute.assert_called_once()
    args, kwargs = conn.execute.call_args
    sql_query = args[0]
    assert "INSERT INTO speech_corrections" in sql_query
    assert args[1] == user_id
    assert args[2] == session_id
    assert args[3] == original
    assert args[4] == corrected

@pytest.mark.asyncio
async def test_fetch_user_corrections_mocked():
    # Test that fetch_user_corrections queries the database correctly and returns the correction list
    db = DatabaseManager()
    db.enabled = True
    db.pool = AsyncMock()
    
    # Mock pool.acquire() context manager and connection
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {"corrected_text": "segmentation fault"},
        {"corrected_text": "database"}
    ])
    db.pool.acquire = MagicMock()
    db.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    db.pool.acquire.return_value.__aexit__ = AsyncMock()
    
    user_id = uuid.uuid4()
    result = await db.fetch_user_corrections(user_id, limit=10)
    
    # Verify result terms
    assert "segmentation fault" in result
    assert "database" in result
    assert len(result) == 2
    
    # Verify sql query structure
    conn.fetch.assert_called_once()
    args = conn.fetch.call_args[0]
    sql_query = args[0]
    assert "SELECT corrected_text" in sql_query
    assert "FROM speech_corrections" in sql_query
    assert args[1] == user_id
    assert args[2] == 10
