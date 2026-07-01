import sys
import os
import pytest
import uuid
import time
import datetime
from unittest import mock
from fastapi.testclient import TestClient

# Add parent folder of tests to path so we can import from backend root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from agent.database import DatabaseManager
from agent import auth_utils

@pytest.fixture(scope="module", autouse=True)
def mock_lifespan_engines():
    """Mock the model engines inside main.py to prevent loading weights during client lifespan setup."""
    with mock.patch("main.WhisperEngine") as mock_whisper, \
         mock.patch("main.LLMEngine") as mock_llm, \
         mock.patch("main.KokoroEngine") as mock_kokoro, \
         mock.patch("main.load_silero_vad") as mock_vad:
         
        # Make aclose an async mock to prevent await TypeErrors on shutdown
        mock_llm.return_value.aclose = mock.AsyncMock()
        mock_whisper.return_value.aclose = mock.AsyncMock()
        mock_kokoro.return_value.aclose = mock.AsyncMock()
        
        yield

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.mark.asyncio
async def test_email_registration_verification_flow(client):
    email = f"test_student_{uuid.uuid4().hex[:6]}@edu.com"
    password = "securepassword123"
    display_name = "Test Student"

    # 1. Register user
    reg_response = client.post("/auth/register", json={
        "email": email,
        "password": password,
        "display_name": display_name
    })
    assert reg_response.status_code == 200
    assert reg_response.json()["status"] == "registered"

    # 2. Attempt login BEFORE verification (should fail with 403)
    login_fail_res = client.post("/auth/login", json={
        "email": email,
        "password": password
    })
    assert login_fail_res.status_code == 403
    assert "not verified" in login_fail_res.json()["detail"]

    # 3. Simulate verification
    verify_token = auth_utils.generate_verification_token(email)
    
    # 4. Verify email
    verify_res = client.get(f"/auth/verify-email?token={verify_token}", follow_redirects=False)
    assert verify_res.status_code == 307  # Redirect response
    assert "login?verified=true" in verify_res.headers["location"]

    # 5. Attempt login AFTER verification (should succeed)
    login_success_res = client.post("/auth/login", json={
        "email": email,
        "password": password
    })
    assert login_success_res.status_code == 200
    data = login_success_res.json()
    assert data["user"]["email"] == email.lower().strip()
    assert "refresh_token" in login_success_res.cookies

    # 6. Verify refresh token works via /auth/refresh (pass cookie explicitly)
    refresh_token = login_success_res.cookies.get("refresh_token")
    refresh_res = client.post("/auth/refresh", cookies={"refresh_token": refresh_token})
    assert refresh_res.status_code == 200
    assert "access_token" in refresh_res.json()

    # 7. Log out (should clear cookies)
    logout_res = client.post("/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "logged_out"
    cookie = logout_res.headers.get("set-cookie", "")
    assert "refresh_token=" in cookie or "Max-Age=0" in cookie or "expires=" in cookie

@pytest.mark.asyncio
async def test_google_oauth_upsert_integration(client):
    email = f"google_match_{uuid.uuid4().hex[:6]}@gmail.com"
    password = "some_password"
    display_name = "Email Registration"
    
    reg_response = client.post("/auth/register", json={
        "email": email,
        "password": password,
        "display_name": display_name
    })
    assert reg_response.status_code == 200

    with mock.patch("config.Config.GOOGLE_CLIENT_ID", ""):
        google_res = client.get("/auth/google/callback?code=mock_google_code_123", follow_redirects=False)
        assert google_res.status_code == 307
        
        location = google_res.headers["location"]
        assert "token=" in location
        token = location.split("token=")[1]
        
        payload = auth_utils.decode_token(token)
        assert payload["email"] == "mock_student@gmail.com"

@pytest.mark.asyncio
async def test_profile_stats_computation_logic():
    import asyncpg
    from config import Config
    from main import db_manager
    if not db_manager:
        pytest.skip("PostgreSQL manager not instantiated")

    pool = await asyncpg.create_pool(
        host=Config.POSTGRES_HOST,
        port=Config.POSTGRES_PORT,
        user=Config.POSTGRES_USER,
        password=Config.POSTGRES_PASSWORD,
        database=Config.POSTGRES_DB
    )
    
    old_pool = db_manager.pool
    db_manager.pool = pool

    temp_user_id = uuid.uuid4()
    email = f"stats_user_{temp_user_id.hex[:6]}@edu.com"
    
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, email, display_name, provider, email_verified) VALUES ($1, $2, 'Stats User', 'email', TRUE);",
                temp_user_id, email
            )
            
            import json
            for i in range(3):
                date = datetime.date.today() - datetime.timedelta(days=i)
                intent_dist = {
                    "CONCEPT_EXPLANATION": 3,
                    "CODE_HELP": 2,
                    "long_questions": 2,
                    "useful_turns": 4
                }
                
                await conn.execute(
                    """
                    INSERT INTO session_stats (
                        user_id, session_date, total_turns, total_tokens_in, total_tokens_out,
                        disciplines_hit, intent_dist, avg_turns_per_concept, self_initiated_questions, followup_rate
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);
                    """,
                    temp_user_id,
                    date,
                    10 + i,
                    1000 * (i + 1),
                    1200 * (i + 1),
                    ["cse", "mech"],
                    json.dumps(intent_dist),
                    4.5 - (i * 0.5),
                    6 - i,
                    float(10 - 6) / 10
                )
            
            stats = await db_manager.get_profile_stats(temp_user_id)
            
            assert stats is not None
            assert "readiness" in stats
            assert stats["readiness"]["score"] > 0
            assert "fingerprint" in stats
            assert stats["fingerprint"]["cse"] > 0
            assert "velocity" in stats
            assert len(stats["velocity"]) == 8
            assert "phase" in stats
            assert stats["phase"]["current"] in ["foundation-building", "placement-prep", "interview-mode", "post-offer"]
            assert "quality" in stats
            assert stats["quality"]["curiosity"] > 0
            assert "tokens" in stats
            assert stats["tokens"]["this_week"]["efficiency"] > 0
            
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM session_stats WHERE user_id = $1;", temp_user_id)
            await conn.execute("DELETE FROM users WHERE user_id = $1;", temp_user_id)
        db_manager.pool = old_pool
        await pool.close()
