import sys
import os
import asyncio
import pytest
from unittest import mock
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# Add parent folder of tests to path so we can import from backend root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from observability.metrics import queue_depth

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

def test_metrics_endpoint_basic():
    # Trigger metric instantiation/registration on the default registry
    queue_depth.set(12.0)

    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain") or \
           response.headers["content-type"].startswith("application/openmetrics-text")
    
    body = response.text
    # Verify our metric is exposed
    assert "edumentor_queue_depth" in body
    # Verify the value set is correct
    assert "12.0" in body

@pytest.mark.asyncio
async def test_metrics_endpoint_concurrency():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        t0 = asyncio.get_event_loop().time()
        
        # Concurrently request metrics and health check
        responses = await asyncio.gather(
            ac.get("/metrics"),
            ac.get("/health"),
            ac.get("/metrics"),
            ac.get("/health")
        )
        
        t1 = asyncio.get_event_loop().time()
        duration = t1 - t0
        
        for response in responses:
            assert response.status_code == 200
            
        assert duration < 1.0
