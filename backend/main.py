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
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["BLIS_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import sys

# Dynamically add NVIDIA cuDNN and cuBLAS bin paths to Windows DLL search directory and PATH
if sys.platform == "win32":
    for pkg in ["nvidia.cudnn", "nvidia.cublas"]:
        try:
            import importlib
            mod = importlib.import_module(pkg)
            bin_dir = os.path.join(os.path.dirname(mod.__file__), "bin")
            if os.path.exists(bin_dir):
                os.add_dll_directory(bin_dir)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]
        except Exception:
            pass
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
from request_queue.llm_queue import QueueFullError
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
# Configure standard logging to direct logs to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("edumentor.main")


class QueueingLLMEngine:
    """Wrap an LLM engine and route generation through Redis request queue."""

    def __init__(self, base_engine, request_queue):
        self._base_engine = base_engine
        self._request_queue = request_queue
        self.last_usage = None

    async def stream_tokens(self, user_text: str):
        return self._stream_via_queue(user_text, session_id="")

    async def stream_tokens_from_messages(self, messages: list, session_id: str = "", max_tokens=None):
        prompt_text = self._serialize_messages(messages)
        return self._stream_via_queue(prompt_text, session_id=session_id)

    def _serialize_messages(self, messages: list) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _stream_via_queue(self, prompt: str, session_id: str):
        request_id = await self._request_queue.enqueue(session_id, prompt)
        async for chunk in self._request_queue.stream_response(request_id):
            if chunk.get("type") == "token":
                yield chunk.get("data", "")
            elif chunk.get("type") == "error":
                raise RuntimeError(chunk.get("error", "LLM queue error"))
            elif chunk.get("type") == "done":
                return

    def __getattr__(self, name):
        return getattr(self._base_engine, name)


async def _run_queue_housekeeping(queue):
    try:
        while True:
            await asyncio.sleep(60)
            try:
                await queue.trim_acked()
                logger.debug("Redis queue housekeeping: trimmed acked entries.")
            except Exception as exc:
                logger.warning("Redis queue housekeeping failed: %s", exc)
    except asyncio.CancelledError:
        logger.info("Redis queue housekeeping task cancelled.")


redis_rate_limiter = None
queue_housekeeping_task = None


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
memory_manager:    Optional[MemoryManager]         = None

# Redis — only active when REDIS_ENABLED=true
redis_client       = None   # redis.asyncio.Redis instance
llm_request_queue  = None   # request_queue.llm_queue.LLMRequestQueue

# Multilingual pipeline — only active when MULTILINGUAL_ENABLED=true
multilingual_pipeline = None

