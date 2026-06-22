"""
EduMentor Voice — FastAPI Backend Entry Point

Real-time voice pipeline:
  Browser mic (PCM Int16 @ 16kHz)
    → WebSocket /ws/voice
    → faster-whisper STT
    → Agent Controller (intent, memory, safety, emotion, interruption)
    → llama.cpp LLM streaming
    → Kokoro TTS (sentence-by-sentence)
    → WebSocket binary audio → browser playback

All engines are loaded once at startup via the lifespan context manager
and are never reloaded between requests.
"""

import asyncio
import json
import logging
import logging.handlers
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

import torch
from silero_vad import load_silero_vad

# Force UTF-8 output on Windows (prevents UnicodeEncodeError for log chars)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi.middleware.cors import CORSMiddleware

from config import Config
from stt.whisper_engine import WhisperEngine
from llm.llm_engine import LLMEngine
from tts.kokoro_engine import KokoroEngine
from utils.audio import int16_bytes_to_float32, is_sentence_complete

import time
from agent.models import ConversationState, Emotion
from speech.stabilizer import TranscriptStabilizer

# Agent layer imports
from agent import (
    AgentController,
    InterruptManager,
    MemoryManager,
    SessionSummarizer,
    StudentProfileManager,
)
from agent.database import DatabaseManager

silero_vad_model = None

# ─────────────────────────────────────────────────────────────────────────────
# Logging — main console logger + agent file logger
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("edumentor.main")


def _setup_agent_file_logger() -> None:
    """Set up rotating file logger for agent events."""
    log_path = Config.AGENT_LOG_FILE
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    file_handler.setLevel(getattr(logging, Config.AGENT_LOG_LEVEL, logging.INFO))

    # Attach to the agent logger hierarchy
    agent_root = logging.getLogger("edumentor.agent")
    agent_root.addHandler(file_handler)
    logger.info("Agent file logger → %s", log_path)


# ─────────────────────────────────────────────────────────────────────────────
# Engine singletons — initialised in lifespan, used in WebSocket handlers
# ─────────────────────────────────────────────────────────────────────────────

