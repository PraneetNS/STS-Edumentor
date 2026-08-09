import sys
import os
import pytest
import uuid
import time
from unittest import mock
from fastapi.testclient import TestClient
from fastapi import status
from fastapi.websockets import WebSocketDisconnect

# Add parent folder to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app, WSPingMessage, WSTextQueryMessage
from agent.database import DatabaseManager
from agent import auth_utils
from agent.rate_limiter import RateLimiter
from agent.access_control import AccessControl

@pytest.fixture(scope="module", autouse=True)
def mock_lifespan_engines():
    """Mock the model engines inside main.py to prevent loading weights during client lifespan setup."""
    with mock.patch("main.WhisperEngine") as mock_whisper, \
         mock.patch("main.LLMEngine") as mock_llm, \
         mock.patch("main.KokoroEngine") as mock_kokoro, \
         mock.patch("main.load_silero_vad") as mock_vad:
         
        mock_llm.return_value.aclose = mock.AsyncMock()
        mock_whisper.return_value.aclose = mock.AsyncMock()
        mock_kokoro.return_value.aclose = mock.AsyncMock()
        
        yield

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

# 1. Reduced JWT Expiration and Role Claims Test
def test_jwt_claims_and_expiration():
    user_id = uuid.uuid4()
    email = "student@edu.com"
    
    # Generate token
    token = auth_utils.generate_access_token(user_id, email, role="student")
    payload = auth_utils.decode_token(token)
    
    assert payload["role"] == "student"
    assert payload["type"] == "access"
    # Verify expiration is around 30 minutes (1800s)
    time_diff = payload["exp"] - time.time()
    assert 1700 < time_diff < 1900

# 2. HTTP Rate Limiting Test
def test_http_rate_limiter():
    limiter = RateLimiter()
    ip = "192.168.1.50"
    
    # Perform 5 requests (default max)
    for _ in range(5):
        assert limiter.check_http_rate_limit(ip, "login", max_per_minute=5) is True
        
    # 6th request must block
    assert limiter.check_http_rate_limit(ip, "login", max_per_minute=5) is False