hesitation_detector = None
hesitation_composer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all ML models and agent components once at startup; release on shutdown."""
    global whisper_engine, llm_engine, kokoro_engine, silero_vad_model
    global agent_controller, interrupt_manager, db_manager, profile_manager, domain_corrector, memory_manager
    global hesitation_detector, hesitation_composer

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

    # ── Initialize Redis (optional) ───────────────────────────────────────────
    global redis_client, llm_request_queue, redis_rate_limiter, queue_housekeeping_task
    if Config.REDIS_ENABLED:
        logger.info("REDIS_ENABLED=true — connecting to Redis at %s ...", Config.REDIS_URL)
        try:
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(
                Config.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            await redis_client.ping()
            logger.info("[OK] Redis connected.")

            from request_queue.llm_queue import LLMRequestQueue, QueueConfig
            llm_request_queue = LLMRequestQueue(redis_client, QueueConfig())
            await llm_request_queue.ensure_group()
            logger.info("[OK] LLM request queue ready (stream=%s).", QueueConfig().stream_key)

            from utils.redis_rate_limiter import RedisRateLimiter
            redis_rate_limiter = RedisRateLimiter(
                redis_client,
                limit=Config.VOICE_RATE_LIMIT_PER_MINUTE,
                window_seconds=Config.REDIS_RATE_LIMIT_WINDOW_SECONDS,
                key_prefix="voice_ratelimit",
            )

            queue_housekeeping_task = asyncio.create_task(_run_queue_housekeeping(llm_request_queue))
            logger.info("[OK] Redis queue housekeeping task started.")
        except Exception as redis_exc:
            logger.warning(
                "Redis connection failed (%s) — falling back to in-memory backends.", redis_exc
            )
            redis_client = None
            llm_request_queue = None
            redis_rate_limiter = None
            queue_housekeeping_task = None
    else:
        logger.info("REDIS_ENABLED=false — using in-memory backends.")

    # ── Initialize Agent Layer ────────────────────────────────────────────────
    if Config.AGENT_ENABLED:
        logger.info("Initializing Agent Layer...")

        interrupt_manager = InterruptManager()

        # Choose memory backend based on Redis availability
        if Config.REDIS_ENABLED and redis_client is not None and Config.MEMORY_BACKEND == "redis":
            _memory_backend = get_backend(
                "redis",
                redis_url=Config.REDIS_URL,
                ttl_seconds=Config.REDIS_MEMORY_TTL_SECONDS,
            )
        elif Config.MEMORY_BACKEND == "redis":
            logger.warning(
                "Redis memory backend requested but Redis is unavailable. Falling back to in-memory memory backend."
            )
            _memory_backend = get_backend("memory")
        else:
            _memory_backend = get_backend(Config.MEMORY_BACKEND)

        memory_manager = MemoryManager(
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
        await profile_manager.increment_session_count()

        from speech.domain_corrector import domain_corrector as dc
        domain_corrector = dc

        if llm_request_queue is not None:
            llm_engine = QueueingLLMEngine(llm_engine, llm_request_queue)

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

    # ── Initialize Hesitation Detection Layer ─────────────────────────────────
    from agent.hesitation_detector import HesitationDetector
    from agent.hesitation_composer import HesitationComposer, HesitationConfig
    
    hesitation_detector = HesitationDetector()
    hesitation_composer = HesitationComposer(
        HesitationConfig(enabled=Config.HESITATION_DETECTION_ENABLED)
    )

    # ── Multilingual Pipeline (optional) ─────────────────────────────────────
    global multilingual_pipeline
    if Config.MULTILINGUAL_ENABLED:
        logger.info("MULTILINGUAL_ENABLED=true — initializing multilingual pipeline ...")
        try:
            from speech.multilingual_pipeline import get_multilingual_pipeline
            multilingual_pipeline = get_multilingual_pipeline(
                whisper_engine=whisper_engine,
                agent_controller=agent_controller,
                llm_engine=llm_engine,
            )
            logger.info("[OK] Multilingual pipeline ready.")
        except Exception as ml_exc:
            logger.error("Failed to initialize multilingual pipeline: %s", ml_exc)
            logger.warning("Falling back to English-only mode.")
            multilingual_pipeline = None
    else:
        logger.info("Multilingual pipeline disabled (MULTILINGUAL_ENABLED=false).")

    # ── STEP 1: Runtime config dump (actual in-process values) ────────────────
    logger.info("=" * 60)
    logger.info("[RUNTIME CONFIG] MULTILINGUAL_ENABLED = %s", Config.MULTILINGUAL_ENABLED)
    logger.info("[RUNTIME CONFIG] WHISPER_MODEL        = %s", Config.WHISPER_MODEL)
    logger.info("[RUNTIME CONFIG] WHISPER_DEVICE       = %s", Config.WHISPER_DEVICE)
    logger.info("[RUNTIME CONFIG] WHISPER_COMPUTE_TYPE = %s", Config.WHISPER_COMPUTE_TYPE)
    nllb_device = os.getenv("NLLB_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
    mms_tts_device = os.getenv("MMS_TTS_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
    logger.info("[RUNTIME CONFIG] NLLB_DEVICE          = %s", nllb_device)
    logger.info("[RUNTIME CONFIG] MMS_TTS_DEVICE       = %s", mms_tts_device)
    logger.info("=" * 60)
    if Config.REDIS_ENABLED and redis_client is not None:
        from agent.analytics_aggregator import start_analytics_aggregator
        asyncio.create_task(start_analytics_aggregator(redis_client, db_manager))

    yield  # Server is running

    # Shutdown
    logger.info("Shutting down engines ...")
    from agent.analytics_aggregator import stop_analytics_aggregator
    await stop_analytics_aggregator()

    if queue_housekeeping_task is not None:
        queue_housekeeping_task.cancel()
        try:
            await queue_housekeeping_task
        except asyncio.CancelledError:
            pass
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


@app.get("/metrics", tags=["System"])
def metrics_endpoint():
    """
    Expose collected Prometheus metrics for scraping.

    NOTE: If this backend is ever exposed publicly, /metrics should be restricted
    (e.g., via IP allowlist, reverse proxy rules, or hosting on a separate
    internal-only port) because operational metrics can leak system details.
    """
    import prometheus_client
    try:
        data = prometheus_client.generate_latest()
        return Response(
            content=data,
            media_type=prometheus_client.CONTENT_TYPE_LATEST
        )
    except Exception as e:
        logger.error("Failed to generate Prometheus metrics: %s", e, exc_info=True)
        return Response(
            content="Internal Server Error: Failed to generate metrics",
            status_code=500,
            media_type="text/plain"
        )


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
                # Explicitly send form-encoded data (Google expects x-www-form-urlencoded)
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                token_res = await client.post(token_url, data=data, headers=headers)
                # If the token endpoint returns an error (400/401/etc), capture body for debugging
                if token_res.status_code != 200:
                    logger.error(
                        "Google token endpoint error: status=%s body=%s",
                        token_res.status_code,
                        token_res.text[:1000]
                    )
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
            except httpx.HTTPStatusError as hs_err:
                # Log full response text (truncated) for diagnosis without leaking secrets
                resp = getattr(hs_err, 'response', None)
                body = resp.text[:2000] if resp is not None else str(hs_err)
                logger.error("Google OAuth token exchange failed: %s", body)
                raise HTTPException(status_code=400, detail="Google authentication failed (token exchange error)")
            except Exception as e:
                logger.exception("Failed to perform Google OAuth exchange: %s", e)
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


@app.get("/api/sessions", tags=["Profile"])
async def get_session_history(
    limit: int = 50,
    user: dict = Depends(get_current_user)
):
    """
    Return a list of past sessions for the authenticated user.
    Each session is the first message exchange in a session_id group from conversation_logs.
    Returns: list of { session_id, title (first query truncated), created_at, turns, intent_category, disciplines }
    """
    user_id_str = user.get("user_id")
    import uuid as _uuid
    user_id = _uuid.UUID(user_id_str)

    if not db_manager or not db_manager.pool:
        return []

    query = """
    SELECT
        session_id,
        MIN(created_at)   AS session_start,
        MAX(created_at)   AS session_end,
        COUNT(*)          AS turns,
        MIN(query_text)   AS first_query,
        array_agg(DISTINCT intent_category ORDER BY intent_category) FILTER (WHERE intent_category IS NOT NULL) AS intents,
        SUM(tokens_in)    AS total_tokens_in,
        SUM(tokens_out)   AS total_tokens_out,
        SUM(latency_ms)   AS total_latency_ms
    FROM conversation_logs
    WHERE user_id = $1
    GROUP BY session_id
    ORDER BY MIN(created_at) DESC
    LIMIT $2;
    """
    try:
        async with db_manager.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, limit)
            sessions = []
            for r in rows:
                first_q = r["first_query"] or ""
                title = (first_q[:60] + "…") if len(first_q) > 60 else first_q
                sessions.append({
                    "session_id": str(r["session_id"]),
                    "title": title or "Voice Session",
                    "created_at": r["session_start"].isoformat() if r["session_start"] else None,
                    "ended_at": r["session_end"].isoformat() if r["session_end"] else None,
                    "turns": r["turns"],
                    "intents": list(r["intents"]) if r["intents"] else [],
                    "tokens_in": r["total_tokens_in"] or 0,
                    "tokens_out": r["total_tokens_out"] or 0,
                    "avg_latency_ms": round(r["total_latency_ms"] / r["turns"]) if r["turns"] and r["total_latency_ms"] else 0,
                })
            return sessions
    except Exception as e:
        logger.error("Failed to fetch session history for user_id=%s: %s", user_id, e)
        return []


@app.get("/api/sessions/heatmap", tags=["Profile"])
async def get_session_heatmap(
    days: int = 90,
    user: dict = Depends(get_current_user)
):
    """
    Return daily session counts for the last N days for the consistency heatmap.
    Returns: list of { date: YYYY-MM-DD, count: int }
    """
    user_id_str = user.get("user_id")
    import uuid as _uuid
    user_id = _uuid.UUID(user_id_str)

    if not db_manager or not db_manager.pool:
        return []

    query = """
    SELECT
        DATE(created_at AT TIME ZONE 'UTC') AS activity_date,
        COUNT(DISTINCT session_id)          AS sessions,
        COUNT(*)                            AS turns
    FROM conversation_logs
    WHERE user_id = $1
      AND created_at >= CURRENT_DATE - ($2 * INTERVAL '1 day')
    GROUP BY activity_date
    ORDER BY activity_date ASC;
    """
    try:
        async with db_manager.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, days)
            return [
                {
                    "date": str(r["activity_date"]),
                    "count": r["turns"],
                    "sessions": r["sessions"],
                }
                for r in rows
            ]
    except Exception as e:
        logger.error("Failed to fetch heatmap for user_id=%s: %s", user_id, e)
        return []


@app.get("/api/sessions/{session_id}/messages", tags=["Profile"])
async def get_session_messages(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Return all messages for a specific session_id.
    Matches standard UI message object structure.
    Returns: list of messages, sorted chronologically.
    """
    user_id_str = user.get("user_id")
    import uuid as _uuid
    user_id = _uuid.UUID(user_id_str)
    
    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        # If it is a frontend placeholder ID or not a valid UUID, return empty list
        return []

    if not db_manager or not db_manager.pool:
        return []

    query = """
    SELECT id, query_text, response_text, created_at, intent_category
    FROM conversation_logs
    WHERE user_id = $1 AND session_id = $2
    ORDER BY created_at ASC;
    """
    try:
        async with db_manager.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, session_uuid)
            messages = []
            for r in rows:
                q_time = r["created_at"].isoformat() if r["created_at"] else None
                # Create user message
                messages.append({
                    "id": f"u-{r['id']}",
                    "role": "user",
                    "text": r["query_text"],
                    "timestamp": q_time,
                    "intent": r["intent_category"]
                })
                # Create assistant message
                messages.append({
                    "id": f"a-{r['id']}",
                    "role": "assistant",
                    "text": r["response_text"],
                    "timestamp": q_time
                })
            return messages
    except Exception as e:
        logger.error("Failed to fetch session messages for user_id=%s, session_id=%s: %s", user_id, session_id, e)
        return []


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
    live_transcribed_len_samples = 0

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
        nonlocal final_transcript, latest_live_transcript, live_transcribed_len_samples
        try:
            from speech.normalizer import speech_normalizer
            while True:
                await asyncio.sleep(Config.LIVE_TRANSCRIPTION_INTERVAL)
                current_len = len(audio_chunks)
                if current_len > 0:
                    new_bytes = b"".join(audio_chunks[:current_len])
                    audio_array = int16_bytes_to_float32(new_bytes)
                    if Config.MULTILINGUAL_ENABLED:
                        initial_prompt = Config.MULTILINGUAL_WHISPER_PROMPT
                    else:
                        initial_prompt = whisper_engine.get_prompt_for_discipline(discipline, user_corrections)

                    live_text = await loop.run_in_executor(
                        None,
                        lambda: whisper_engine.transcribe(
                            audio_array,
                            initial_prompt=initial_prompt,
                            language=None,  # Allow auto-detection during live feedback
                        )
                    )
                    live_transcribed_len_samples = len(audio_array)
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
            try:
                await live_transcribe_task
            except asyncio.CancelledError:
                pass

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
                speech_speed=session_speech_speed,
                live_transcribed_len=live_transcribed_len_samples
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

        # Trigger analytics session end flush
        if Config.REDIS_ENABLED:
            try:
                from agent.analytics_aggregator import get_analytics_aggregator
                agg = get_analytics_aggregator()
                if agg:
                    asyncio.create_task(agg.on_session_end(session_id, user_id))
            except Exception as e:
                logger.error("Failed to trigger analytics session end flush: %s", e)

        # Clean up session states to prevent memory leaks (Finding #2)
        if agent_controller:
            agent_controller.remove_session(session_id)
        if memory_manager:
            memory_manager.clear_session(session_id)

        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
            try:
                await pipeline_task
            except asyncio.CancelledError:
                pass
        if live_transcribe_task and not live_transcribe_task.done():
            live_transcribe_task.cancel()
            try:
                await live_transcribe_task
            except asyncio.CancelledError:
                pass