whisper_engine:    Optional[WhisperEngine]       = None
llm_engine:        Optional[LLMEngine]            = None
kokoro_engine:     Optional[KokoroEngine]         = None
agent_controller:  Optional[AgentController]      = None
interrupt_manager: Optional[InterruptManager]     = None
db_manager:        Optional[DatabaseManager]      = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all ML models and agent components once at startup; release on shutdown."""
    global whisper_engine, llm_engine, kokoro_engine, silero_vad_model
    global agent_controller, interrupt_manager, db_manager

    logger.info("=" * 60)
    logger.info("  EduMentor Voice -- Starting up")
    logger.info("=" * 60)

    # Set up agent file logger
    _setup_agent_file_logger()

    # Load database pool
    db_manager = DatabaseManager()
    await db_manager.initialize()

    # Load core engines sequentially (each may use GPU memory)
    whisper_engine = WhisperEngine()
    llm_engine = LLMEngine()
    kokoro_engine = KokoroEngine()


    # Load Silero VAD model
    logger.info("Loading Silero VAD model ...")
    torch.set_num_threads(1)
    silero_vad_model = load_silero_vad()
    if torch.cuda.is_available():
        logger.info("Moving Silero VAD model to GPU (cuda) ...")
        silero_vad_model = silero_vad_model.to("cuda")
    logger.info("[OK] Silero VAD ready.")

    # ── Initialize Agent Layer ────────────────────────────────────────────────
    if Config.AGENT_ENABLED:
        logger.info("Initializing Agent Layer...")

        interrupt_manager  = InterruptManager()
        memory_manager     = MemoryManager(
            max_turns = Config.MEMORY_MAX_TURNS,
        )
        session_summarizer = SessionSummarizer(
            llm_engine  = llm_engine,
            summary_dir = Config.SESSION_SUMMARY_DIR,
        )
        profile_manager    = StudentProfileManager(
            profile_path = Config.STUDENT_PROFILE_PATH,
        )
        profile_manager.increment_session_count()

        agent_controller = AgentController(
            llm_engine          = llm_engine,
            memory_manager      = memory_manager,
            session_summarizer  = session_summarizer,
            profile_manager     = profile_manager,
            interrupt_manager   = interrupt_manager,
            intent_enabled      = Config.AGENT_INTENT_CLASSIFY,
            safety_enabled      = Config.AGENT_SAFETY_ENABLED,
            db_manager          = db_manager,
        )
        logger.info("[OK] Agent Layer ready.")
    else:
        logger.info("Agent Layer disabled (AGENT_ENABLED=false). Using direct LLM calls.")

    logger.info("=" * 60)
    logger.info("  All engines ready -- accepting connections")
    logger.info("=" * 60)

    yield  # Server is running

    # Shutdown
    logger.info("Shutting down engines ...")
    if llm_engine:
        await llm_engine.aclose()
    if db_manager:
        await db_manager.close()
    logger.info("Goodbye.")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI application
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="EduMentor Voice API",
    description="Real-time AI voice tutor — STT → LLM → TTS pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Return liveness status and engine readiness."""
    return {
        "status": "ok",
        "engines": {
            "whisper":          whisper_engine is not None,
            "llm":              llm_engine is not None,
            "kokoro":           kokoro_engine is not None,
            "agent_controller": agent_controller is not None,
        },
        "agent": {
            "enabled":          Config.AGENT_ENABLED,
            "intent_classify":  Config.AGENT_INTENT_CLASSIFY,
            "safety_enabled":   Config.AGENT_SAFETY_ENABLED,
            "memory_max_turns": Config.MEMORY_MAX_TURNS,
        },
        "config": {
            "whisper_model":  Config.WHISPER_MODEL,
            "whisper_device": Config.WHISPER_DEVICE,
            "llm_base_url":   Config.LLM_BASE_URL,
            "kokoro_voice":   Config.KOKORO_VOICE,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Persona Endpoints & Request Models
# ─────────────────────────────────────────────────────────────────────────────

import base64


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Pipeline
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/voice")
async def voice_endpoint(websocket: WebSocket):
    """
    Main real-time voice pipeline WebSocket endpoint.

    Protocol (client → server):
        - Binary frames  : Raw Int16 PCM audio @ 16 kHz (mono) accumulated
        - JSON text frame: {"type": "end_of_speech"} — triggers STT + LLM + TTS
        - JSON text frame: {"type": "interrupt"}     — cancels active generation
        - JSON text frame: {"type": "ping"}           — keepalive

    Protocol (server → client):
        - JSON: {"type": "state",          "state": "..."} — state machine sync
        - JSON: {"type": "live_transcript","text": "..."}  — live/updating transcript
        - JSON: {"type": "transcript",     "text": "..."}  — final user speech
        - JSON: {"type": "assistant_token","text": "..."}  — LLM token
        - JSON: {"type": "tts_start"}                      — TTS about to start
        - JSON: {"type": "vad_end_of_speech"}              — auto silence cut detected
        - JSON: {"type": "done"}                           — turn complete
        - JSON: {"type": "error",          "text": "..."}  — pipeline error
        - Binary frames: WAV audio chunks (24 kHz PCM_16) for playback
    """
    await websocket.accept()
    logger.info("Client connected: %s", websocket.client)
    session_id = websocket.query_params.get("session_id") or f"{websocket.client.host}:{websocket.client.port}"

    import numpy as np
    loop = asyncio.get_running_loop()

    # Per-connection audio accumulation buffer and VAD states
    audio_chunks: list[bytes] = []
    vad_buffer = b""
    speech_started = False
    speech_duration = 0.0
    silence_duration = 0.0
    is_pipeline_running = False

    # Task references
    pipeline_task: Optional[asyncio.Task] = None
    live_transcribe_task: Optional[asyncio.Task] = None
    final_transcript = ""
    latest_live_transcript = ""

    # Initialize TranscriptStabilizer
    stabilizer = TranscriptStabilizer()

    # Conversation State Machine
    current_state = ConversationState.IDLE

    async def set_state(new_state: ConversationState):
        nonlocal current_state
        current_state = new_state
        await websocket.send_json({"type": "state", "state": current_state.value})
        logger.info("Conversation State Transition -> %s", new_state.value)

    # Set initial state
    await set_state(ConversationState.IDLE)

    async def live_transcription_loop():
        nonlocal final_transcript, latest_live_transcript
        try:
            from speech.normalizer import speech_normalizer
            while True:
                await asyncio.sleep(Config.LIVE_TRANSCRIPTION_INTERVAL)
                current_len = len(audio_chunks)
                if current_len > 0:
                    new_bytes = b"".join(audio_chunks[:current_len])
                    audio_array = int16_bytes_to_float32(new_bytes)
                    live_text = await loop.run_in_executor(
                        None,
                        whisper_engine.transcribe,
                        audio_array
                    )
                    if live_text:
                        # Apply speech correction normalization
                        normalized_text = speech_normalizer.normalize(live_text, session_id=session_id)
                        latest_live_transcript = normalized_text
                        
                        # Apply stabilization to get confirmed vs temporary words
                        words_payload = stabilizer.stabilize(normalized_text)
                        
                        await websocket.send_json({
                            "type": "live_transcript",
                            "text": normalized_text,
                            "words": words_payload
                        })
        except asyncio.CancelledError:
            pass

    async def trigger_pipeline(is_vad_trigger: bool = False):
        nonlocal is_pipeline_running, live_transcribe_task, pipeline_task
        if is_pipeline_running or not audio_chunks:
            return
        is_pipeline_running = True

        # Stop live transcription immediately
        if live_transcribe_task and not live_transcribe_task.done():
            live_transcribe_task.cancel()

        # Cancel any active running pipeline task first (to support interruption/new start)
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
            try:
                await pipeline_task
            except asyncio.CancelledError:
                pass

        # Concatenate and clear chunks
        raw_pcm = b"".join(audio_chunks)
        audio_chunks.clear()

        if is_vad_trigger:
            # Tell the frontend the backend detected silence and stopped recording
            await websocket.send_json({"type": "vad_end_of_speech"})

        await set_state(ConversationState.TRANSCRIBING)

        # Spawn pipeline execution as a background task to keep websocket responsive to interrupts
        pre_transcribed = latest_live_transcript if (is_vad_trigger and latest_live_transcript) else None
        pipeline_task = asyncio.create_task(_run_pipeline_wrapper(raw_pcm, pre_transcribed))

    async def _run_pipeline_wrapper(raw_pcm: bytes, pre_transcribed: Optional[str] = None):
        nonlocal is_pipeline_running
        try:
            await _run_pipeline(websocket, raw_pcm, set_state, pre_transcribed)
        except asyncio.CancelledError:
            logger.info("Pipeline execution cancelled.")
        except Exception as e:
            logger.exception("Pipeline execution failed: %s", e)
            await set_state(ConversationState.ERROR)
            try:
                await websocket.send_json({"type": "error", "text": str(e)})
            except Exception:
                pass
        finally:
            is_pipeline_running = False

    try:
        while True:
            message = await websocket.receive()

            # ── Binary audio frame ──────────────────────────────────────────
            if "bytes" in message and message["bytes"]:
                chunk = message["bytes"]
                audio_chunks.append(chunk)

                if silero_vad_model is not None:
                    vad_buffer += chunk
                    # Silero VAD expects chunk sizes of 512 samples (1024 bytes)
                    while len(vad_buffer) >= 1024:
                        vad_chunk = vad_buffer[:1024]
                        vad_buffer = vad_buffer[1024:]

                        # Get speech probability from Silero
                        samples = np.frombuffer(vad_chunk, dtype=np.int16).astype(np.float32) / 32768.0
                        audio_tensor = torch.from_numpy(samples)
                        if torch.cuda.is_available():
                            audio_tensor = audio_tensor.to("cuda")
                        with torch.no_grad():
                            speech_prob = silero_vad_model(audio_tensor, 16000).item()

                        if speech_prob > Config.VAD_THRESHOLD:
                            speech_duration += 0.032  # 512 samples = 32ms
                            silence_duration = 0.0
                            if not speech_started and speech_duration >= Config.MIN_SPEECH_DURATION:
                                speech_started = True
                                logger.info("VAD: Speech start detected.")
                                
                                # Barge-in handling
                                if is_pipeline_running:
                                    logger.info("Barge-in detected! Interrupting assistant.")
                                    await set_state(ConversationState.INTERRUPTED)
                                    
                                    # Save interrupt state BEFORE cancellation
                                    if agent_controller and pipeline_task and not pipeline_task.done():
                                        partial    = agent_controller.get_partial_response(session_id)
                                        topic      = agent_controller.get_current_topic(session_id)
                                        interrupt_manager.save_state(
                                            session_id       = session_id,
                                            partial_response = partial,
                                            topic            = topic,
                                        )

                                    if pipeline_task and not pipeline_task.done():
                                        pipeline_task.cancel()
                                        try:
                                            await pipeline_task
                                        except asyncio.CancelledError:
                                            pass
                                            
                                    if live_transcribe_task and not live_transcribe_task.done():
                                        live_transcribe_task.cancel()

                                    # Tell frontend to stop playing audio immediately
                                    await websocket.send_json({"type": "interrupt"})
                                    is_pipeline_running = False
                                    
                                    # Keep only the last ~500ms of audio to avoid cutting off start of barge-in
                                    keep_chunks = 15
                                    if len(audio_chunks) > keep_chunks:
                                        audio_chunks = audio_chunks[-keep_chunks:]
                                else:
                                    await set_state(ConversationState.LISTENING)

                                stabilizer.reset()
                                final_transcript = ""
                                latest_live_transcript = ""
                                live_transcribe_task = asyncio.create_task(live_transcription_loop())
                        else:
                            if speech_started:
                                silence_duration += 0.032
                                if silence_duration >= Config.VAD_SILENCE_TIMEOUT:
                                    logger.info("VAD: Silence timeout reached. Auto-triggering pipeline.")
                                    speech_started = False
                                    speech_duration = 0.0
                                    silence_duration = 0.0
                                    await trigger_pipeline(is_vad_trigger=True)
                            else:
                                speech_duration = 0.0

            # ── Text control frame ──────────────────────────────────────────
            elif "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON from client: %r", message["text"][:80])
                    continue

                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "end_of_speech":
                    # User clicked stop manually
                    if not audio_chunks:
                        await websocket.send_json({"type": "error", "text": "No audio received."})
                        continue
                    speech_started = False
                    speech_duration = 0.0
                    silence_duration = 0.0
                    await trigger_pipeline(is_vad_trigger=False)

                elif msg_type == "interrupt":
                    logger.info("Interruption received. Saving state then cancelling.")
                    await set_state(ConversationState.INTERRUPTED)

                    # ── Save interrupt state BEFORE cancellation ──────────────
                    if agent_controller and pipeline_task and not pipeline_task.done():
                        partial    = agent_controller.get_partial_response(session_id)
                        topic      = agent_controller.get_current_topic(session_id)
                        interrupt_manager.save_state(
                            session_id       = session_id,
                            partial_response = partial,
                            topic            = topic,
                        )

                    if pipeline_task and not pipeline_task.done():
                        pipeline_task.cancel()
                        try:
                            await pipeline_task
                        except asyncio.CancelledError:
                            pass
                    if live_transcribe_task and not live_transcribe_task.done():
                        live_transcribe_task.cancel()

                    audio_chunks.clear()
                    vad_buffer = b""
                    speech_started = False
                    speech_duration = 0.0
                    silence_duration = 0.0
                    is_pipeline_running = False
                    final_transcript = ""
                    latest_live_transcript = ""
                    stabilizer.reset()
                    await set_state(ConversationState.IDLE)

                elif msg_type == "persona_changed":
                    logger.info("Persona changed in session: %s -> %s", data.get("previous"), data.get("current"))
                    stabilizer.reset()

    except WebSocketDisconnect:
        logger.info("Client disconnected: %s", websocket.client)
    except RuntimeError as exc:
        if "disconnect message has been received" in str(exc):
            logger.info("Client disconnected (disconnect message received): %s", websocket.client)
        else:
            logger.exception("Runtime error in WebSocket: %s", exc)
    except Exception as exc:
        logger.exception("Unexpected WebSocket error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "text": str(exc)})
        except Exception:
            pass
    finally:
        logger.info("Cleaning up WebSocket session for client: %s", websocket.client)
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        if live_transcribe_task and not live_transcribe_task.done():
            live_transcribe_task.cancel()


async def _run_pipeline(
    websocket: WebSocket,
    raw_pcm: bytes,
    set_state,
    pre_transcribed_text: Optional[str] = None
) -> None:
    """
    Execute the full STT → LLM → TTS pipeline for one user utterance.

    Steps:
      1. Convert raw Int16 bytes → Float32 numpy array
      2. Whisper transcription (in thread executor to avoid blocking)
      3. Stream LLM tokens + sentence-buffer TTS in parallel
      4. Send "done" when everything is complete
    """
    start_time = time.time()
    latency_metrics = {
        "vad_end": 0.0,
        "whisper_done": None,
        "first_llm_token": None,
        "first_audio": None,
        "complete": None
    }

    loop = asyncio.get_running_loop()
    session_id = websocket.query_params.get("session_id") or f"{websocket.client.host}:{websocket.client.port}"
    user_id = websocket.query_params.get("user_id") or session_id

    # ── 1. STT ───────────────────────────────────────────────────────────────
    audio_array = int16_bytes_to_float32(raw_pcm)
    if pre_transcribed_text:
        transcript = pre_transcribed_text
        logger.info("Using pre-transcribed text from live transcriber: %r", transcript)
        latency_metrics["whisper_done"] = 0.0
    else:
        logger.info("Transcribing %.1f seconds of audio …", len(audio_array) / Config.AUDIO_SAMPLE_RATE)

        # Run blocking Whisper in a thread to keep the event loop free
        transcript: str = await loop.run_in_executor(
            None, whisper_engine.transcribe, audio_array
        )
        latency_metrics["whisper_done"] = round(time.time() - start_time, 2)

    if not transcript:
        logger.info("Empty transcript — skipping pipeline.")
        await websocket.send_json({"type": "transcript", "text": "", "words": []})
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "done"})
        return

    # ── 1.5 Speech Normalization ─────────────────────────────────────────────
    from speech.normalizer import speech_normalizer
    normalized_transcript = speech_normalizer.normalize(transcript, session_id=session_id)

    if not normalized_transcript:
        logger.info("Empty normalized transcript — skipping pipeline.")
        await websocket.send_json({"type": "transcript", "text": "", "words": []})
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "done"})
        return

    # ── 2. Send transcript to frontend with word statuses ────────────────────
    logger.info("Original Transcript: %r -> Normalized: %r", transcript, normalized_transcript)
    confirmed_words = [{"word": w, "status": "confirmed"} for w in normalized_transcript.split()]
    await websocket.send_json({
        "type": "transcript",
        "text": normalized_transcript,
        "words": confirmed_words
    })

    # ── 2.5 Speech Emotion Detection ──────────────────────────────────────────
    from speech.emotion import detect_audio_emotion
    audio_emotion = detect_audio_emotion(audio_array, normalized_transcript)
    
    # Send the emotion analysis to the frontend
    await websocket.send_json({
        "type": "emotion",
        "features": getattr(audio_emotion, "features", {}),
        "state": audio_emotion.emotion.value,
        "confidence": audio_emotion.confidence
    })

    # Calculate dynamic speed based on student emotion
    emotion_adjust = 1.0
    emotion_state = audio_emotion.emotion if audio_emotion else Emotion.NEUTRAL
    if emotion_state in (Emotion.CONFUSED, Emotion.FRUSTRATED):
        emotion_adjust = 0.85
    elif emotion_state == Emotion.BORED:
        emotion_adjust = 1.1

    speed = round(Config.KOKORO_SPEED * emotion_adjust, 2)
    voice = Config.KOKORO_VOICE
    logger.info("Dynamic Prosody: base_speed=%.2f, emotion=%s -> final_speed=%.2f, voice=%s",
                Config.KOKORO_SPEED, emotion_state.value, speed, voice)

    # Transition to THINKING state
    await set_state(ConversationState.THINKING)

    # ── 3. LLM streaming + TTS ────────────────────────────────────────────────
    if agent_controller is not None:
        # ── Agent path: full pipeline with intent, memory, safety, emotion ────
        token_stream = agent_controller.stream(normalized_transcript, session_id, user_id=user_id, audio_array=audio_array)
        await _stream_llm_and_tts(websocket, token_stream, loop, set_state, speed, voice, latency_metrics, start_time)
    else:
        # ── Legacy path: direct LLM call (AGENT_ENABLED=false) ───────────────
        token_stream = llm_engine.stream_tokens(normalized_transcript)
        await _stream_llm_and_tts(websocket, token_stream, loop, set_state, speed, voice, latency_metrics, start_time)

    # ── 4. Signal turn complete ───────────────────────────────────────────────
    await set_state(ConversationState.IDLE)
    latency_metrics["complete"] = round(time.time() - start_time, 2)
    logger.info("Latency Tracing: %s", json.dumps(latency_metrics))
    logger.info("Latency Metrics: TTFT=%.2fs, TTFA=%.2fs", 
                latency_metrics.get("first_llm_token") or 0.0, 
                latency_metrics.get("first_audio") or 0.0)
    await websocket.send_json({"type": "assistant_finished"})


