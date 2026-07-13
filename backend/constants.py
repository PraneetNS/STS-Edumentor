"""
EduMentor Voice — Shared Constants

Centralises magic strings, event types, and pipeline state labels that are
used across multiple backend modules. Import from here instead of scattering
raw strings through the codebase.
"""

# ── WebSocket message types sent server → client ───────────────────────────

class WSEvent:
    """Server-to-client WebSocket event type constants."""
    # Voice pipeline state changes
    PIPELINE_STATE    = "pipeline_state"
    # Partial / final STT transcript
    TRANSCRIPT_LIVE   = "transcript_live"
    TRANSCRIPT_FINAL  = "transcript_final"
    # Streaming LLM tokens
    LLM_TOKEN         = "llm_token"
    LLM_DONE          = "llm_done"
    # Structured visual block extracted from LLM output
    SHOW_BLOCK        = "show_block"
    # TTS control
    TTS_START         = "tts_start"
    TTS_CHUNK         = "tts_chunk"
    TTS_DONE          = "tts_done"
    TTS_INTERRUPTED   = "tts_interrupted"
    # Follow-up question
    FOLLOWUP          = "followup"
    # Error conditions
    ERROR             = "error"
    # Non-fatal server warnings (e.g. soft rate-limit, degraded mode)
    WARN              = "warn"
    # Rate-limit reached — client should back off
    RATE_LIMITED      = "rate_limited"
    # Server health / meta
    HEALTH            = "health"
    SESSION_READY     = "session_ready"


# ── WebSocket message types sent client → server ───────────────────────────

class WSCommand:
    """Client-to-server WebSocket command type constants."""
    AUDIO_CHUNK       = "audio_chunk"
    TEXT_QUERY        = "text_query"
    INTERRUPT         = "interrupt"
    PING              = "ping"
    START_RECORDING   = "start_recording"
    STOP_RECORDING    = "stop_recording"
    SETTINGS_UPDATE   = "settings_update"


# ── Pipeline conversation states ───────────────────────────────────────────

class PipelineState:
    """Voice pipeline state machine labels (mirrored on the frontend)."""
    IDLE         = "IDLE"
    LISTENING    = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING     = "THINKING"
    SPEAKING     = "SPEAKING"
    INTERRUPTED  = "INTERRUPTED"
    ERROR        = "ERROR"


# ── LLM response tag names ─────────────────────────────────────────────────

class LLMTag:
    """XML-style tag names used in structured LLM responses."""
    SPEAK    = "speak"
    SHOW     = "show"
    FOLLOWUP = "followup"


# ── Show block visual types ────────────────────────────────────────────────

class ShowType:
    """Allowed values for the `type` attribute of <show> blocks."""
    CODE      = "code"
    TABLE     = "table"
    ROADMAP   = "roadmap"
    WORKFLOW  = "workflow"
    CHECKLIST = "checklist"
    MERMAID   = "mermaid"
    DIAGRAM   = "diagram"  # alias for mermaid-rendered diagrams

    ALL = {CODE, TABLE, ROADMAP, WORKFLOW, CHECKLIST, MERMAID, DIAGRAM}


# ── Reconnect / session limits ─────────────────────────────────────────────

MAX_RECONNECT_ATTEMPTS: int = 5
RECONNECT_BACKOFF_BASE: float = 1.5   # seconds — exponential base
MAX_SESSION_IDLE_SECS: int = 300      # 5 minutes before idle disconnect
