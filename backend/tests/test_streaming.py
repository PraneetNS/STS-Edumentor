import pytest
import asyncio
from unittest import mock
import numpy as np

from tts.kokoro_engine import KokoroEngine

@pytest.mark.asyncio
async def test_kokoro_synthesize_stream_mocked():
    # Mock KPipeline and check synthesize_stream structure
    engine = KokoroEngine.__new__(KokoroEngine)
    engine.sample_rate = 24000
    engine.pipeline = mock.MagicMock()
    
    # Setup mock pipeline generator
    mock_audio = np.zeros(24000)
    engine.pipeline.return_value = [
        ("Hello", "həˈloʊ", mock_audio),
        ("world", "wɜːld", mock_audio)
    ]
    
    # Preprocessing mock
    engine._preprocess_text = lambda x: x
    
    # Call synthesize_stream
    chunks = list(engine.synthesize_stream("Hello world", speed=1.0, voice="af_bella"))
    
    assert len(chunks) == 2
    assert chunks[0][0] == "Hello"
    assert len(chunks[0][1]) > 44  # Should contain WAV header + PCM bytes
    assert chunks[1][0] == "world"

@pytest.mark.asyncio
async def test_stream_llm_and_tts_integration():
    from main import _stream_llm_and_tts
    
    # Mock parameters
    mock_ws = mock.AsyncMock()
    
    # Async iterator yielding tokens
    async def mock_token_stream():
        yield {"raw": "Hello ", "planned": "Hello "}
        yield {"raw": "world.", "planned": "world."}
        
    mock_loop = asyncio.get_event_loop()
    mock_set_state = mock.AsyncMock()
    latency_metrics = {"first_llm_token": None, "first_audio": None}
    
    # Mock KokoroEngine synthesize_stream
    mock_generator = [
        ("Hello", b"wav_data_1"),
        ("world", b"wav_data_2")
    ]
    
    mock_kokoro = mock.MagicMock()
    mock_kokoro.synthesize_stream.return_value = mock_generator
    
    with mock.patch("main.kokoro_engine", mock_kokoro):
        await _stream_llm_and_tts(
            websocket=mock_ws,
            token_stream=mock_token_stream(),
            loop=mock_loop,
            set_state=mock_set_state,
            speed=1.0,
            voice="af_bella",
            latency_metrics=latency_metrics,
            start_time=mock_loop.time(),
            student_id="test_student"
        )
        
    # Verify websocket calls
    sent_msgs = [call.args[0] for call in mock_ws.send_json.call_args_list]
    
    # We should have sent assistant_text_delta for "Hello " and "world."
    text_deltas = [m["text"] for m in sent_msgs if m["type"] == "assistant_text_delta"]
    assert "Hello " in text_deltas
    assert "world." in text_deltas
    
    # We should have sent audio_chunks
    audio_chunks = [m for m in sent_msgs if m["type"] == "audio_chunk"]
    assert len(audio_chunks) >= 1
    assert audio_chunks[0]["audio"] is not None

@pytest.mark.asyncio
async def test_stream_llm_and_tts_text_only():
    from main import _stream_llm_and_tts
    
    # Mock parameters
    mock_ws = mock.AsyncMock()
    
    # Async iterator yielding tokens
    async def mock_token_stream():
        yield {"raw": "Hello ", "planned": "Hello "}
        yield {"raw": "world.", "planned": "world."}
        
    mock_loop = asyncio.get_event_loop()
    mock_set_state = mock.AsyncMock()
    latency_metrics = {"first_llm_token": None, "first_audio": None}
    
    mock_kokoro = mock.MagicMock()
    
    with mock.patch("main.kokoro_engine", mock_kokoro):
        await _stream_llm_and_tts(
            websocket=mock_ws,
            token_stream=mock_token_stream(),
            loop=mock_loop,
            set_state=mock_set_state,
            speed=1.0,
            voice="af_bella",
            latency_metrics=latency_metrics,
            start_time=mock_loop.time(),
            student_id="test_student",
            text_only=True
        )
        
    # Verify websocket calls
    sent_msgs = [call.args[0] for call in mock_ws.send_json.call_args_list]
    
    # We should have sent assistant_text_delta for "Hello " and "world."
    text_deltas = [m["text"] for m in sent_msgs if m["type"] == "assistant_text_delta"]
    assert "Hello " in text_deltas
    assert "world." in text_deltas
    
    # We should NOT have sent any audio_chunk since it is text_only
    audio_chunks = [m for m in sent_msgs if m["type"] == "audio_chunk"]
    assert len(audio_chunks) == 0
    
    # Kokoro synthesize_stream should not have been called
    mock_kokoro.synthesize_stream.assert_not_called()
