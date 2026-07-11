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
if sys.platform == "win32" and "pytest" not in sys.modules:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, status, Response, Cookie, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from config import Config
from stt.whisper_engine import WhisperEngine
from llm.llm_engine import LLMEngine
from tts.kokoro_engine import KokoroEngine
from utils.audio import int16_bytes_to_float32, is_sentence_complete, validate_audio_chunk, validate_utterance_duration, check_audio_frequency_profile, is_utterance_substantial

import time
from agent.models import ConversationState, Emotion
from speech.stabilizer import TranscriptStabilizer
from speech.endpointing import SemanticEndpointer, EndpointingConfig, EndpointingMode
from speech.domain_corrector import DomainCorrector

# Agent layer imports
from agent import (
    AgentController,
    InterruptManager,
    MemoryManager,
    SessionSummarizer,
    StudentProfileManager,
    get_backend,
)
from agent.database import DatabaseManager
from agent.access_control import AccessControl
from agent.integrity_check import verify_model_integrity, verify_requirements_pinned, IntegrityError
from agent.idempotency import idempotency_guard

silero_vad_model = None
utterance_count = 0

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
profile_manager:   Optional[StudentProfileManager] = None
domain_corrector:  Optional[DomainCorrector]      = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all ML models and agent components once at startup; release on shutdown."""
    global whisper_engine, llm_engine, kokoro_engine, silero_vad_model
    global agent_controller, interrupt_manager, db_manager, profile_manager, domain_corrector

    logger.info("=" * 60)
    logger.info("  EduMentor Voice -- Starting up")
    logger.info("=" * 60)

    # Set up agent file logger
    _setup_agent_file_logger()

    # ── GAP 4 (LLM03/LLM04): Supply chain & model integrity checks ──────────
    # Run BEFORE loading any model into memory. A hash mismatch aborts startup.
    logger.info("Running supply chain and model integrity checks...")
    req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    verify_requirements_pinned(req_path)

    # Verify model files if they exist (graceful skip during development
    # when hashes are not yet pinned — verify_model_integrity() logs a
    # WARNING and returns True when EXPECTED_HASHES[key] is empty string).
    try:
        model_gguf_path = Config.LLM_MODEL_PATH if hasattr(Config, "LLM_MODEL_PATH") else ""
        if model_gguf_path and os.path.isfile(model_gguf_path):
            model_filename = os.path.basename(model_gguf_path)
            verify_model_integrity(model_gguf_path, model_filename)
        else:
            logger.info(
                "[INTEGRITY] GGUF model path not configured or not found. "
                "Skipping hash verification (configure Config.LLM_MODEL_PATH to enable)."
            )
    except IntegrityError as ie:
        logger.critical(
            "[INTEGRITY] Model integrity check FAILED: %s", ie
        )
        raise SystemExit(1) from ie

    logger.info("[OK] Integrity checks complete.")

    # Load database pool
    db_manager = DatabaseManager()
    await db_manager.initialize()

    # Load core engines sequentially (each may use GPU memory)
    whisper_engine = WhisperEngine()
    llm_engine = LLMEngine()
    kokoro_engine = KokoroEngine()

    # Reset circuit breaker so a stale open state from a previous
    # crash/restart never blocks the first real request of this session.
    from llm.circuit_breaker import llm_circuit
    llm_circuit.reset()
    logger.info("[OK] LLM circuit breaker reset to closed state.")


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
        _memory_backend    = get_backend(Config.MEMORY_BACKEND)
        memory_manager     = MemoryManager(
            max_turns = Config.MEMORY_MAX_TURNS,
            backend   = _memory_backend,
        )
        session_summarizer = SessionSummarizer(
            llm_engine  = llm_engine,
            summary_dir = Config.SESSION_SUMMARY_DIR,
        )
        profile_manager    = StudentProfileManager(
            profile_path = Config.STUDENT_PROFILE_PATH,
        )
        profile_manager.increment_session_count()

        from speech.domain_corrector import domain_corrector as dc
        domain_corrector = dc

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
# User Authentication HTTP Endpoints
# ─────────────────────────────────────────────────────────────────────────────

from pydantic import BaseModel

class UserRegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str

class UserLoginRequest(BaseModel):
    email: str
    password: str

from agent import auth_utils

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header"
        )
    token = authorization.split(" ")[1]
    try:
        payload = auth_utils.decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        return payload
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {e}"
        )

@app.post("/auth/register", tags=["Auth"])
async def register_user(req: UserRegisterRequest):
    if not db_manager or not db_manager.pool:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    existing = await db_manager.get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    password_hash = auth_utils.hash_password(req.password)
    user = await db_manager.create_user_email(req.email, req.display_name, password_hash)
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user record")
        
    verify_token = auth_utils.generate_verification_token(req.email)
    try:
        await auth_utils.send_verification_email(req.email, verify_token)
    except Exception as exc:
        logger.error("Failed to send verification email: %s", exc)
        
    return {
        "status": "registered",
        "message": "Verification email sent. Please verify your account before logging in."
    }

@app.get("/auth/verify-email", tags=["Auth"])
async def verify_email(token: str):
    try:
        payload = auth_utils.decode_token(token)
        if payload.get("type") != "verification":
            raise HTTPException(status_code=400, detail="Invalid token type")
        email = payload.get("email")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or expired verification token: {e}")
        
    success = await db_manager.verify_user_email(email)
    if not success:
        raise HTTPException(status_code=400, detail="Verification failed or user not found")
        
    return RedirectResponse(url="http://localhost:5173/login?verified=true")

@app.post("/auth/login", tags=["Auth"])
async def login_user(req: UserLoginRequest, response: Response):
    user = await db_manager.get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if not user.get("password_hash") or not auth_utils.check_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if not user.get("email_verified"):
        raise HTTPException(status_code=403, detail="Email address is not verified yet")
        
    user_id = user["user_id"]
    email = user["email"]
    
    access_token = auth_utils.generate_access_token(user_id, email)
    refresh_token = auth_utils.generate_refresh_token(user_id, email)
    
    is_production = Config.ENVIRONMENT == "production"
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=is_production,
        path="/auth",
        max_age=7*86400
    )
    
    return {
        "access_token": access_token,
        "user": {
            "user_id": str(user_id),
            "email": email,
            "display_name": user.get("display_name"),
            "avatar_url": user.get("avatar_url")
        }
    }

@app.post("/auth/refresh", tags=["Auth"])
async def refresh_tokens(response: Response, refresh_token: Optional[str] = Cookie(None)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
        
    try:
        payload = auth_utils.decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=410, detail="Invalid token type")
        user_id_str = payload.get("user_id")
        email = payload.get("email")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired refresh token: {e}")
        
    import uuid
    new_access_token = auth_utils.generate_access_token(uuid.UUID(user_id_str), email)
    return {"access_token": new_access_token}

@app.post("/auth/logout", tags=["Auth"])
async def logout_user(response: Response):
    response.delete_cookie(key="refresh_token", path="/auth")
    return {"status": "logged_out"}

@app.get("/auth/google", tags=["Auth"])
async def google_auth():
    if not Config.GOOGLE_CLIENT_ID or Config.GOOGLE_CLIENT_ID.startswith("your_"):
        logger.info("Google Client ID not configured. Using mock bypass redirect.")
        return RedirectResponse(url="http://localhost:8000/auth/google/callback?code=mock_google_code_123")
        
    import urllib.parse
    params = {
        "response_type": "code",
        "client_id": Config.GOOGLE_CLIENT_ID,
        "redirect_uri": Config.GOOGLE_REDIRECT_URI,
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent"
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=url)

@app.get("/auth/google/callback", tags=["Auth"])
async def google_auth_callback(code: str, response: Response):
    if code == "mock_google_code_123":
        email = "mock_student@gmail.com"
        display_name = "Mock Student"
        avatar_url = "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=150&h=150"
    else:
        import httpx
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": Config.GOOGLE_CLIENT_ID,
            "client_secret": Config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": Config.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        async with httpx.AsyncClient() as client:
            try:
                token_res = await client.post(token_url, data=data)
                token_res.raise_for_status()
                token_data = token_res.json()
                
                access_token = token_data.get("access_token")
                user_info_url = "https://www.googleapis.com/oauth2/v3/userinfo"
                headers = {"Authorization": f"Bearer {access_token}"}
                user_info_res = await client.get(user_info_url, headers=headers)
                user_info_res.raise_for_status()
                user_info = user_info_res.json()
                
                email = user_info.get("email")
                display_name = user_info.get("name")
                avatar_url = user_info.get("picture")
            except Exception as e:
                logger.error("Failed to perform Google OAuth exchange: %s", e)
                raise HTTPException(status_code=400, detail="Google authentication failed")
                
    if not email:
        raise HTTPException(status_code=400, detail="No email returned from Google")
        
    user = await db_manager.upsert_google_user(email, display_name, avatar_url)
    if not user:
        raise HTTPException(status_code=500, detail="Failed to upsert user record")
        
    user_id = user["user_id"]
    access_token = auth_utils.generate_access_token(user_id, email)
    refresh_token = auth_utils.generate_refresh_token(user_id, email)
    
    is_production = Config.ENVIRONMENT == "production"
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=is_production,
        path="/auth",
        max_age=7*86400
    )
    
    return RedirectResponse(url=f"http://localhost:5173/auth/callback?token={access_token}")

@app.get("/api/profile/stats", tags=["Profile"])
async def profile_stats(user: dict = Depends(get_current_user)):
    user_id_str = user.get("user_id")
    import uuid
    user_id = uuid.UUID(user_id_str)
    stats = await db_manager.get_profile_stats(user_id)
    return stats


# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Client error logging (FIX 1 — ErrorBoundary fire-and-forget POST)
# ─────────────────────────────────────────────────────────────────────────────

from pydantic import BaseModel as PydanticBaseModel
from typing import Optional as _Opt


class ClientErrorReport(PydanticBaseModel):
    message:        str
    stack:          _Opt[str] = None
    componentStack: _Opt[str] = None
    timestamp:      _Opt[str] = None


@app.post("/api/reset-circuit", tags=["System"])
async def reset_circuit_breaker():
    """Manually reset the LLM circuit breaker to closed state.
    Use this when the LLM server comes back online after an outage
    and you don't want to wait for the recovery_timeout."""
    from llm.circuit_breaker import llm_circuit
    llm_circuit.reset()
    logger.info("[CIRCUIT BREAKER] Manually reset via API.")
    return {"status": "reset", "state": llm_circuit.state}


