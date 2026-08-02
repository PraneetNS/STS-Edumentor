# Diagnostic script to run a real Hindi WebSocket turn.
# Findings: Devanagari Hindi text correctly routes directly to 'hindi'.
# However, LLM responds in English due to system prompts, adding translation bridge latency.
import asyncio
import json
import time
import sys
import websockets

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

async def run_hindi_turn():
    import uuid
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from agent.auth_utils import generate_access_token

    token = generate_access_token(uuid.uuid4(), "test_student@example.com")
    ws_url = f"ws://localhost:8000/ws/voice?token={token}"
    
    payload = {
        "type": "text_query",
        "student_id": "test_student_123",
        "session_id": "test_session_123",
        "text": "रिकर्सन क्या होता है और इसका एक उदाहरण दीजिए"
    }

    print(f"Connecting to {ws_url[:60]}... [token generated]")
    t0 = time.time()
    try:
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            print(f"Connected in {time.time()-t0:.3f}s.")
            print(f"Sending text query: {payload['text']!r}")
            await ws.send(json.dumps(payload))
            
            print("\nStreaming response events:")
            print("-" * 60)
            async for msg in ws:
                data = json.loads(msg)
                mtype = data.get("type")
                # Format print based on message type
                if mtype == "state":
                    print(f"[State] -> {data.get('state')}")
                elif mtype == "live_transcript":
                    print(f"[Live Transcript] -> {data.get('text')!r}")
                elif mtype == "transcript":
                    print(f"[FINAL Transcript] -> {data.get('text')!r} | route={data.get('route_lang')}")
                elif mtype == "assistant_text_delta":
                    # Print raw token stream
                    print(f"[Token Delta] {repr(data.get('text'))}")
                elif mtype == "audio_chunk":
                    audio_len = len(data.get("audio", ""))
                    print(f"[Audio Chunk] length={audio_len} bytes")
                elif mtype == "followup":
                    print(f"[Followup Question] {data.get('text')!r}")
                elif mtype == "assistant_finished":
                    print("[Assistant Finished]")
                    break
                elif mtype == "error":
                    print(f"[ERROR] {data.get('text')!r}")
                    break
                else:
                    print(f"[Event: {mtype}] -> {data}")
    except Exception as exc:
        print(f"Error connecting/transacting with WebSocket: {exc}")

if __name__ == "__main__":
    asyncio.run(run_hindi_turn())