async def _run_pipeline(
    websocket: WebSocket,
    raw_pcm: bytes,
    set_state,
    pre_transcribed_text: Optional[str] = None,
    user_corrections: Optional[list[str]] = None,
    voice_style: Optional[str] = None,
    accent: Optional[str] = None,
    speech_speed: Optional[float] = None,
    live_transcribed_len: Optional[int] = None,
) -> None:
    """
    Execute the full STT → LLM → TTS pipeline for one user utterance.

    Steps:
      1. Convert raw Int16 bytes → Float32 numpy array
      2. Whisper transcription (in thread executor to avoid blocking)
      3. Stream LLM tokens + sentence-buffer TTS in parallel
      4. Send "done" when everything is complete
    """
    def clean_speak_text(text: str) -> str:
        import re
        if not text:
            return ""
        # Strip out <show> blocks and their contents
        text = re.sub(r"<show(?:\s+[^>]*)?>.*?</show>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Strip out <followup> blocks and their contents
        text = re.sub(r"<followup>.*?</followup>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Strip out markdown code fences and their contents
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        # Strip remaining tag boundaries
        text = re.sub(r"</?(?:speak|show|followup)(?:\s+[^>]*)?>", "", text, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip()


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
    if redis_rate_limiter is not None:
        allowed, rate_limit_msg = await redis_rate_limiter.check_voice_rate_limit(user_id)
    else:
        allowed, rate_limit_msg = rate_limiter.check_voice_rate_limit(user_id)

    if not allowed:
        # Send the message back as a TTS response, not just an error
        # Student hears "slow down" rather than getting a silent drop
        await send_tts_response(websocket, rate_limit_msg)
        from agent.security_logger import log_security_event
        await log_security_event(
            user_id, client_ip, "rate_limit_hit",
            f"utterances_in_window={user_id}"
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

    # ── MULTILINGUAL BRANCH ───────────────────────────────────────────────────
    # When MULTILINGUAL_ENABLED=true and the multilingual pipeline is ready,
    # delegate the entire turn to it.
    if multilingual_pipeline is not None:
        audio_array_ml = int16_bytes_to_float32(raw_pcm)

        # 1. Frequency profile safety check (adversarial/ultrasonic check)
        is_safe, reason = check_audio_frequency_profile(audio_array_ml, Config.AUDIO_SAMPLE_RATE)
        if not is_safe:
            logger.warning(f"[AUDIO GUARD] Multilingual frame rejected: {reason}")
            await set_state(ConversationState.IDLE)
            await websocket.send_json({"type": "done"})
            return

        # 2. Utterance duration cap and noise filter validation.
        # Bypass duration checks if text_query (pre_transcribed_text) is provided since no audio is sent.
        if not pre_transcribed_text:
            duration_seconds = len(audio_array_ml) / Config.AUDIO_SAMPLE_RATE
            if not validate_utterance_duration(duration_seconds):
                logger.warning("Multilingual utterance duration validation failed: %.2fs", duration_seconds)
                if duration_seconds < Config.MIN_UTTERANCE_MS / 1000:
                    logger.info("Multilingual utterance too short (treated as noise) — responding with clarification prompt.")
                    await set_state(ConversationState.THINKING)
                    async def _short_audio_stream():
                        yield {"raw": "Can you please repeat it once again?", "planned": "Can you please repeat it once again?"}
                    await _stream_llm_and_tts(websocket, _short_audio_stream(), loop, set_state, speed, voice, latency_metrics, start_time)
                    await set_state(ConversationState.IDLE)
                    await websocket.send_json({"type": "assistant_finished"})
                    return

        total_samples = len(audio_array_ml)
        can_bypass_stt = (
            pre_transcribed_text
            and live_transcribed_len is not None
            and (total_samples - live_transcribed_len) <= 4800
        )
        if can_bypass_stt:
            logger.info(
                "[ML-STAGE-1-BYPASS] Bypassing final STT: reusing live transcript %r (audio length delta: %.3fs)",
                pre_transcribed_text, (total_samples - live_transcribed_len) / 16000
            )
            transcript = pre_transcribed_text
            whisper_lang = None
            stt_latency = 0.0
        else:
            t_stt = time.time()
            logger.info("[ML-STAGE-1] STT: calling multilingual transcribe (no forced language) ...")

            def _transcribe_runner():
                return multilingual_pipeline.transcribe_multilingual(
                    audio_array_ml,
                    initial_prompt=Config.MULTILINGUAL_WHISPER_PROMPT
                )

            transcript, whisper_lang, stt_latency = await loop.run_in_executor(None, _transcribe_runner)
            logger.info(
                "[ML-STAGE-1] STT done in %.3fs | whisper_lang=%r | transcript repr=%r",
                stt_latency, whisper_lang, transcript
            )

            # If full STT returned nothing, fall back to the live transcript as a last resort
            if not transcript and pre_transcribed_text:
                logger.info(
                    "[ML-STAGE-1] Full STT empty — falling back to live transcript: %r",
                    pre_transcribed_text,
                )
                transcript = pre_transcribed_text
                whisper_lang = None
                stt_latency = 0.0


        if not transcript:
            logger.info("[ML-STAGE-1] Empty multilingual transcript — responding with clarification prompt.")
            await set_state(ConversationState.THINKING)
            async def _empty_transcript_stream():
                yield {"raw": "Can you please repeat it once again?", "planned": "Can you please repeat it once again?"}
            await _stream_llm_and_tts(websocket, _empty_transcript_stream(), loop, set_state, speed, voice, latency_metrics, start_time)
            await set_state(ConversationState.IDLE)
            await websocket.send_json({"type": "assistant_finished"})
            return

        # Retrieve profile preferences first to bias routing decisions
        lang_pref = "auto"
        glossary_mode = "english"
        if agent_controller is not None:
            profile_fut = agent_controller._profile_manager.get_profile(session_id)
            if asyncio.iscoroutine(profile_fut) or hasattr(profile_fut, "__await__"):
                profile = await profile_fut
            else:
                profile = profile_fut

            if profile:
                lang_pref = getattr(profile, "output_language_preference", "auto")
                glossary_mode = getattr(profile, "glossary_mode", "english")

        # Older profiles and manual edits may use codes (``hi``) or title case.
        # Keep downstream translation and TTS routing on canonical names.
        lang_pref = multilingual_pipeline.router.normalize_language(lang_pref) or "auto"

        stt_text = transcript

        # 2. Language Router
        logger.info("[ML-STAGE-2] Router input: text repr=%r | whisper_lang=%r | lang_pref=%r", transcript, whisper_lang, lang_pref)
        route_lang, route_meta = multilingual_pipeline.router.route(transcript, whisper_lang, lang_pref)
        logger.info(
            "[ML-STAGE-2] Router output: route_lang=%r | reason=%r | routing_path=%r",
            route_lang, route_meta.get("reason"), route_meta.get("routing_path")
        )

        # Increment Prometheus metric
        routing_path = route_meta.get("routing_path", "hindi-default")
        try:
            from observability.metrics import language_routing_total
            language_routing_total.labels(routing_path=routing_path, route_lang=route_lang).inc()
        except Exception as exc:
            logger.warning("Failed to record language routing metric: %s", exc)

        # Send transcript event so frontend shows what was heard
        if stt_text:
            confirmed_words = [{"word": w, "status": "confirmed"} for w in stt_text.split()]
            await websocket.send_json({
                "type": "transcript",
                "text": stt_text,
                "words": confirmed_words,
                "route_lang": route_lang,
            })

        # ── Explicit output-language request detection ────────────────────────
        # The user may speak English but explicitly ask for a response in Hindi,
        # Marathi, or Kannada (e.g. "explain in Hindi", "give me a roadmap in Marathi").
        # detect_requested_output_language() scans the transcript for such phrases
        # and, if found, overrides the response language regardless of route_lang.
        requested_output_lang = multilingual_pipeline.router.detect_requested_output_language(transcript)
        if requested_output_lang:
            logger.info(
                "[ML-STAGE-2] Explicit output-language request detected in English utterance: %r → override response_lang=%r",
                transcript[:80], requested_output_lang,
            )

        # Determine target output language
        # Priority: explicit request > user profile preference > route_lang
        if requested_output_lang:
            response_lang = requested_output_lang
        elif lang_pref != "auto":
            response_lang = lang_pref
        else:
            response_lang = route_lang

        logger.info("[ML-STAGE-2] response_lang=%r (requested=%r, lang_pref=%r, route_lang=%r)",
                    response_lang, requested_output_lang, lang_pref, route_lang)

        # 3. Input translation (only for kannada / marathi)
        # Note: if the user spoke English but requested an Indic output, the input is still
        # English — we pass it directly to the LLM and only translate the *output*.
        llm_input = transcript
        needs_input_translation = route_lang in ("hindi", "kannada", "marathi")
        logger.info(
            "[ML-STAGE-3] Translation check: needs_input_translation=%s | route_lang=%r | response_lang=%r",
            needs_input_translation, route_lang, response_lang
        )
        if needs_input_translation and transcript:
            from i18n.term_glossary import protect_terms, restore_terms
            t_trans_in = time.time()
            protected_transcript, mapping = protect_terms(transcript, route_lang)
            logger.info("[ML-STAGE-3] Translating to EN: protected repr=%r", protected_transcript)
            english_input_protected, trans_lat = multilingual_pipeline.translate_to_english(protected_transcript, route_lang)
            llm_input = restore_terms(english_input_protected, mapping, mode="english")
            logger.info(
                "[ML-STAGE-3] Translate-IN done in %.3fs | en_input repr=%r",
                trans_lat, llm_input
            )
        else:
            logger.info("[ML-STAGE-3] Translation skipped — LLM input repr=%r", llm_input)

        # Determine TTS engine selection
        use_mms_for_hindi = False
        if response_lang == "hindi":
            has_devanagari = multilingual_pipeline.router.contains_devanagari_script(transcript)
            # Use MMS-TTS for Hindi when: user explicitly requested Hindi, profile preference is Hindi,
            # or auto-routed as Hindi with Devanagari script present.
            use_mms_for_hindi = (
                requested_output_lang == "hindi"
                or lang_pref == "hindi"
                or (lang_pref == "auto" and route_lang == "hindi" and has_devanagari)
            )

        tts_engine = "mms" if (response_lang in ("kannada", "marathi") or use_mms_for_hindi) else "kokoro"
        logger.info("[ML-STAGE-4] TTS engine selected: %r | use_mms_for_hindi=%s", tts_engine, use_mms_for_hindi)


        # 4. Stream LLM response & TTS
        import base64
        if tts_engine == "kokoro":
            # English response — stream through Kokoro
            if agent_controller is not None:
                llm_stream = agent_controller.stream(
                    llm_input, session_id, user_id=user_id,
                    audio_array=audio_array_ml, ip_address=client_ip,
                    voice_style=voice_style, response_lang=response_lang,
                    original_query=transcript
                )
            else:
                llm_stream = llm_engine.stream_tokens(llm_input)

            await set_state(ConversationState.THINKING)
            try:
                await _stream_llm_and_tts(
                    websocket, llm_stream, loop, set_state,
                    speed, voice, latency_metrics, start_time, student_id=user_id, session_id=session_id
                )
                if agent_controller:
                    await agent_controller.emit_turn_event(
                        session_id, user_id, was_interrupted=False, start_time=start_time, response_lang=response_lang
                    )
            except asyncio.CancelledError:
                if agent_controller:
                    await agent_controller.emit_turn_event(
                        session_id, user_id, was_interrupted=True, start_time=start_time, response_lang=response_lang
                    )
                raise
        else:
            # Indic response — stream, translate, synthesize sentence-by-sentence
            if agent_controller is not None:
                llm_stream = agent_controller.stream(
                    llm_input, session_id, user_id=user_id,
                    audio_array=audio_array_ml, ip_address=client_ip,
                    voice_style=voice_style, response_lang=response_lang,
                    original_query=transcript
                )
            else:
                llm_stream = llm_engine.stream_tokens(llm_input)

            translation_queue = asyncio.Queue()
            tts_queue = asyncio.Queue()
            audio_queue = asyncio.Queue()
            # Accumulates all translated sentences for DB back-fill
            _translated_sentences: list[str] = []

            async def llm_reader():
                sentence_buffer = ""
                t_llm_start = time.time()
                ttft = None
                is_first_chunk = True
                try:
                    async for token_dict in llm_stream:
                        if ttft is None:
                            ttft = time.time() - t_llm_start
                            try:
                                from observability.metrics import multilingual_llm_ttft_seconds
                                multilingual_llm_ttft_seconds.labels(language=response_lang).observe(ttft)
                            except Exception as exc:
                                logger.warning("Failed to record LLM TTFT metric: %s", exc)

                        raw_token = token_dict.get("raw", "")
                        planned_token = token_dict.get("planned", "")
                        followup_text = token_dict.get("followup", "")

                        if raw_token:
                            sentence_buffer += raw_token
                            
                            should_flush = False
                            stripped = sentence_buffer.strip()
                            
                            # For translation routes (kannada, marathi), we want sentence-level translation
                            # to prevent fragmentation and keep translation quality high.
                            # For direct native routes (hindi) or english, we can use fast clause-level flushing.
                            if response_lang in ("kannada", "marathi"):
                                import re
                                # Flush on sentence boundary
                                if len(stripped) >= 3 and re.search(r"(?<=\S{2})[.!?|।]+['\"`’”\]\)]*(?:\s|$)", stripped):
                                    should_flush = True
                                # Fallback if it exceeds a high character limit (e.g. 220 chars) to prevent infinite buffering
                                elif len(stripped) >= 220:
                                    should_flush = True
                            else:
                                # Standard fast clause-level flushing for native/english paths
                                if is_first_chunk:
                                    import re
                                    if len(stripped) >= 3 and re.search(r"(?<=\S{2})[.!?]+['\"`’”\]\)]*(?:\s|$)", stripped):
                                        should_flush = True
                                    elif len(stripped) >= 8 and re.search(r"(?<=\S{2})[,;:—\n\r]+['\"`’”\]\)]*(?:\s|$)", stripped):
                                        should_flush = True
                                    # Flush on word boundary at 10+ chars - faster Time-to-First-Audio
                                    elif len(stripped) >= 10 and (raw_token and (raw_token.isspace() or any(char in raw_token for char in ".,!?;:-—"))):
                                        should_flush = True
                                    elif len(stripped) >= Config.TTS_CHUNK_CHARS:
                                        should_flush = True
                                else:
                                    if is_sentence_complete(sentence_buffer) or len(sentence_buffer) >= Config.TTS_CHUNK_CHARS:
                                        should_flush = True

                            if should_flush:
                                if sentence_buffer.strip():
                                    logger.info("[ML-LLM-READER] Flushing raw sentence to translation_queue: %r", sentence_buffer)
                                    await translation_queue.put(sentence_buffer)
                                sentence_buffer = ""
                                is_first_chunk = False

                        if followup_text:
                            # Translate followup_text to the target language before sending
                            from speech.multilingual_pipeline import NLLB_LANG_MAP
                            tc = NLLB_LANG_MAP.get(response_lang, "hin_Deva")
                            def _trans_followup(text=followup_text, tc_code=tc):
                                _translated, _ = multilingual_pipeline.translator.translate(
                                    text, "eng_Latn", tc_code
                                )
                                return _translated
                            translated_followup = await loop.run_in_executor(None, _trans_followup)
                            await websocket.send_json({"type": "followup", "text": translated_followup})

                    if sentence_buffer.strip():
                        logger.info("[ML-LLM-READER] Flushing final raw remainder to translation_queue: %r", sentence_buffer)
                        await translation_queue.put(sentence_buffer)
                except Exception as exc:
                    logger.exception("[ML-LLM-READER] ERROR in LLM reader: %s", exc)
                    # Ensure downstream workers are not left waiting forever
                    await translation_queue.put(None)
                    raise
                finally:
                    llm_latency = time.time() - t_llm_start
                    logger.info("[ML-LLM-READER] Complete in %.3fs — putting sentinel to translation_queue", llm_latency)
                    try:
                        from observability.metrics import multilingual_llm_completion_seconds
                        multilingual_llm_completion_seconds.labels(language=response_lang).observe(llm_latency)
                    except Exception as exc:
                        logger.warning("Failed to record LLM completion metric: %s", exc)
                    await translation_queue.put(None)

            async def translator_worker():
                nonlocal _translated_sentences
                from speech.multilingual_pipeline import NLLB_LANG_MAP
                tgt_code = NLLB_LANG_MAP.get(response_lang, "hin_Deva")
                from i18n.term_glossary import protect_terms, restore_terms, protect_visual_blocks, restore_visual_blocks
                sent_idx = 0
                last_sentence = ""
                try:
                    while True:
                        eng_sentence = await translation_queue.get()
                        logger.info("[ML-TRANS-WORKER] Got from translation_queue[%d]: %r", sent_idx, eng_sentence)
                        if eng_sentence is None:
                            logger.info("[ML-TRANS-WORKER] Sentinel received — done translating.")
                            break
                        gl_mode = glossary_mode
                        resp_lang = response_lang



                        def _full_translate(sentence=eng_sentence, tc=tgt_code):
                            # 1. Protect visual blocks (fences/tags)
                            sentence_no_vis, vis_mapping = protect_visual_blocks(sentence)
                            
                            # 2. Protect glossary terms
                            t_prot = time.time()
                            _protected, _mapping = protect_terms(sentence_no_vis)
                            _prot_lat = time.time() - t_prot

                            # 3. Translate using NLLB
                            t_trans = time.time()
                            _translated_protected, _ = multilingual_pipeline.translator.translate(
                                _protected, "eng_Latn", tc
                            )
                            _trans_lat = time.time() - t_trans

                            # 4. Restore glossary terms
                            t_rest = time.time()
                            _translated_no_vis = restore_terms(
                                _translated_protected, _mapping,
                                mode=gl_mode, target_language=resp_lang
                            )
                            _rest_lat = time.time() - t_rest
                            
                            # 5. Restore visual blocks
                            _translated = restore_visual_blocks(_translated_no_vis, vis_mapping)

                            return _translated, _prot_lat, _trans_lat, _rest_lat

                        t_total = time.time()
                        translated, prot_latency, trans_latency, rest_latency = await loop.run_in_executor(
                            None, _full_translate
                        )
                        logger.info(
                            "[ML-TRANS-WORKER] Translated[%d] in %.3fs | result repr=%r",
                            sent_idx, trans_latency, translated
                        )

                        try:
                            from observability.metrics import (
                                multilingual_glossary_protect_seconds,
                                multilingual_translate_out_seconds,
                                multilingual_glossary_restore_seconds
                            )
                            multilingual_glossary_protect_seconds.labels(language=response_lang).observe(prot_latency)
                            multilingual_translate_out_seconds.labels(language=response_lang).observe(trans_latency)
                            multilingual_glossary_restore_seconds.labels(language=response_lang).observe(rest_latency)
                        except Exception as exc:
                            logger.warning("Failed to record translate_out stages metrics: %s", exc)

                        logger.info("[ML-TRANS-WORKER] Putting sentence[%d] to tts_queue.", sent_idx)
                        translated = translated.strip()
                        
                        # Determine delimiter to prepend (newline before/after code blocks or visual cards)
                        delim = " "
                        if last_sentence:
                            is_curr_block = translated.startswith("```") or translated.startswith("<show") or translated.startswith("<followup")
                            is_prev_block = last_sentence.endswith("```") or last_sentence.endswith("</show>") or last_sentence.endswith("</followup>")
                            if is_curr_block or is_prev_block:
                                delim = "\n\n"
                        
                        stream_text = (delim if sent_idx > 0 else "") + translated
                        await websocket.send_json({"type": "assistant_text_delta", "text": stream_text})
                        _translated_sentences.append(translated)
                        last_sentence = translated
                        
                        # Strip show blocks, followup blocks, and tags from translated text to get the clean text for TTS
                        import re
                        tts_clean = re.sub(r"<show(?:\s+[^>]*)?>.*?</show>", "", translated, flags=re.DOTALL | re.IGNORECASE)
                        tts_clean = re.sub(r"<followup>.*?</followup>", "", tts_clean, flags=re.DOTALL | re.IGNORECASE)
                        tts_clean = re.sub(r"```.*?```", "", tts_clean, flags=re.DOTALL)
                        tts_clean = re.sub(r"</?(?:speak|show|followup|code)(?:\s+[^>]*)?>", "", tts_clean, flags=re.IGNORECASE)
                        tts_clean = tts_clean.strip()
                        
                        from i18n.term_glossary import transliterate_latin_words
                        translated_tts = transliterate_latin_words(tts_clean, response_lang)
                        
                        # Chunk the translated sentence for TTS to keep audio synthesis chunks small and fast
                        import re
                        def _split_for_tts(text_val: str) -> list[str]:
                            pattern = re.compile(r"([^,;!?।|\n\r.]+[,;!?।|\n\r.]*)")
                            raw_chunks = pattern.findall(text_val)
                            chunks = []
                            current_chunk = ""
                            for rc in raw_chunks:
                                if len(current_chunk) + len(rc) < 80:
                                    current_chunk += rc
                                else:
                                    if current_chunk.strip():
                                        chunks.append(current_chunk.strip())
                                    current_chunk = rc
                            if current_chunk.strip():
                                chunks.append(current_chunk.strip())
                            if not chunks and text_val.strip():
                                chunks.append(text_val.strip())
                            return chunks
                            
                        tts_chunks = _split_for_tts(translated_tts)
                        logger.info("[ML-TRANS-WORKER] Split translated sentence[%d] into %d TTS chunks: %r", sent_idx, len(tts_chunks), tts_chunks)
                        for chunk in tts_chunks:
                            await tts_queue.put(chunk)
                            
                        translation_queue.task_done()
                        sent_idx += 1
                except Exception as exc:
                    logger.exception("[ML-TRANS-WORKER] ERROR: %s", exc)
                    # Propagate sentinel so tts_worker doesn't hang
                    await tts_queue.put(None)
                    raise
                finally:
                    logger.info("[ML-TRANS-WORKER] Putting sentinel to tts_queue.")
                    await tts_queue.put(None)


            async def tts_worker():
                from speech.multilingual_pipeline import MMS_TTS_LANG_MAP
                from i18n.term_glossary import transliterate_latin_words
                mms_lang = MMS_TTS_LANG_MAP.get(response_lang, "hin")
                is_first_sentence = True
                tts_idx = 0
                sentence_buffer = ""

                # Helper to check if text contains native characters for target Indic language.
                # Crucial to prevent VITS modeling pad crashes resulting from zero-token output.
                def has_native_script_characters(text: str) -> bool:
                    from i18n.term_glossary import normalize_lang
                    norm_lang = normalize_lang(response_lang)
                    if norm_lang in ("hindi", "marathi"):
                        return any('\u0900' <= char <= '\u097f' for char in text)
                    elif norm_lang == "kannada":
                        return any('\u0c80' <= char <= '\u0cff' for char in text)
                    return True

                async def synthesize_and_enqueue(text: str, use_kokoro: bool = False):
                    nonlocal is_first_sentence, tts_idx
                    t_tts = time.time()
                    if use_kokoro:
                        logger.info("[ML-TTS-WORKER] Synthesizing[%d] with Kokoro fallback stream: %r ...", tts_idx, text)
                        q = asyncio.Queue()
                        quota_exhausted_sent = False
                        
                        def run_synthesis_thread(loop_inst, q_inst):
                            try:
                                generator = kokoro_engine.synthesize_stream(text, speed, "af_heart", user_id)
                                if generator is None:
                                    loop_inst.call_soon_threadsafe(q_inst.put_nowait, "QUOTA_EXCEEDED")
                                    return
                                
                                has_yielded = False
                                for gs, wav_bytes in generator:
                                    has_yielded = True
                                    loop_inst.call_soon_threadsafe(q_inst.put_nowait, (gs, wav_bytes))
                                
                                if not has_yielded:
                                    loop_inst.call_soon_threadsafe(q_inst.put_nowait, (text, b""))
                                
                                loop_inst.call_soon_threadsafe(q_inst.put_nowait, None)
                            except Exception as e:
                                logger.error("Error in synthesis thread: %s", e)
                                loop_inst.call_soon_threadsafe(q_inst.put_nowait, e)

                        import threading
                        threading.Thread(
                            target=run_synthesis_thread,
                            args=(loop, q),
                            daemon=True
                        while True:
                            item = await q.get()
                            if item is None:
                                q.task_done()
                                break
                            if item == "QUOTA_EXCEEDED":
                                q.task_done()
                                if not quota_exhausted_sent:
                                    quota_exhausted_sent = True
                                    notice = "You've used up today's voice budget — I'll keep responding in text for now."
                                    await websocket.send_json({"type": "assistant_text_delta", "text": "\n\n" + notice})
                                await audio_queue.put(b"")
                                break
                            if isinstance(item, Exception):
                                q.task_done()
                                raise item
                            
                            gs, wav_bytes = item
                            if wav_bytes:
                                logger.info("[ML-TTS-WORKER] Putting streamed Kokoro chunk (%d bytes) to audio_queue.", len(wav_bytes))
                                await audio_queue.put(wav_bytes)
                            q.task_done()
                        
                        tts_latency = time.time() - t_tts
                        logger.info("[ML-TTS-WORKER] Synth[%d] streaming done in %.3fs", tts_idx, tts_latency)
                        
                        try:
                            from observability.metrics import (
                                multilingual_tts_ttf_seconds,
                                multilingual_tts_completion_seconds
                            )
                            if is_first_sentence:
                                is_first_sentence = False
                                multilingual_tts_ttf_seconds.labels(language=response_lang).observe(tts_latency)
                            multilingual_tts_completion_seconds.labels(language=response_lang).observe(tts_latency)
                        except Exception as exc:
                            logger.warning("Failed to record TTS metrics in main: %s", exc)
                    else:
                        logger.info("[ML-TTS-WORKER] Synthesizing[%d] with mms_lang=%r: %r ...", tts_idx, mms_lang, text)
                        wav_bytes = await loop.run_in_executor(
                            None, lambda: multilingual_pipeline.mms_tts.synthesize(text, mms_lang)
                        )
                        tts_latency = time.time() - t_tts
                        logger.info(
                            "[ML-TTS-WORKER] Synth[%d] done in %.3fs | wav_bytes len=%d (empty=%s)",
                            tts_idx, tts_latency, len(wav_bytes), len(wav_bytes) == 0
                        )

                        if len(wav_bytes) == 0:
                            logger.error(
                                "[ML-TTS-WORKER] MMS-TTS returned EMPTY bytes for sentence[%d]=%r lang=%r",
                                tts_idx, text, mms_lang
                            )

                        try:
                            from observability.metrics import (
                                multilingual_tts_ttf_seconds,
                                multilingual_tts_completion_seconds
                            )
                            if is_first_sentence:
                                is_first_sentence = False
                                multilingual_tts_ttf_seconds.labels(language=response_lang).observe(tts_latency)
                            multilingual_tts_completion_seconds.labels(language=response_lang).observe(tts_latency)
                        except Exception as exc:
                            logger.warning("Failed to record TTS metrics in main: %s", exc)

                        logger.info("[ML-TTS-WORKER] Putting audio[%d] (%d bytes) to audio_queue.", tts_idx, len(wav_bytes))
                        await audio_queue.put(wav_bytes)
                    tts_idx += 1

                try:
                    while True:
                        sentence = await tts_queue.get()
                        if sentence is not None:
                            real_content_started["flag"] = True
                        logger.info("[ML-TTS-WORKER] Got from tts_queue: %r", sentence)
                        
                        if sentence is None:
                            logger.info("[ML-TTS-WORKER] Sentinel received — done synthesizing. Flashing remaining buffer: %r", sentence_buffer)
                            if sentence_buffer.strip():
                                final_sentence = sentence_buffer.strip()
                                # Fallback: if remaining text is pure Latin, force-transliterate it to native script
                                if not has_native_script_characters(final_sentence):
                                    has_glossary_term = False
                                    if glossary_mode == "english":
                                        from i18n.term_glossary import GLOSSARY_TERMS
                                        import re
                                        words = re.findall(r"[a-zA-Z]+", final_sentence)
                                        if any(w.lower() in GLOSSARY_TERMS for w in words):
                                            has_glossary_term = True

                                    if has_glossary_term:
                                        logger.info("[ML-TTS-WORKER] Sentinel flush: glossary-protected English term %r detected — routing to Kokoro.", final_sentence)
                                        await synthesize_and_enqueue(final_sentence, use_kokoro=True)
                                    else:
                                        logger.info("[ML-TTS-WORKER] Sentinel flush: pure Latin chunk detected, force-transliterating %r", final_sentence)
                                        final_sentence = transliterate_latin_words(final_sentence, response_lang)
                                        await synthesize_and_enqueue(final_sentence)
                                else:
                                    await synthesize_and_enqueue(final_sentence)
                            break

                        # If chunk has no native script characters, buffer it
                        if not has_native_script_characters(sentence):
                            logger.info("[ML-TTS-WORKER] Pure Latin chunk detected %r — buffering for adjacent native script merge.", sentence)
                            sentence_buffer = (sentence_buffer + " " + sentence).strip()
                            tts_queue.task_done()
                            continue

                        # If we have buffered text, prepend it to this native script chunk
                        if sentence_buffer:
                            sentence = (sentence_buffer + " " + sentence).strip()
                            sentence_buffer = ""

                        await synthesize_and_enqueue(sentence)
                        tts_queue.task_done()
                        tts_idx += 1
                except Exception as exc:
                    logger.exception("[ML-TTS-WORKER] ERROR: %s", exc)
                    # Propagate sentinel so audio_sender doesn't hang
                    await audio_queue.put(None)
                    raise
                finally:
                    logger.info("[ML-TTS-WORKER] Putting sentinel to audio_queue.")
                    await audio_queue.put(None)

            async def audio_sender():
                first_audio_sent = False
                audio_idx = 0
                try:
                    while True:
                        wav_bytes = await audio_queue.get()
                        logger.info("[ML-AUDIO-SENDER] Got from audio_queue[%d]: len=%s sentinel=%s",
                                    audio_idx, len(wav_bytes) if wav_bytes is not None else "N/A", wav_bytes is None)
                        if wav_bytes is None:
                            logger.info("[ML-AUDIO-SENDER] Sentinel received — done sending audio.")
                            break

                        if wav_bytes:
                            if not first_audio_sent:
                                first_audio_sent = True
                                latency_metrics["first_audio"] = round(time.time() - start_time, 2)
                                await set_state(ConversationState.SPEAKING)
                                await websocket.send_json({"type": "tts_start"})
                                logger.info("[ML-AUDIO-SENDER] First audio sent to frontend at %.2fs", latency_metrics["first_audio"])

                            base64_wav = base64.b64encode(wav_bytes).decode("utf-8")
                            await websocket.send_json({
                                "type": "audio_chunk",
                                "audio": base64_wav,
                                "word_timestamps": []
                            })
                            logger.info("[ML-AUDIO-SENDER] Sent audio_chunk[%d] (%d bytes wav).", audio_idx, len(wav_bytes))
                        else:
                            logger.warning("[ML-AUDIO-SENDER] Skipping empty wav_bytes at index %d.", audio_idx)
                        audio_queue.task_done()
                        audio_idx += 1
                except Exception as exc:
                    logger.exception("[ML-AUDIO-SENDER] ERROR: %s", exc)
                    raise

            _FILLER_DELAY_SECONDS = 0.6  # fires if translation/LLM hasn't started streaming within 600ms
            
            _ML_FILLER_PHRASES = {
                "hindi": ["ठीक है, देखते हैं।", "अरे, एक सेकंड दीजिए।"],
                "kannada": ["ಸರಿ, ನೋಡೋಣ.", "ಒಂದು ಕ್ಷಣ ತಡೆಯಿರಿ."],
                "marathi": ["ठीक आहे, पाहूया.", "एक क्षण द्या."],
                "english": ["Okay, let's see.", "Alright, one moment."]
            }

            def _pick_ml_filler_text(lang) -> str:
                import random
                pool = _ML_FILLER_PHRASES.get(lang, _ML_FILLER_PHRASES["english"])
                return random.choice(pool)

            async def filler_watchdog():
                try:
                    await asyncio.sleep(_FILLER_DELAY_SECONDS)
                    if real_content_started["flag"]:
                        return  # real content already started queuing — don't add a filler
                    
                    filler_text = _pick_ml_filler_text(response_lang)
                    logger.info("[ML-FILLER-WATCHDOG] Fired! Synthesizing filler: %r in %r", filler_text, response_lang)
                    
                    from speech.multilingual_pipeline import MMS_TTS_LANG_MAP
                    if tts_engine == "kokoro":
                        wav_bytes = await loop.run_in_executor(
                            None, lambda: kokoro_engine.synthesize(filler_text, speed, voice, user_id)
                        )
                    else:
                        mms_lang = MMS_TTS_LANG_MAP.get(response_lang, "hin")
                        wav_bytes = await loop.run_in_executor(
                            None, lambda: multilingual_pipeline.mms_tts.synthesize(filler_text, mms_lang)
                        )
                    
                    if real_content_started["flag"]:
                        return  # real content started while we were synthesizing — drop the filler
                    
                    if wav_bytes:
                        logger.info("[ML-FILLER-WATCHDOG] Enqueuing filler audio to audio_queue.")
                        await audio_queue.put(wav_bytes)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("Multilingual filler watchdog failed (non-fatal): %s", exc)

            await set_state(ConversationState.THINKING)
            real_content_started = {"flag": False}
            reader_task = asyncio.create_task(llm_reader())
            trans_task = asyncio.create_task(translator_worker())
            tts_task = asyncio.create_task(tts_worker())
            sender_task = asyncio.create_task(audio_sender())
            filler_task = asyncio.create_task(filler_watchdog())

            # Task supervisor wrapper to monitor workers. If any task raises an exception (crashes),
            # we catch it, cancel sibling tasks immediately, notify client, and fail cleanly.
            try:
                try:
                    await asyncio.gather(reader_task, trans_task, tts_task, sender_task)
                    filler_task.cancel()
                    try:
                        await filler_task
                    except asyncio.CancelledError:
                        pass
                    if agent_controller:
                        await agent_controller.emit_turn_event(
                            session_id, user_id, was_interrupted=False, start_time=start_time, response_lang=response_lang
                        )
                except asyncio.CancelledError:
                    if agent_controller:
                        await agent_controller.emit_turn_event(
                            session_id, user_id, was_interrupted=True, start_time=start_time, response_lang=response_lang
                        )
                    raise
            except Exception as pipeline_exc:
                if not isinstance(pipeline_exc, asyncio.CancelledError):
                    logger.error("[MULTILINGUAL] Supervisor detected pipeline worker crash: %s", pipeline_exc)
                # Cancel remaining tasks
                for t in [reader_task, trans_task, tts_task, sender_task, filler_task]:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(reader_task, trans_task, tts_task, sender_task, filler_task, return_exceptions=True)
                if not isinstance(pipeline_exc, asyncio.CancelledError):
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "text": f"Pipeline failure: {str(pipeline_exc)}"
                        })
                    except Exception:
                        pass
                raise

            # Back-fill DB with the translated response and confirmed language
            if _translated_sentences and db_manager is not None and agent_controller is not None:
                full_translated = ""
                for idx, sent in enumerate(_translated_sentences):
                    sent = sent.strip()
                    if not sent:
                        continue
                    if not full_translated:
                        full_translated = sent
                    else:
                        is_curr_block = sent.startswith("```") or sent.startswith("<show") or sent.startswith("<followup")
                        is_prev_block = full_translated.endswith("```") or full_translated.endswith("</show>") or full_translated.endswith("</followup>")
                        if is_curr_block or is_prev_block:
                            full_translated += "\n\n" + sent
                        else:
                            full_translated += " " + sent
                try:
                    _u_uuid = agent_controller._to_uuid(user_id)
                    _s_uuid = agent_controller._to_uuid(session_id)
                    asyncio.create_task(db_manager.update_log_translation(
                        user_id=_u_uuid,
                        session_id=_s_uuid,
                        translated_response=full_translated,
                        response_lang=response_lang,
                    ))
                    logger.info(
                        "[MULTILINGUAL] Scheduled DB translation back-fill: lang=%s len=%d",
                        response_lang, len(full_translated)
                    )
                except Exception as _bf_exc:
                    logger.warning("[MULTILINGUAL] DB back-fill failed: %s", _bf_exc)


        await set_state(ConversationState.IDLE)
        latency_metrics["complete"] = round(time.time() - start_time, 2)
        logger.info(
            "[MULTILINGUAL] Turn complete | route=%s | response_lang=%s | first_audio=%.2fs | complete=%.2fs",
            route_lang, response_lang, float(latency_metrics.get("first_audio") or -1), latency_metrics["complete"]
        )
        await websocket.send_json({"type": "assistant_finished"})
        return

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

    total_samples = len(audio_array)
    can_bypass_stt = (
        pre_transcribed_text
        and live_transcribed_len is not None
        and (total_samples - live_transcribed_len) <= 4800
    )
    min_avg_logprob = 0.0
    try:
        if can_bypass_stt:
            logger.info(
                "[STAGE-1-BYPASS] Bypassing final STT: reusing live transcript %r (audio length delta: %.3fs)",
                pre_transcribed_text, (total_samples - live_transcribed_len) / 16000
            )
            transcript = pre_transcribed_text
            min_avg_logprob = 0.0
            latency_metrics["whisper_done"] = 0.0
        else:
            # Always run the full Whisper STT to get the accurate final transcript.
            # pre_transcribed_text is a partial live capture and must not bypass real STT.
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

            # If full STT returned nothing, fall back to the live transcript as a last resort
            if not transcript and pre_transcribed_text:
                logger.info("Full STT empty — falling back to live transcript: %r", pre_transcribed_text)
                transcript = pre_transcribed_text
                min_avg_logprob = 0.0
                latency_metrics["whisper_done"] = 0.0

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

    # ── Hesitation Detection ──────────────────────────────────────────────────
    is_hesitation = False
    hesitation_text = ""
    if Config.HESITATION_DETECTION_ENABLED:
        overall_rms = float(np.sqrt(np.mean(audio_array ** 2))) if (audio_array is not None and len(audio_array) > 0) else 0.0
        signal = hesitation_detector.detect(normalized_transcript, audio_energy_signal=overall_rms)
        if signal.detected:
            current_topic = None
            if agent_controller and agent_controller._profile_manager:
                current_topic = await agent_controller._profile_manager.get_active_topic(session_id)
            hesitation_response = hesitation_composer.compose(session_id, signal, current_topic=current_topic)
            if hesitation_response:
                is_hesitation = True
                hesitation_text = hesitation_response

    # ── 3. LLM streaming + TTS ────────────────────────────────────────────────
    client_ip = websocket.client.host if websocket.client else "unknown"
    if is_hesitation:
        async def _hesitation_stream():
            yield {"raw": hesitation_text, "planned": hesitation_text}
        token_stream = _hesitation_stream()
    else:
        if agent_controller is not None:
            # ── Agent path: full pipeline with intent, memory, safety, emotion ────
            token_stream = agent_controller.stream(
                normalized_transcript, session_id, user_id=user_id, audio_array=audio_array, ip_address=client_ip,
                voice_style=voice_style
            )
        else:
            # ── Legacy path: direct LLM call (AGENT_ENABLED=false) ───────────────
            token_stream = llm_engine.stream_tokens(normalized_transcript)

    try:
        await _stream_llm_and_tts(
            websocket, token_stream, loop, set_state, speed, voice, latency_metrics, start_time,
            student_id=user_id, emotion_state=emotion_state, session_id=session_id
        )
        if agent_controller and not is_hesitation:
            await agent_controller.emit_turn_event(
                session_id, user_id, was_interrupted=False, start_time=start_time, response_lang="english"
            )
    except asyncio.CancelledError:
        if agent_controller and not is_hesitation:
            await agent_controller.emit_turn_event(
                session_id, user_id, was_interrupted=True, start_time=start_time, response_lang="english"
            )
        raise

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
    emotion_state: Optional[Emotion] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Simultaneously stream LLM tokens to the frontend AND generate TTS audio
    sentence-by-sentence using a 3-queue architecture with backpressure.
    """
    # Queues
    tts_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=3)
    audio_queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=3)
    sentence_buffer = ""
    tts_and_llm_start = time.time()
    real_content_started = {"flag": False}   # set True the instant tts_worker dequeues its first real sentence

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
                        # Flush on comma/clause ending punctuation only if minimum context length (8 chars) is met
                        elif len(stripped) >= 8 and re.search(r"(?<=\S{2})[,;:—\n\r]+['\"`’”\]\)]*(?:\s|$)", stripped):
                            should_flush = True
                        # Flush on word boundary at 10+ chars (was 15) - faster Time-to-First-Audio
                        elif len(stripped) >= 10 and (raw_token and (raw_token.isspace() or any(char in raw_token for char in ".,!?;:-—"))):
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
                
                real_content_started["flag"] = True
                from agent.output_sanitiser import sanitise
                sanitized_sentence = sanitise(sentence)
                logger.debug("TTS worker synthesizing: %r", sanitized_sentence[:60])
                try:
                    q = asyncio.Queue()
                    
                    def run_synthesis_thread(loop_inst, q_inst):
                        try:
                            generator = kokoro_engine.synthesize_stream(sanitized_sentence, speed, voice, student_id)
                            if generator is None:
                                loop_inst.call_soon_threadsafe(q_inst.put_nowait, "QUOTA_EXCEEDED")
                                return
                            
                            has_yielded = False
                            for gs, wav_bytes in generator:
                                has_yielded = True
                                loop_inst.call_soon_threadsafe(q_inst.put_nowait, (gs, wav_bytes))
                            
                            if not has_yielded:
                                loop_inst.call_soon_threadsafe(q_inst.put_nowait, (sanitized_sentence, b""))
                            
                            loop_inst.call_soon_threadsafe(q_inst.put_nowait, None)
                        except Exception as e:
                            logger.error("Error in synthesis thread: %s", e)
                            loop_inst.call_soon_threadsafe(q_inst.put_nowait, e)

                    import threading
                    threading.Thread(
                        target=run_synthesis_thread,
                        args=(loop, q),
                        daemon=True
                    ).start()
                    
                    while True:
                        item = await q.get()
                        if item is None:
                            q.task_done()
                            break
                        if item == "QUOTA_EXCEEDED":
                            q.task_done()
                            if not quota_exhausted_sent:
                                quota_exhausted_sent = True
                                notice = "You've used up today's voice budget — I'll keep responding in text for now."
                                await websocket.send_json({"type": "assistant_text_delta", "text": "\n\n" + notice})
                            await audio_queue.put({
                                "wav": b"",
                                "timestamps": [],
                                "text": sanitized_sentence
                            })
                            break
                        if isinstance(item, Exception):
                            q.task_done()
                            raise item
                        
                        gs, wav_bytes = item
                        from speech.alignment import estimate_word_timestamps
                        try:
                            if wav_bytes and gs:
                                timestamps = estimate_word_timestamps(gs, wav_bytes)
                            else:
                                timestamps = []
                        except Exception as align_exc:
                            logger.warning("Alignment engine failed: %s", align_exc)
                            timestamps = []

                        await audio_queue.put({
                            "wav": wav_bytes,
                            "timestamps": timestamps,
                            "text": gs
                        })
                        q.task_done()
                except Exception as tts_exc:
                    logger.error("TTS synthesis stream failed for sentence %r: %s", sanitized_sentence, tts_exc)
                    await audio_queue.put({
                        "wav": b"",
                        "timestamps": [],
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

    _FILLER_DELAY_SECONDS = 0.6  # fires if LLM hasn't started streaming within 600ms; keeps UX alive during TTFT

    _FILLER_PHRASES = {
        "default": ["Okay, let's see.", "Alright, one moment."],
        "frustrated_or_confused": ["No worries, let's take a look.", "Okay, let's break this down."],
        "confident": ["Nice, let's see.", "Good, let's dig in."],
    }

    def _pick_filler_text(emotion_state) -> str:
        import random
        from agent.models import Emotion
        if emotion_state in (Emotion.FRUSTRATED, Emotion.CONFUSED):
            pool = _FILLER_PHRASES["frustrated_or_confused"]
        elif emotion_state == Emotion.CONFIDENT:
            pool = _FILLER_PHRASES["confident"]
        else:
            pool = _FILLER_PHRASES["default"]
        return random.choice(pool)

    async def filler_watchdog():
        if emotion_state is None:
            return  # only run for the real agent path, not fallback/offline streams
        try:
            await asyncio.sleep(_FILLER_DELAY_SECONDS)
            if real_content_started["flag"]:
                return  # real content already started queuing — don't add a filler
            filler_text = _pick_filler_text(emotion_state)
            wav_bytes = await loop.run_in_executor(
                None, lambda: kokoro_engine.synthesize(filler_text, speed, voice, student_id)
            )
            if real_content_started["flag"]:
                return  # real content started while we were synthesizing — drop the filler, don't play it late
            if wav_bytes:
                await audio_queue.put({"wav": wav_bytes, "timestamps": [], "text": filler_text})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Filler watchdog failed (non-fatal): %s", exc)

    # Spawn tasks
    reader_task = asyncio.create_task(llm_token_reader())
    worker_task = asyncio.create_task(tts_worker())
    sender_task = asyncio.create_task(audio_sender())
    filler_task = asyncio.create_task(filler_watchdog())

    try:
        # Wait until all subtasks complete
        await asyncio.gather(reader_task, worker_task, sender_task)
        filler_task.cancel()
        try:
            await filler_task
        except asyncio.CancelledError:
            pass
    except asyncio.CancelledError:
        logger.info("LLM/TTS streaming gathering cancelled. Cancelling subtasks.")
        reader_task.cancel()
        worker_task.cancel()
        sender_task.cancel()
        filler_task.cancel()
        await asyncio.gather(reader_task, worker_task, sender_task, filler_task, return_exceptions=True)
        raise


# For translation routes (kannada, marathi), we want sentence-level translation to prevent fragmentation.