@app.get("/api/circuit-status", tags=["System"])
async def circuit_status():
    """Check current circuit breaker state."""
    from llm.circuit_breaker import llm_circuit
    return {
        "state": llm_circuit.state,
        "failure_count": llm_circuit.failure_count,
        "call_timeout": llm_circuit.call_timeout,
        "recovery_timeout": llm_circuit.recovery_timeout,
    }



async def log_client_error(report: ClientErrorReport):
    """
    Receive and log a React ErrorBoundary crash report.

    Called fire-and-forget by the frontend ErrorBoundary — never raises,
    never blocks UI recovery.  Logged at WARNING level so it surfaces in
    production logs without being as noisy as ERROR level.
    """
    logger.warning(
        "[CLIENT-ERROR] %s | stack: %s | component: %s | ts: %s",
        report.message,
        (report.stack or "")[:300],
        (report.componentStack or "")[:300],
        report.timestamp,
    )
    return {"status": "logged"}


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
    # Connection limit check (Part 1)
    from agent.rate_limiter import rate_limiter
    client_ip = websocket.client.host if websocket.client else "unknown"
    registered_connection = False

    # ── Token Authentication Check ──
    token = websocket.query_params.get("token")
    if not token:
        logger.warning("Rejected WebSocket connection: missing token.")
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing auth token")
        return
        
    try:
        from agent import auth_utils
        import uuid
        payload = auth_utils.decode_token(token)
        user_uuid = uuid.UUID(payload["user_id"])
        email = payload["email"]
    except Exception as e:
        logger.warning("Rejected WebSocket connection: invalid auth token. Error: %s", e)
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid auth token")
        return

    if not rate_limiter.check_connection_limit(client_ip):
        await websocket.accept()
        await websocket.close(code=1008, reason="too many connections")
        return

    await websocket.accept()
    rate_limiter.register_connection(client_ip)
    registered_connection = True
    logger.info("Client connected and authenticated: %s (user_id=%s)", websocket.client, user_uuid)

    session_id = websocket.query_params.get("session_id") or f"{websocket.client.host}:{websocket.client.port}"
    user_id = str(user_uuid)

    session_voice_style = websocket.query_params.get("voice_style", "Friendly Mentor")
    session_accent = websocket.query_params.get("accent", "English (US) - Male")
    try:
        session_speech_speed = float(websocket.query_params.get("speech_speed", str(Config.KOKORO_SPEED)))
    except ValueError:
        session_speech_speed = Config.KOKORO_SPEED

    # Convert session_id to UUID
    session_uuid = None
    if agent_controller:
        session_uuid = agent_controller._to_uuid(session_id)

    # Pre-fetch user speech corrections from database
    user_corrections = []
    if db_manager and db_manager.enabled and user_uuid:
        try:
            user_corrections = await db_manager.fetch_user_corrections(user_uuid)
            logger.info("Pre-fetched %d speech corrections for user_id=%s", len(user_corrections), user_id)
        except Exception as exc:
            logger.error("Failed to pre-fetch user corrections: %s", exc)

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

    # Initialize SemanticEndpointer
    endpointer = SemanticEndpointer(EndpointingConfig(
        mode=EndpointingMode(Config.ENDPOINTING_MODE),
        min_silence_ms=Config.ENDPOINT_MIN_SILENCE_MS,
        default_silence_ms=int(Config.VAD_SILENCE_TIMEOUT * 1000),
        max_silence_ms=Config.ENDPOINT_MAX_SILENCE_MS,
        check_interval_ms=Config.ENDPOINT_CHECK_INTERVAL_MS,
    ))

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
                    discipline = "cse"
                    if profile_manager:
                        discipline = profile_manager.get_discipline()
                    initial_prompt = whisper_engine.get_prompt_for_discipline(discipline, user_corrections)

                    live_text = await loop.run_in_executor(
                        None,
                        lambda: whisper_engine.transcribe(audio_array, initial_prompt=initial_prompt)
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
            await _run_pipeline(
                websocket,
                raw_pcm,
                set_state,
                pre_transcribed,
                user_corrections,
                voice_style=session_voice_style,
                accent=session_accent,
                speech_speed=session_speech_speed
            )
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
                
                # Audio chunk size check (Part 2)
                if not validate_audio_chunk(chunk):
                    logger.warning("Dropped audio chunk exceeding size limit (%d bytes)", len(chunk))
                    from agent.security_logger import log_security_event
                    client_ip = websocket.client.host if websocket.client else "unknown"
                    asyncio.create_task(log_security_event(user_id, client_ip, "payload_too_large", f"Audio chunk exceeding size limit ({len(chunk)} bytes)"))
                    continue

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
                            
                            # Forced transcription cutoff (Part 2)
                            if speech_duration >= Config.MAX_UTTERANCE_SECONDS:
                                logger.info("VAD: Max utterance duration reached (%.2fs). Auto-triggering pipeline.", speech_duration)
                                speech_started = False
                                speech_duration = 0.0
                                silence_duration = 0.0
                                await trigger_pipeline(is_vad_trigger=True)
                                continue

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
                                silence_elapsed_ms = int(silence_duration * 1000)
                                decision = endpointer.decide(stabilizer.get_confirmed_text(), silence_elapsed_ms)
                                if decision.should_finalize:
                                    logger.info("VAD: Silence timeout reached (reason=%s) at %dms. Auto-triggering pipeline.", decision.reason, silence_elapsed_ms)
                                    speech_started = False
                                    speech_duration = 0.0
                                    silence_duration = 0.0
                                    await trigger_pipeline(is_vad_trigger=True)
                            else:
                                # Decay speech_duration slowly instead of wiping it out immediately,
                                # to handle quiet consonants or brief audio dips. Prevents voice pipeline cuts.
                                speech_duration = max(0.0, speech_duration - 0.032)

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

                elif msg_type == "text_query":
                    query_text = data.get("text", "")
                    if query_text:
                        if pipeline_task and not pipeline_task.done():
                            pipeline_task.cancel()
                            try:
                                await pipeline_task
                            except asyncio.CancelledError:
                                pass
                        if live_transcribe_task and not live_transcribe_task.done():
                            live_transcribe_task.cancel()

                        await set_state(ConversationState.TRANSCRIBING)
                        await websocket.send_json({
                            "type": "transcript",
                            "text": query_text,
                            "words": [{"word": w, "status": "confirmed"} for w in query_text.split()]
                        })
                        pipeline_task = asyncio.create_task(_run_pipeline_wrapper(b"", query_text))

                elif msg_type == "start_recording":
                    logger.info("Client started recording. Clearing audio chunks and resetting VAD/STT state.")
                    if live_transcribe_task and not live_transcribe_task.done():
                        live_transcribe_task.cancel()
                    if pipeline_task and not pipeline_task.done():
                        pipeline_task.cancel()
                    audio_chunks.clear()
                    vad_buffer = b""
                    speech_started = False
                    speech_duration = 0.0
                    silence_duration = 0.0
                    is_pipeline_running = False
                    final_transcript = ""
                    latest_live_transcript = ""
                    stabilizer.reset()

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

                elif msg_type == "settings_update":
                    settings = data.get("settings", {})
                    logger.info("Settings updated for session %s: %s", session_id, settings)
                    if "voice_style" in settings:
                        session_voice_style = settings["voice_style"]
                    if "accent" in settings:
                        session_accent = settings["accent"]
                    if "speech_speed" in settings:
                        try:
                            session_speech_speed = float(settings["speech_speed"])
                        except ValueError:
                            pass

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
        # Release connection (Part 1)
        if "registered_connection" in locals() and registered_connection:
            rate_limiter.release_connection(client_ip)
        # Save interruption state on unexpected disconnect to enable resuming
        if is_pipeline_running and agent_controller and pipeline_task and not pipeline_task.done():
            try:
                partial = agent_controller.get_partial_response(session_id)
                topic = agent_controller.get_current_topic(session_id)
                logger.info("Unexpected disconnect during active pipeline. Saving interrupt state for session %s (partial length: %d)", session_id, len(partial))
                interrupt_manager.save_state(
                    session_id=session_id,
                    partial_response=partial,
                    topic=topic,
                )
            except Exception as e:
                logger.warning("Failed to save disconnect interrupt state: %s", e)

        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        if live_transcribe_task and not live_transcribe_task.done():
            live_transcribe_task.cancel()


async def _run_pipeline(
    websocket: WebSocket,
    raw_pcm: bytes,
    set_state,
    pre_transcribed_text: Optional[str] = None,
    user_corrections: Optional[list[str]] = None,
    voice_style: Optional[str] = None,
    accent: Optional[str] = None,
    speech_speed: Optional[float] = None,
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

    # Connection ip-rate limits / daily limits (Part 1)
    from agent.rate_limiter import rate_limiter
    client_ip = websocket.client.host if websocket.client else "unknown"

    def map_accent_to_voice(acc: Optional[str]) -> str:
        """Map a voice display label (accent) to a Kokoro voice code.

        The frontend now sends exact Kokoro voice codes directly.
        We keep the old fuzzy fallbacks for backwards compat with any
        stored settings that use the old string format.
        """
        if not acc:
            return Config.KOKORO_VOICE

        # Full set of supported Kokoro-82M English voices
        VALID_VOICES = {
            # American Female
            "af_heart", "af_bella", "af_aoede", "af_kore", "af_sarah",
            "af_nova", "af_sky", "af_alloy", "af_jessica", "af_nicole", "af_river",
            # American Male
            "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
            "am_michael", "am_onyx", "am_puck",
            # British Female
            "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
            # British Male
            "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
        }

        # Direct code — pass through (new frontend format)
        if acc in VALID_VOICES:
            return acc

        # Legacy fuzzy fallback for old saved settings
        acc_lower = acc.lower()
        if "us" in acc_lower and "female" in acc_lower:
            return "af_bella"
        elif "us" in acc_lower and "male" in acc_lower:
            return "am_adam"
        elif "uk" in acc_lower and "female" in acc_lower:
            return "bf_emma"
        elif "uk" in acc_lower and "male" in acc_lower:
            return "bm_george"
        elif "female" in acc_lower:
            return "af_bella"
        elif "male" in acc_lower:
            return "am_adam"
        return Config.KOKORO_VOICE

    # Map selected accent to Kokoro voice name and compute base speech speed
    voice = map_accent_to_voice(accent)
    base_speech_speed = speech_speed if speech_speed is not None else Config.KOKORO_SPEED
    speed = base_speech_speed

    async def send_tts_response(ws: WebSocket, message: str):
        await set_state(ConversationState.THINKING)
        async def _message_stream():
            yield {"raw": message, "planned": message}
        start_time_tts = time.time()
        latency_metrics_tts = {}
        await _stream_llm_and_tts(
            ws,
            _message_stream(),
            loop,
            set_state,
            base_speech_speed,
            voice,
            latency_metrics_tts,
            start_time_tts,
            student_id=user_id
        )
        await set_state(ConversationState.IDLE)
        await ws.send_json({"type": "assistant_finished"})

    # Voice rate limiting (Part 2)
    allowed, rate_limit_msg = rate_limiter.check_voice_rate_limit(user_id)
    if not allowed:
        # Send the message back as a TTS response, not just an error
        # Student hears "slow down" rather than getting a silent drop
        await send_tts_response(websocket, rate_limit_msg)
        from agent.security_logger import log_security_event
        await log_security_event(
            user_id, client_ip, "rate_limit_hit",
            f"utterances_in_window={len(rate_limiter.requests_per_student[user_id])}"
        )
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "done"})
        return
    
    if not rate_limiter.check_daily_limit(user_id):
        from agent.security_logger import log_security_event
        asyncio.create_task(log_security_event(user_id, client_ip, "daily_limit_hit", "Daily request limit exceeded"))
        await websocket.send_json({"type": "error", "text": "You've hit your daily usage limit. Come back tomorrow."})
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "done"})
        return
        
    rate_limiter.increment_daily(user_id)

    user_uuid = None
    session_uuid = None
    if agent_controller:
        user_uuid = agent_controller._to_uuid(user_id)
        session_uuid = agent_controller._to_uuid(session_id)

    # ── 1. STT ───────────────────────────────────────────────────────────────
    audio_array = int16_bytes_to_float32(raw_pcm)

    # Ultrasonic / adversarial audio detection (Part 3A)
    is_safe, reason = check_audio_frequency_profile(audio_array, Config.AUDIO_SAMPLE_RATE)
    if not is_safe:
        logger.warning(f"[AUDIO GUARD] Frame rejected: {reason}")
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "done"})
        return
    
    # Utterance duration cap and noise filter validation (Part 2)
    duration_seconds = len(audio_array) / Config.AUDIO_SAMPLE_RATE
    if not validate_utterance_duration(duration_seconds):
        logger.warning("Utterance duration validation failed: %.2fs", duration_seconds)
        if duration_seconds < Config.MIN_UTTERANCE_MS / 1000:
            logger.info("Utterance too short (treated as noise) — responding with clarification prompt.")
            await set_state(ConversationState.THINKING)
            async def _short_audio_stream():
                yield {"raw": "Can you please repeat it once again?", "planned": "Can you please repeat it once again?"}
            await _stream_llm_and_tts(websocket, _short_audio_stream(), loop, set_state, speed, voice, latency_metrics, start_time)
            await set_state(ConversationState.IDLE)
            await websocket.send_json({"type": "assistant_finished"})
            return

    min_avg_logprob = 0.0
    try:
        if pre_transcribed_text:
            transcript = pre_transcribed_text
            logger.info("Using pre-transcribed text from live transcriber: %r", transcript)
            latency_metrics["whisper_done"] = 0.0
        else:
            logger.info("Transcribing %.1f seconds of audio …", len(audio_array) / Config.AUDIO_SAMPLE_RATE)

            discipline = "cse"
            if profile_manager:
                discipline = profile_manager.get_discipline()
            initial_prompt = whisper_engine.get_prompt_for_discipline(discipline, user_corrections)

            # Run blocking Whisper in a thread to keep the event loop free
            transcript, min_avg_logprob = await loop.run_in_executor(
                None,
                lambda: whisper_engine.transcribe_with_confidence(
                    audio_array, initial_prompt=initial_prompt
                )
            )
            latency_metrics["whisper_done"] = round(time.time() - start_time, 2)
    except Exception as stt_exc:
        logger.exception("STT Transcription failed: %s", stt_exc)
        # Notify the frontend of the user speech transcription error and explain gracefully
        await websocket.send_json({
            "type": "transcript", 
            "text": "[Speech recognition unavailable]", 
            "words": [{"word": "[Speech recognition unavailable]", "status": "confirmed"}]
        })
        await set_state(ConversationState.THINKING)
        # Yield a spoken error response using session settings
        async def mock_error_stream():
            yield {"raw": "I am sorry, but I failed to recognize your speech due to a local transcriber error. Please try again.", "planned": "I am sorry, but I failed to recognize your speech due to a local transcriber error. Please try again."}
        await _stream_llm_and_tts(websocket, mock_error_stream(), loop, set_state, speed, voice, latency_metrics, start_time)
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "assistant_finished"})
        return

    if not transcript:
        logger.info("Empty transcript — responding with clarification prompt.")
        await set_state(ConversationState.THINKING)
        async def _empty_transcript_stream():
            yield {"raw": "Can you please repeat it once again?", "planned": "Can you please repeat it once again?"}
        await _stream_llm_and_tts(websocket, _empty_transcript_stream(), loop, set_state, speed, voice, latency_metrics, start_time)
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "assistant_finished"})
        return

    # ── 1.5 Speech Normalization & Domain Correction ─────────────────────────
    from speech.normalizer import speech_normalizer
    normalized = speech_normalizer.normalize(transcript, session_id=session_id)

    discipline = "cse"
    active_topic = "general"
    if profile_manager:
        discipline = profile_manager.get_discipline()
        active_topic = profile_manager.get_active_topic()

    corrected_transcript, changes = domain_corrector.correct_sentence(normalized, discipline)

    # Check for low confidence to trigger context-aware LLM correction pass
    if not pre_transcribed_text and min_avg_logprob < Config.WHISPER_CORRECTION_THRESHOLD:
        logger.info("Confidence low (min_avg_logprob=%.2f < %.2f). Triggering LLM correction pass...", 
                    min_avg_logprob, Config.WHISPER_CORRECTION_THRESHOLD)

        CORRECTION_PROMPT = (
            f"You are a transcription correction tool for engineering students.\n"
            f"Active topic: {active_topic}\n"
            f"Discipline: {discipline}\n\n"
            f"Raw transcript: \"{corrected_transcript}\"\n\n"
            f"Rewrite ONLY correcting clear speech-to-text errors in technical terms "
            f"(e.g. \"chace\" -> \"cache\", \"colonel\" -> \"kernel\", \"reynolds number\" stays as is if correct).\n"
            f"Do NOT change meaning, grammar, or add words. Return ONLY the corrected sentence."
        )

        messages = [
            {"role": "system", "content": "You are a transcription correction tool for engineering students."},
            {"role": "user", "content": CORRECTION_PROMPT}
        ]

        llm_corrected = await llm_engine.get_completion(
            messages,
            max_tokens=Config.WHISPER_CORRECTION_MAX_TOKENS,
            timeout=Config.WHISPER_CORRECTION_TIMEOUT
        )

        if llm_corrected:
            llm_corrected_clean = llm_corrected.strip('"\'')
            if llm_corrected_clean and llm_corrected_clean != corrected_transcript:
                logger.info("LLM correction applied: %r -> %r", corrected_transcript, llm_corrected_clean)

                # Log to Postgres
                if db_manager and db_manager.enabled and user_uuid:
                    asyncio.create_task(
                        db_manager.write_speech_correction(
                            user_uuid, session_uuid, corrected_transcript, llm_corrected_clean, source="session"
                        )
                    )
                # Cache locally for biasing
                if user_corrections is not None and llm_corrected_clean not in user_corrections:
                    user_corrections.append(llm_corrected_clean)

                corrected_transcript = llm_corrected_clean

    elif changes:
        if db_manager and db_manager.enabled and user_uuid:
            for raw, corr in changes:
                asyncio.create_task(
                    db_manager.write_speech_correction(
                        user_uuid, session_uuid, raw, corr, source="session"
                    )
                )
                if user_corrections is not None and corr not in user_corrections:
                    user_corrections.append(corr)

    normalized_transcript = corrected_transcript

    if not normalized_transcript:
        logger.info("Empty normalized transcript — skipping pipeline.")
        await websocket.send_json({"type": "transcript", "text": "", "words": []})
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "done"})
        return

    # VAD silence abuse prevention (Part 3B)
    vad_speech_duration_ms = (len(audio_array) / Config.AUDIO_SAMPLE_RATE) * 1000
    if not is_utterance_substantial(normalized_transcript, vad_speech_duration_ms):
        logger.info(f"Ignoring unsubstantial utterance: {normalized_transcript!r} ({vad_speech_duration_ms:.1f}ms)")
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "done"})
        return

    # Idempotency check — same utterance within 1 second = skip (Part 1)
    if idempotency_guard.is_duplicate(session_id, normalized_transcript):
        logger.warning(f"[IDEMPOTENCY] Duplicate utterance dropped: {normalized_transcript[:40]}")
        from agent.security_logger import log_security_event
        await log_security_event(
            user_id, client_ip, "duplicate_utterance_dropped",
            f"transcript_hash={idempotency_guard._make_key(session_id, normalized_transcript)}"
        )
        await set_state(ConversationState.IDLE)
        await websocket.send_json({"type": "done"})
        return

    idempotency_guard.register(session_id, normalized_transcript)
    global utterance_count
    utterance_count += 1
    if utterance_count % 50 == 0:
        idempotency_guard.cleanup()

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

    speed = round(base_speech_speed * emotion_adjust, 2)
    logger.info("Dynamic Prosody: base_speed=%.2f, emotion=%s -> final_speed=%.2f, voice=%s",
                base_speech_speed, emotion_state.value, speed, voice)

    # Transition to THINKING state
    await set_state(ConversationState.THINKING)

    # ── 3. LLM streaming + TTS ────────────────────────────────────────────────
    client_ip = websocket.client.host if websocket.client else "unknown"
    if agent_controller is not None:
        # ── Agent path: full pipeline with intent, memory, safety, emotion ────
        token_stream = agent_controller.stream(
            normalized_transcript, session_id, user_id=user_id, audio_array=audio_array, ip_address=client_ip,
            voice_style=voice_style
        )
        await _stream_llm_and_tts(websocket, token_stream, loop, set_state, speed, voice, latency_metrics, start_time, student_id=user_id)
    else:
        # ── Legacy path: direct LLM call (AGENT_ENABLED=false) ───────────────
        token_stream = llm_engine.stream_tokens(normalized_transcript)
        await _stream_llm_and_tts(websocket, token_stream, loop, set_state, speed, voice, latency_metrics, start_time, student_id=user_id)

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
    student_id: Optional[str] = None,
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
        legacy_parser = None
        try:
            async for token_data in token_stream:
                # Record first LLM token latency
                if latency_metrics["first_llm_token"] is None:
                    latency_metrics["first_llm_token"] = round(time.time() - start_time, 2)

                events = []
                if isinstance(token_data, dict):
                    events = [token_data]
                elif isinstance(token_data, tuple):
                    events = [{"raw": token_data[0], "planned": token_data[1]}]
                else:
                    if legacy_parser is None:
                        from agent.realtime_parser import RealtimeStreamingParser
                        legacy_parser = RealtimeStreamingParser()
                    for event in legacy_parser.feed(token_data):
                        events.append(event)

                for event in events:
                    raw_token = event.get("raw", "") if isinstance(event, dict) else ""
                    planned_token = event.get("planned", "") if isinstance(event, dict) else event
                    
                    # Intercept parsed follow-up events and dispatch to client
                    followup = event.get("followup", "") if isinstance(event, dict) else ""
                    if followup:
                        await websocket.send_json({"type": "followup", "text": followup})

                    # Forward display-safe token to frontend immediately
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
                        # Flush on comma/clause ending punctuation only if minimum context length (10 chars) is met
                        elif len(stripped) >= 10 and re.search(r"(?<=\S{2})[,;:—\n\r]+['\"`’”\]\)]*(?:\s|$)", stripped):
                            should_flush = True
                        # Flush on space/word boundary if we've accumulated at least 15 characters (fast phrase split)
                        elif len(stripped) >= 15 and (raw_token and (raw_token.isspace() or any(char in raw_token for char in ".,!?;:-—"))):
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

                            # Split multi-line content (e.g. inline code without fences)
                            # into individual lines so TTS reads them one at a time.
                            if "\n" in sentence:
                                sub_lines = [l.strip() for l in sentence.split("\n") if l.strip()]
                                for sub_line in sub_lines:
                                    if not is_diagram_or_roadmap(sub_line):
                                        logger.debug("Enqueuing code line for TTS: %r", sub_line[:60])
                                        await tts_queue.put(sub_line)
                            else:
                                logger.debug("Enqueuing sentence for TTS: %r", sentence[:60])
                                # This will block if tts_queue is full (size >= 3), implementing backpressure
                                await tts_queue.put(sentence)
        except asyncio.CancelledError:
            logger.info("LLM token reader cancelled.")
            raise
        except Exception as exc:
            logger.exception("LLM token reading error: %s", exc)
        finally:
            if legacy_parser is not None:
                for event in legacy_parser.finalize():
                    raw_token = event.get("raw", "")
                    planned_token = event.get("planned", "")
                    followup = event.get("followup", "")
                    if followup:
                        await websocket.send_json({"type": "followup", "text": followup})
                    if raw_token:
                        await websocket.send_json({"type": "assistant_text_delta", "text": raw_token})
                    if planned_token:
                        sentence_buffer += planned_token

            final_sentence = sentence_buffer.strip()
            if final_sentence:
                from agent.response_planner import is_diagram_or_roadmap
                if not is_diagram_or_roadmap(final_sentence):
                    # Split multi-line final content line-by-line for TTS
                    if "\n" in final_sentence:
                        sub_lines = [l.strip() for l in final_sentence.split("\n") if l.strip()]
                        for sub_line in sub_lines:
                            if not is_diagram_or_roadmap(sub_line):
                                logger.debug("Enqueuing final code line for TTS: %r", sub_line[:60])
                                await tts_queue.put(sub_line)
                    else:
                        logger.debug("Enqueuing final sentence for TTS: %r", final_sentence[:60])
                        await tts_queue.put(final_sentence)
            # Enqueue sentinel to signal TTS worker to stop
            await tts_queue.put(None)

    # ── TTS Synthesis Worker ────────────────────────────────────────────────
    async def tts_worker():
        quota_exhausted_sent = False
        try:
            while True:
                sentence = await tts_queue.get()
                if sentence is None:
                    # Send sentinel to audio sender
                    await audio_queue.put(None)
                    tts_queue.task_done()
                    break
                
                from agent.output_sanitiser import sanitise
                sanitized_sentence = sanitise(sentence)
                logger.debug("TTS worker synthesizing: %r", sanitized_sentence[:60])
                # Synthesize sentence using dynamic speed and voice with fail-safe logic
                try:
                    wav_bytes = await loop.run_in_executor(None, lambda: kokoro_engine.synthesize(sanitized_sentence, speed, voice, student_id))
                    
                    if wav_bytes is None:
                        # Fallback to text-only (Part 7)
                        wav_bytes = b""
                        if not quota_exhausted_sent:
                            quota_exhausted_sent = True
                            notice = "You've used up today's voice budget — I'll keep responding in text for now."
                            await websocket.send_json({"type": "assistant_text_delta", "text": "\n\n" + notice})
                    
                    # Estimate word timestamps using the alignment engine
                    from speech.alignment import estimate_word_timestamps
                    try:
                        if wav_bytes:
                            timestamps = estimate_word_timestamps(sanitized_sentence, wav_bytes)
                        else:
                            timestamps = []
                    except Exception as align_exc:
                        logger.warning("Alignment engine failed: %s", align_exc)
                        timestamps = []
                except Exception as tts_exc:
                    logger.error("TTS synthesis failed for sentence %r: %s", sanitized_sentence, tts_exc)
                    wav_bytes = b""
                    timestamps = []

                await audio_queue.put({
                    "wav": wav_bytes,
                    "timestamps": timestamps,
                    "text": sanitized_sentence
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