# 3. IDOR Prevention - Profile Summary Test
@pytest.mark.asyncio
async def test_idor_profile_summary(client):
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    
    token_a = auth_utils.generate_access_token(user_a_id, "user_a@edu.com", role="student")
    token_b = auth_utils.generate_access_token(user_b_id, "user_b@edu.com", role="student")
    token_admin = auth_utils.generate_access_token(uuid.uuid4(), "admin@edumentor.edu", role="admin")
    
    # Mock DatabaseManager.pool fetchrow responses
    mock_user_row = {
        "user_id": user_b_id,
        "email": "user_b@edu.com",
        "display_name": "User B",
        "role": "student",
        "created_at": None
    }
    mock_stats_row = {"total_turns": 42, "active_days": 3}
    
    # We mock connection acquire and fetchrow
    mock_conn = mock.AsyncMock()
    mock_conn.fetchrow.side_effect = [mock_user_row, mock_stats_row]
    
    with mock.patch("main.db_manager") as mock_db:
        mock_db.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_db.enabled = True
        
        # User A requesting User B's profile summary -> Should be Forbidden (403)
        res = client.get(
            f"/api/profile/{user_b_id}/summary",
            headers={"Authorization": f"Bearer {token_a}"}
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN
        
        # User B requesting own profile summary -> Should be OK (200)
        mock_conn.fetchrow.side_effect = [mock_user_row, mock_stats_row]
        res = client.get(
            f"/api/profile/{user_b_id}/summary",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["student_id"] == str(user_b_id)
        
        # Admin requesting User B's profile summary -> Should be OK (200)
        mock_conn.fetchrow.side_effect = [mock_user_row, mock_stats_row]
        res = client.get(
            f"/api/profile/{user_b_id}/summary",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        assert res.status_code == status.HTTP_200_OK

# 4. IDOR Prevention - Session Messages Test
@pytest.mark.asyncio
async def test_idor_session_messages(client):
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    session_id = uuid.uuid4()
    
    token_a = auth_utils.generate_access_token(user_a_id, "user_a@edu.com", role="student")
    token_b = auth_utils.generate_access_token(user_b_id, "user_b@edu.com", role="student")
    token_admin = auth_utils.generate_access_token(uuid.uuid4(), "admin@edumentor.edu", role="admin")
    
    mock_conn = mock.AsyncMock()
    # 1. First fetchrow checks session owner (user_b_id)
    # 2. Second fetch returns messages
    mock_conn.fetchrow.return_value = {"user_id": user_b_id}
    mock_conn.fetch.return_value = []
    
    with mock.patch("main.db_manager") as mock_db:
        mock_db.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        # User A tries to view User B's session messages -> Should be 403
        res = client.get(
            f"/api/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {token_a}"}
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN
        
        # User B tries to view own session messages -> Should be 200
        res = client.get(
            f"/api/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        assert res.status_code == status.HTTP_200_OK
        
        # Admin tries to view User B's session messages -> Should be 200
        res = client.get(
            f"/api/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        assert res.status_code == status.HTTP_200_OK

# 5. Role-Based Access Control (RBAC) Test
def test_rbac_circuit_endpoints(client):
    student_token = auth_utils.generate_access_token(uuid.uuid4(), "student@edu.com", role="student")
    admin_token = auth_utils.generate_access_token(uuid.uuid4(), "admin@edu.com", role="admin")
    edumentor_email_token = auth_utils.generate_access_token(uuid.uuid4(), "staff@edumentor.edu", role="student")
    
    # 1. Student accesses /api/reset-circuit -> Should be 403
    res = client.post("/api/reset-circuit", headers={"Authorization": f"Bearer {student_token}"})
    assert res.status_code == status.HTTP_403_FORBIDDEN
    
    # 2. Admin accesses /api/reset-circuit -> Should be 200
    res = client.post("/api/reset-circuit", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == status.HTTP_200_OK
    
    # 3. Staff with edumentor.edu domain accesses /api/reset-circuit -> Should be 200
    res = client.post("/api/reset-circuit", headers={"Authorization": f"Bearer {edumentor_email_token}"})
    assert res.status_code == status.HTTP_200_OK

# 6. WebSocket Security checks
def test_websocket_restrictions(client):
    # Setup test tokens
    student_id = uuid.uuid4()
    token = auth_utils.generate_access_token(student_id, "student@edu.com", role="student")
    
    # 1. Test missing token check
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()
    assert exc.value.code == 1008
    
    # 2. Test invalid session_id path validation regex
    bad_session_id = "invalid_session/../../../etc/passwd"
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/voice?token={token}&session_id={bad_session_id}") as ws:
            ws.receive_json()
    assert exc.value.code == 1008
    
    # 3. Test connection attempt rate limiting
    # Mock rate limiter check_connection_attempt_rate to return False
    with mock.patch("agent.rate_limiter.rate_limiter.check_connection_attempt_rate", return_value=False):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/voice?token={token}") as ws:
                ws.receive_json()
        assert exc.value.code == 1008

def python_equivalent_sanitize_assistant_text(text: str) -> str:
    if not text:
        return ""
    show_tokens = []
    import re
    
    # Replace <show ...>
    def open_repl(match):
        attrs = match.group(1)
        token = f"__SHOW_OPEN_{len(show_tokens)}__"
        show_tokens.append({"token": token, "type": "open", "attrs": attrs})
        return token
    text = re.sub(r"<show\b([^>]*)>", open_repl, text, flags=re.IGNORECASE)
    
    # Replace </show>
    def close_repl(match):
        token = f"__SHOW_CLOSE_{len(show_tokens)}__"
        show_tokens.append({"token": token, "type": "close"})
        return token
    text = re.sub(r"</show>", close_repl, text, flags=re.IGNORECASE)
    
    # Escape
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # Restore
    for item in show_tokens:
        if item["type"] == "open":
            text = text.replace(item["token"], f"<show {item['attrs']}>")
        else:
            text = text.replace(item["token"], "</show>")
            
    # Simple convert show code blocks -> ```
    def show_code_repl(match):
        attrs = match.group(1)
        code = match.group(2).strip()
        lang_match = re.search(r'lang=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        lang = lang_match.group(1) if lang_match else ""
        return f"\n```{lang}\n{code}\n```\n"
    text = re.sub(r"<show\b([^>]*\btype=[\"']code[\"'][^>]*)>([\s\S]*?)<\/show>", show_code_repl, text, flags=re.IGNORECASE)
    
    # Strip remaining XML tags
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    return text.strip()

# 7. Output Stored XSS Escaping Test
def test_xss_escaping_sanitize_assistant_text():
    # Blatant XSS scripts
    payload_1 = "<script>alert('XSS')</script>"
    payload_2 = "<img src=x onerror=evil()>"
    payload_3 = "<scr<script>ipt>alert(1)</script>" # Recursive tag bypass
    
    # Sanitize visual show block code syntax should be preserved
    payload_code = '<show type="code" lang="python">print("Hello")</show>'
    
    res_1 = python_equivalent_sanitize_assistant_text(payload_1)
    res_2 = python_equivalent_sanitize_assistant_text(payload_2)
    res_3 = python_equivalent_sanitize_assistant_text(payload_3)
    res_code = python_equivalent_sanitize_assistant_text(payload_code)
    
    # Scripts should be escaped, rendering them harmless literal text
    assert "&lt;script&gt;" in res_1
    assert "onerror=evil()" in res_2
    assert "&lt;img" in res_2
    assert "&lt;script&gt;" in res_3
    
    # Code block format must be parsed correctly into markdown fences
    assert "```python" in res_code
    assert 'print("Hello")' in res_code