async def _stream_llm_and_tts(
    websocket: WebSocket,
    token_stream,           # AsyncIterator[str] from either AgentController or LLMEngine
    loop: asyncio.AbstractEventLoop,
    set_state,
    speed: float,
    voice: str,
    latency_metrics: dict,
    start_time: float,
) -> None:
    """
    Simultaneously stream LLM tokens to the frontend AND generate TTS audio
    sentence-by-sentence using a 3-queue architecture with backpressure.
    """
    # Queues
    tts_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=3)
    audio_queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=3)
    sentence_buffer = ""

    # ── LLM Token Reader & Sentence Chunker ────────────────────────────────
    async def llm_token_reader():
        nonlocal sentence_buffer
        is_first_chunk = True
        try:
            async for token_data in token_stream:
                # Record first LLM token latency
                if latency_metrics["first_llm_token"] is None:
                    latency_metrics["first_llm_token"] = round(time.time() - start_time, 2)
                
                # Unpack raw and planned tokens
                if isinstance(token_data, dict):
                    raw_token = token_data.get("raw", "")
                    planned_token = token_data.get("planned", "")
                elif isinstance(token_data, tuple):
                    raw_token, planned_token = token_data
                else:
                    raw_token = token_data
                    planned_token = token_data

                # Forward raw token to frontend immediately
                if raw_token:
                    await websocket.send_json({"type": "assistant_text_delta", "text": raw_token})
                
                # Accumulate planned token for TTS
                if planned_token:
                    sentence_buffer += planned_token

                # Dynamic first-chunk optimization:
                # For the first chunk, we flush aggressively to minimize Time-to-First-Audio (TTFA).
                # We flush if length is >= 40 characters and we hit a word boundary (space) or punctuation,
                # or if a complete sentence/clause is detected.
                should_flush = False
                stripped = sentence_buffer.strip()
                
                if is_first_chunk:
                    import re
                    # Flush on any sentence ending punctuation if minimum length (3 chars) is met (handles quotes/brackets)
                    if len(stripped) >= 3 and re.search(r"(?<=\S{2})[.!?]+['\"`’”\]\)]*(?:\s|$)", stripped):
                        should_flush = True
                    # Flush on comma/clause ending punctuation without the 15 char minimum (handles quotes/brackets)
                    elif len(stripped) >= 3 and re.search(r"(?<=\S{2})[,;:—\n\r]+['\"`’”\]\)]*(?:\s|$)", stripped):
                        should_flush = True
                    # Flush on space/word boundary if we've accumulated at least 30 characters (fast phrase split)
                    elif len(stripped) >= 30 and (raw_token and (raw_token.isspace() or any(char in raw_token for char in ".,!?;:-—"))):
                        should_flush = True
                else:
                    # Standard chunking logic for subsequent sentences
                    if is_sentence_complete(sentence_buffer) or len(sentence_buffer) > Config.TTS_CHUNK_CHARS:
                        should_flush = True

                if should_flush:
                    sentence = sentence_buffer.strip()
                    if sentence:
                        sentence_buffer = ""
                        is_first_chunk = False
                        
                        # Filter out diagrams, flowcharts, or roadmaps from TTS
                        from agent.response_planner import is_diagram_or_roadmap
                        if is_diagram_or_roadmap(sentence):
                            logger.info("Skipping diagram/roadmap sentence for TTS: %r", sentence[:60])
                            continue
                        
                        logger.debug("Enqueuing sentence for TTS: %r", sentence[:60])
                        # This will block if tts_queue is full (size >= 3), implementing backpressure
                        await tts_queue.put(sentence)
        except asyncio.CancelledError:
            logger.info("LLM token reader cancelled.")
            raise
        except Exception as exc:
            logger.exception("LLM token reading error: %s", exc)
        finally:
            final_sentence = sentence_buffer.strip()
            if final_sentence:
                from agent.response_planner import is_diagram_or_roadmap
                if not is_diagram_or_roadmap(final_sentence):
                    logger.debug("Enqueuing final sentence for TTS: %r", final_sentence[:60])
                    await tts_queue.put(final_sentence)
            # Enqueue sentinel to signal TTS worker to stop
            await tts_queue.put(None)

    # ── TTS Synthesis Worker ────────────────────────────────────────────────
    async def tts_worker():
        try:
            while True:
                sentence = await tts_queue.get()
                if sentence is None:
                    # Send sentinel to audio sender
                    await audio_queue.put(None)
                    tts_queue.task_done()
                    break
                
                logger.debug("TTS worker synthesizing: %r", sentence[:60])
                # Synthesize sentence using dynamic speed and voice
                wav_bytes = await loop.run_in_executor(None, lambda: kokoro_engine.synthesize(sentence, speed, voice))
                
                # Estimate word timestamps using the alignment engine
                from speech.alignment import estimate_word_timestamps
                timestamps = estimate_word_timestamps(sentence, wav_bytes)
                
                await audio_queue.put({
                    "wav": wav_bytes,
                    "timestamps": timestamps,
                    "text": sentence
                })
                tts_queue.task_done()
        except asyncio.CancelledError:
            logger.info("TTS worker cancelled.")
            raise
        except Exception as exc:
            logger.exception("TTS worker error: %s", exc)

    # ── Audio Sender ────────────────────────────────────────────────────────
    async def audio_sender():
        first_audio_sent = False
        try:
            while True:
                result = await audio_queue.get()
                if result is None:
                    audio_queue.task_done()
                    break
                
                wav_bytes = result["wav"]
                timestamps = result["timestamps"]
                sentence = result["text"]
                
                if wav_bytes:
                    # If this is the first audio chunk, send tts_start and record first_audio latency
                    if not first_audio_sent:
                        first_audio_sent = True
                        await websocket.send_json({"type": "tts_start"})
                        # Transition state to SPEAKING
                        await set_state(ConversationState.SPEAKING)
                        latency_metrics["first_audio"] = round(time.time() - start_time, 2)
                    
                    # Base64 encode the WAV bytes
                    base64_wav = base64.b64encode(wav_bytes).decode("utf-8")
                    
                    # Send combined audio_chunk event
                    await websocket.send_json({
                        "type": "audio_chunk",
                        "audio": base64_wav,
                        "word_timestamps": timestamps
                    })
                audio_queue.task_done()
        except asyncio.CancelledError:
            logger.info("Audio sender cancelled.")
            raise
        except Exception as exc:
            logger.exception("Audio sender error: %s", exc)

    # Spawn tasks
    reader_task = asyncio.create_task(llm_token_reader())
    worker_task = asyncio.create_task(tts_worker())
    sender_task = asyncio.create_task(audio_sender())

    try:
        # Wait until all subtasks complete
        await asyncio.gather(reader_task, worker_task, sender_task)
    except asyncio.CancelledError:
        logger.info("LLM/TTS streaming gathering cancelled. Cancelling subtasks.")
        reader_task.cancel()
        worker_task.cancel()
        sender_task.cancel()
        await asyncio.gather(reader_task, worker_task, sender_task, return_exceptions=True)
        raise

