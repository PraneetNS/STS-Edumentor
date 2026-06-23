"""
EduMentor Voice — Central Configuration
All settings are driven by environment variables with sensible defaults.
Copy .env.example to .env and adjust before starting the server.
"""

import os
import torch
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ─────────────────────────────────────────────
    # Whisper (STT) settings
    # ─────────────────────────────────────────────
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base.en")
    WHISPER_BEAM_SIZE: int = int(os.getenv("WHISPER_BEAM_SIZE", "5"))


    # Auto-detect GPU; fall back to CPU
    WHISPER_DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"

    # float16 on GPU for speed; int8 on CPU for efficiency
    WHISPER_COMPUTE_TYPE: str = "float16" if WHISPER_DEVICE == "cuda" else "int8"

    # Disable Whisper internal VAD filter since we run Silero VAD
    WHISPER_VAD_FILTER: bool = False

    # ── Voice Activity Detection (VAD) ───────────────────────────────────────
    VAD_ENGINE: str = os.getenv("VAD_ENGINE", "silero")
    VAD_THRESHOLD: float = float(os.getenv("VAD_THRESHOLD", "0.5"))
    VAD_SILENCE_TIMEOUT: float = float(os.getenv("VAD_SILENCE_TIMEOUT", "0.8"))
    MIN_SPEECH_DURATION: float = float(os.getenv("MIN_SPEECH_DURATION", "0.3"))
    LIVE_TRANSCRIPTION_INTERVAL: float = float(os.getenv("LIVE_TRANSCRIPTION_INTERVAL", "0.7"))

    WHISPER_PROMPT: str = (
        "EduMentor technical terms:\n"
        "Python\n"
        "JavaScript\n"
        "React\n"
        "FastAPI\n"
        "CUDA\n"
        "GPU\n"
        "recursion\n"
        "dynamic programming\n"
    )

    # ── TTS Chunker settings ──────────────────────────────────────────────────
    TTS_CHUNK_CHARS: int = int(os.getenv("TTS_CHUNK_CHARS", "120"))

    # ─────────────────────────────────────────────
    # LLM settings (llama.cpp OpenAI-compat server)
    # ─────────────────────────────────────────────
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:8080")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "local")
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "512"))
    # Voice-tuned generation settings — warm and natural, not robotic
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.55"))
    LLM_TOP_P: float = float(os.getenv("LLM_TOP_P", "0.9"))
    LLM_REPEAT_PENALTY: float = float(os.getenv("LLM_REPEAT_PENALTY", "1.1"))
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "120"))

    LLM_SYSTEM_PROMPT: str = (
        "You are Edi. You are a friendly AI tutor that explains programming "
        "and computer science concepts clearly. Keep your answers concise, accurate, "
        "and easy to understand for students.\n\n"
        
        "Your responses must be structured using these three tag types (and only these tag types):\n"
        "- Wrap everything read aloud by TTS inside <speak>...</speak> tags.\n"
        "- Wrap anything rendered visually (never spoken) inside <show type=\"code|roadmap|workflow|table|checklist\" lang=\"...\">...</show> tags.\n"
        "- Wrap a single context-specific short follow-up question inside <followup>...</followup> tags at the very end.\n\n"

        "Identity Rules (CRITICAL):\n"
        "- Your name is Edi. You are an AI programming mentor at EduMentor.\n"
        "- If asked about your identity, creator, or model name, ALWAYS stay in character as Edi from EduMentor.\n"
        "- Do NOT claim that you place students in companies or promise job/placement outcomes at specific companies (like Google, Microsoft, etc.). Focus strictly on concept learning.\n"
        "- Do NOT claim you are only for specific school grades (like 2nd or 3rd grade). You are a learning assistant for students of all levels.\n\n"

        "Your goal:\n"
        "Help students deeply understand programming, AI, mathematics, and technology.\n\n"

        "Teaching behavior:\n"
        "- Explain concepts step by step.\n"
        "- Prefer intuition before technical definitions.\n"
        "- Use simple examples.\n"
        "- Detect confusion and slow down.\n"
        "- If a student is frustrated, reassure them briefly and simplify.\n"
        "- Do not overwhelm beginners.\n"
        "- For advanced students, increase depth.\n\n"

        "Voice behavior:\n"
        "You are speaking through real-time voice. Therefore:\n"
        "- Keep responses conversational inside speak tags.\n"
        "- Avoid markdown inside speak tags.\n"
        "- Avoid long lists.\n"
        "- Use natural spoken sentences.\n"
        "- Prefer short paragraphs.\n"
        "- Never say 'as an AI language model'.\n\n"

        "Debugging behavior:\n"
        "When solving errors:\n"
        "1. Identify the likely cause.\n"
        "2. Explain why it happens.\n"
        "3. Give the fix.\n"
        "4. Suggest prevention.\n"
        "Do not just give answers. Teach the reasoning."
    )

    # ─────────────────────────────────────────────
    # Kokoro TTS settings
    # ─────────────────────────────────────────────
    KOKORO_VOICE: str = os.getenv("KOKORO_VOICE", "af_heart")
    KOKORO_SPEED: float = float(os.getenv("KOKORO_SPEED", "1.0"))
    KOKORO_SAMPLE_RATE: int = 24000          # Kokoro native sample rate
    KOKORO_LANG_CODE: str = os.getenv("KOKORO_LANG_CODE", "a")  # 'a' = American English

    # ─────────────────────────────────────────────
    # Audio pipeline settings
    # ─────────────────────────────────────────────
    AUDIO_SAMPLE_RATE: int = 16000           # Browser → backend PCM sample rate
    AUDIO_CHANNELS: int = 1                  # Mono

    # ─────────────────────────────────────────────
    # Server settings
    # ─────────────────────────────────────────────
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS: list = ["*"]

    # ─────────────────────────────────────────────
    # Agent Layer settings
    # ─────────────────────────────────────────────

    # Master switch: set to "false" to use direct LLM calls (legacy mode)
    AGENT_ENABLED: bool = os.getenv("AGENT_ENABLED", "true").lower() == "true"

    # Intent classification: set to "false" to skip (saves ~1-3s per turn)
    # Falls back to CONCEPT_EXPLANATION intent when disabled
    AGENT_INTENT_CLASSIFY: bool = os.getenv("AGENT_INTENT_CLASSIFY", "true").lower() == "true"

    # Safety guards: set to "false" to disable (NOT recommended for production)
    AGENT_SAFETY_ENABLED: bool = os.getenv("AGENT_SAFETY_ENABLED", "true").lower() == "true"

    # ─────────────────────────────────────────────
    # Memory settings
    # ─────────────────────────────────────────────

    # Number of recent turns to keep in the active memory window
    MEMORY_MAX_TURNS: int = int(os.getenv("MEMORY_MAX_TURNS", "10"))

    # Storage backend: "memory" | "sqlite" | "redis"
    MEMORY_BACKEND: str = os.getenv("MEMORY_BACKEND", "memory")

    # ─────────────────────────────────────────────
    # Session Summarizer settings
    # ─────────────────────────────────────────────

    # Directory to store session summary JSON files
    SESSION_SUMMARY_DIR: str = os.getenv(
        "SESSION_SUMMARY_DIR",
        os.path.join(os.path.dirname(__file__), "data", "session_summaries")
    )

    # ─────────────────────────────────────────────
    # Student Profile settings
    # ─────────────────────────────────────────────

    # Path to the student profile JSON file
    STUDENT_PROFILE_PATH: str = os.getenv(
        "STUDENT_PROFILE_PATH",
        os.path.join(os.path.dirname(__file__), "data", "student_profile.json")
    )

    # ─────────────────────────────────────────────
    # Logging settings
    # ─────────────────────────────────────────────

    # Path to the agent activity log file
    AGENT_LOG_FILE: str = os.getenv(
        "AGENT_LOG_FILE",
        os.path.join(os.path.dirname(__file__), "logs", "agent.log")
    )

    # Agent log level: DEBUG | INFO | WARNING
    AGENT_LOG_LEVEL: str = os.getenv("AGENT_LOG_LEVEL", "INFO")

    # ─────────────────────────────────────────────
    # PostgreSQL settings
    # ─────────────────────────────────────────────
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "edumentor")
    POSTGRES_POOL_SIZE: int = int(os.getenv("POSTGRES_POOL_SIZE", "15"))
    POSTGRES_ENABLED: bool = os.getenv("POSTGRES_ENABLED", "true").lower() == "true"

