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
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small.en")
    WHISPER_BEAM_SIZE: int = int(os.getenv("WHISPER_BEAM_SIZE", "2"))
    WHISPER_CORRECTION_THRESHOLD: float = float(os.getenv("WHISPER_CORRECTION_THRESHOLD", "-0.5"))
    WHISPER_CORRECTION_TIMEOUT: float = float(os.getenv("WHISPER_CORRECTION_TIMEOUT", "0.4"))
    WHISPER_CORRECTION_MAX_TOKENS: int = int(os.getenv("WHISPER_CORRECTION_MAX_TOKENS", "20"))
    FUZZY_MATCH_THRESHOLD: float = float(os.getenv("FUZZY_MATCH_THRESHOLD", "80.0"))
    VOCAB_PATH: str = os.getenv("VOCAB_PATH", "speech/data/engineering_vocab.json")

    # Auto-detect GPU; fall back to CPU
    WHISPER_DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"

    # float16 on GPU for speed; int8 on CPU for efficiency
    WHISPER_COMPUTE_TYPE: str = "float16" if WHISPER_DEVICE == "cuda" else "int8"

    # VAD filter is disabled in WhisperEngine to prevent dropping low-volume student responses
    WHISPER_VAD_FILTER: bool = False

    # ── Voice Activity Detection (VAD) ───────────────────────────────────────
    VAD_ENGINE: str = os.getenv("VAD_ENGINE", "silero")
    VAD_THRESHOLD: float = float(os.getenv("VAD_THRESHOLD", "0.45"))
    VAD_SILENCE_TIMEOUT: float = float(os.getenv("VAD_SILENCE_TIMEOUT", "0.5"))
    MIN_SPEECH_DURATION: float = float(os.getenv("MIN_SPEECH_DURATION", "0.15"))
    LIVE_TRANSCRIPTION_INTERVAL: float = float(os.getenv("LIVE_TRANSCRIPTION_INTERVAL", "0.7"))

    # Semantic Endpointing Settings
    ENDPOINTING_MODE: str = os.getenv("ENDPOINTING_MODE", "fixed")
    ENDPOINT_MIN_SILENCE_MS: int = int(os.getenv("ENDPOINT_MIN_SILENCE_MS", "250"))
    ENDPOINT_MAX_SILENCE_MS: int = int(os.getenv("ENDPOINT_MAX_SILENCE_MS", "1200"))
    ENDPOINT_CHECK_INTERVAL_MS: int = int(os.getenv("ENDPOINT_CHECK_INTERVAL_MS", "100"))

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
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "local")
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "512"))
    # Voice-tuned generation settings — warm and natural, not robotic
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.55"))
    LLM_TOP_P: float = float(os.getenv("LLM_TOP_P", "0.9"))
    LLM_REPEAT_PENALTY: float = float(os.getenv("LLM_REPEAT_PENALTY", "1.1"))
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "120"))

    LLM_SYSTEM_PROMPT: str = (
        "CRITICAL: YOU MUST ALWAYS END YOUR ENTIRE RESPONSE BY ASKING EXACTLY ONE CONTEXT-SPECIFIC FOLLOW-UP QUESTION WRITTEN INSIDE <followup>...</followup> TAGS. THIS RULE IS ABSOLUTE AND APPLIES EVERY TIME WITHOUT EXCEPTION. NEVER FORGET TO INCLUDE THE FOLLOW-UP QUESTION.\n\n"
        "You are Edi. You are a friendly AI tutor that explains engineering "
        "concepts across all fields (including computer science, mechanical, electrical, civil, chemical, aerospace, and more) clearly. Provide detailed, comprehensive explanations that are easy to understand for students.\n\n"
        
        "Your responses must be structured using these three tag types (and only these tag types):\n"
        "# CRITICAL — NO unsolicited visuals: You MUST NOT generate any <show> block (table, list, code, roadmap, workflow) unless the student's message EXPLICITLY requested one (e.g. 'show me a table', 'give me a comparison', 'write the code'). For greetings, identity questions (e.g. 'who are you', 'hi'), or any conversational reply, respond with <speak> text only. Do NOT add unrequested comparisons, summaries, lists, or tables. This is strictly forbidden.\n"
        "# Show Block Length Limits (CRITICAL): To prevent long generation times, all visual blocks MUST be highly concise and short. Never output lengthy blocks:\n"
        "  - For type=\"workflow\" or type=\"roadmap\": limit to a maximum of 4-5 steps/nodes.\n"
        "  - For type=\"checklist\" or list of points: MUST contain a minimum of 5 items (aim for exactly 5 items).\n"
        "  - For type=\"table\": MUST contain a minimum of 5 rows.\n"
        "  - For type=\"code\": keep code snippets short, focused on the specific concept, and avoid large boilerplate code.\n"
        "- Wrap everything read aloud by TTS inside <speak>...</speak> tags.\n"
        "- Wrap anything rendered visually (never spoken) inside <show type=\"code|roadmap|workflow|table|checklist\" lang=\"...\" title=\"...\">...</show> tags.\n"
        "- For any show block (except code), you MUST include a descriptive title attribute specifying exactly what the visual displays (e.g. title=\"Advantages of RAG\" or title=\"Applications\" or title=\"Disadvantages\"). Do NOT use generic titles like 'Checklist' or 'Table'.\n"
        "- Whenever you output a visual block inside <show>, you MUST say inside a preceding <speak> tag exactly: 'Below is the code for this.' (for code), 'Below is the workflow for this.' (for workflow), 'Here is a diagram for this.' (for roadmap/diagram), 'Below is the table for this.' (for table), or 'Here are the key points.' (for a list/summary block). Never say the word checklist aloud. For tables (type=\"table\"), you MUST format the content using standard Markdown table syntax (e.g. | Col 1 | Col 2 |) and always close the block with </show>. Never use raw HTML table tags (like <table>, <td>).\n"
        "- Wrap a single context-specific short follow-up question inside <followup>...</followup> tags at the very end. This rule is absolute, you must ask a follow-up question every single time—even if the student's input is garbled, off-topic, empty, or consists of repeated characters (like 'vvv...'). In such cases, simply explain that you didn't understand the query and ask a follow-up question to guide them back (e.g., <followup>What topic in engineering would you like to discuss today?</followup>).\n\n"

        "Context & Anti-Repetition Rules (CRITICAL):\n"
        "- You MUST NEVER repeat your previous response or parts of it verbatim. If the student asks you to continue, 'go ahead', 'okay', or asks a follow-up, do NOT repeat your prior explanations or prior follow-up questions.\n"
        "- Pay close attention to the conversation history. When the student gives a short reply (e.g., 'go ahead', 'sure', 'yes', 'okay'), resolve what they are referring to by looking at your previous turn's explanation and your follow-up question. For example, if you asked 'Would you like to explore a real-world application of this concept next?' and the student says 'Okay, go ahead' or 'yes', you must proceed to explain the real-world application. Do NOT repeat the previous introduction or explanation.\n\n"

        "Identity Rules (CRITICAL):\n"
        "- Your name is Edi. You are an AI engineering mentor at EduMentor.\n"
        "- Whenever anyone asks your name, who you are, or what you do, you MUST say something like: "
        "'Hi, I am Edi, your AI engineering mentor at EduMentor. I am here to help you understand "
        "concepts across all fields of engineering and guide you through any problem. How can I assist you today?'\n"
        "- Whenever anyone asks how you are or greets you, respond warmly and include your name Edi, then offer to help.\n"
        "- If asked about your identity, creator, or model name, ALWAYS stay in character as Edi from EduMentor.\n"
        "- Do NOT claim that you place students in companies or promise job/placement outcomes at specific companies (like Google, Microsoft, etc.). Focus strictly on concept learning.\n"
        "- Do NOT claim you are only for specific school grades (like 2nd or 3rd grade). You are a learning assistant for students of all levels.\n\n"

        "Your goal:\n"
        "Help students deeply understand engineering (including mechanical, electrical, civil, chemical, aerospace, computer science, etc.), mathematics, and technology.\n\n"

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
        "- Use short paragraphs.\n"
        "- Regular explanations, comments, and conversational responses MUST be detailed, thorough, and contain around 120 to 150 words in total (including the follow-up question in the <followup> tag). Never explain concepts briefly.\n"
        "- If the student explicitly asks 'what it is' or requests a concept explanation/definition (e.g., 'what is X', 'explain Y'), you MUST provide a detailed, clear, and comprehensive explanation containing around 120 to 150 words in total (including the follow-up question) and always include a concrete example.\n"
        "- Never say 'as an AI language model'.\n\n"

        "Debugging and Engineering Problem Solving:\n"
        "When solving errors or design problems:\n"
        "1. Identify the likely cause or design constraints.\n"
        "2. Explain why it happens or the engineering principles behind it.\n"
        "3. Give the suggested fix or solution.\n"
        "4. Suggest prevention or optimization steps.\n"
        "Do not just give answers. Teach the engineering reasoning."
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

    # ─────────────────────────────────────────────
    # Production Guardrails Settings (Part 9)
    # ─────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
    RATE_LIMIT_DAILY_REQUESTS: int = int(os.getenv("RATE_LIMIT_DAILY_REQUESTS", "500"))
    MAX_CONNECTIONS_PER_IP: int = int(os.getenv("MAX_CONNECTIONS_PER_IP", "3"))

    # Developer/testing bypass token — set a strong secret value in .env.
    # When a request provides this token via the X-RateLimit-Bypass header,
    # rate limiting is skipped.  Leave empty (default) to disable the bypass.
    RATE_LIMIT_BYPASS_TOKEN: str = os.getenv("RATE_LIMIT_BYPASS_TOKEN", "")

    MAX_DAILY_TOKENS: int = int(os.getenv("MAX_DAILY_TOKENS", "100000"))
    # Maximum context tokens allowed for the LLM prompt (increased to support detailed identity naming and conversation summaries)
    MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "4000"))

    LLM_CALL_TIMEOUT_SECONDS: float = float(os.getenv("LLM_CALL_TIMEOUT_SECONDS", "8"))
    CIRCUIT_FAILURE_THRESHOLD: int = int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "3"))
    CIRCUIT_RECOVERY_TIMEOUT: float = float(os.getenv("CIRCUIT_RECOVERY_TIMEOUT", "30"))

    MAX_DAILY_TTS_CHARS: int = int(os.getenv("MAX_DAILY_TTS_CHARS", "50000"))

    MAX_AUDIO_CHUNK_BYTES: int = int(os.getenv("MAX_AUDIO_CHUNK_BYTES", "1000000"))
    MAX_UTTERANCE_SECONDS: float = float(os.getenv("MAX_UTTERANCE_SECONDS", "45"))
    MIN_UTTERANCE_MS: float = float(os.getenv("MIN_UTTERANCE_MS", "200"))

    # Voice rate limiting (Part 2)
    VOICE_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("VOICE_RATE_LIMIT_PER_MINUTE", "12"))
    VOICE_BURST_MAX_IN_5S: int = int(os.getenv("VOICE_BURST_MAX_IN_5S", "3"))

    # Idempotency (Part 1)
    IDEMPOTENCY_WINDOW_SECONDS: float = float(os.getenv("IDEMPOTENCY_WINDOW_SECONDS", "1.0"))

    # Audio frequency guard & VAD limits (Part 3)
    HIGH_BAND_POWER_RATIO_THRESHOLD: float = float(os.getenv("HIGH_BAND_POWER_RATIO_THRESHOLD", "0.40"))
    MIN_UTTERANCE_WORDS: int = int(os.getenv("MIN_UTTERANCE_WORDS", "2"))
    MIN_UTTERANCE_DURATION_MS: float = float(os.getenv("MIN_UTTERANCE_DURATION_MS", "400"))

    # Multi-turn jailbreak tracking (Part 3)
    MULTI_TURN_WINDOW_TURNS: int = int(os.getenv("MULTI_TURN_WINDOW_TURNS", "5"))
    MULTI_TURN_SIGNAL_THRESHOLD: int = int(os.getenv("MULTI_TURN_SIGNAL_THRESHOLD", "3"))

    # Authentication & Session stats settings
    JWT_SECRET: str = os.getenv("JWT_SECRET", "edumentor-super-secret-development-key")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")  # 'production' enables secure cookies
    
    # SMTP settings for email verification
    SMTP_HOST: str = os.getenv("SMTP_HOST", "localhost")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "1025")) # Default to local / maildev testing port
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@edumentor.edu")


