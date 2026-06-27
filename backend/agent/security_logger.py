"""
EduMentor Agent Layer — Security Event Logger

Writes security events to three destinations:
  1. PostgreSQL security_events table (when DB pool is available)
  2. security.log file in the agent log directory
  3. The edumentor.agent.security logger (captured by the rotating file handler)

Event types used by the OWASP gap mitigations:
  session_ownership_violation  — LLM08: mismatched student_id for a session
  system_leak_attempt          — LLM07: model output contained system config
  rag_content_injection_attempt — LLM01: poisoned RAG document detected
  rate_limit_exceeded          — LLM10: student hit per-minute rate limit
  daily_budget_exceeded        — LLM10: student hit daily token budget
  circuit_open                 — LLM10: circuit breaker tripped
"""
import logging
import os
import time
from config import Config

logger = logging.getLogger("edumentor.agent.security")

# Severity mapping for structured log lines
_SEVERITY: dict[str, str] = {
    "session_ownership_violation": "CRITICAL",
    "system_leak_attempt":         "CRITICAL",
    "rag_content_injection_attempt": "HIGH",
    "rate_limit_exceeded":         "MEDIUM",
    "daily_budget_exceeded":       "MEDIUM",
    "circuit_open":                "HIGH",
}


async def log_security_event(
    student_id: str | None,
    ip_address: str,
    event_type: str,
    details: str
):
    """
    Log a security event to the DB, security.log, and the Python logger.

    Non-blocking on DB failure — security events must never crash the request
    pipeline. Both the file and the Python logger provide a fallback if the DB
    write fails.
    """
    severity = _SEVERITY.get(event_type, "INFO")

    # 1. PostgreSQL security_events table
    from agent.database import db_pool
    if db_pool is not None:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO security_events (student_id, ip_address, "
                    "event_type, details) VALUES ($1, $2, $3, $4)",
                    student_id, ip_address, event_type, details
                )
        except Exception as e:
            logger.error("Failed to write to security_events table: %s", e)
    else:
        logger.warning("db_pool is None, skipping write to security_events table.")

    # 2. security.log — structured line for SIEM ingestion
    log_dir = os.path.dirname(Config.AGENT_LOG_FILE)
    sec_log_path = os.path.join(log_dir, "security.log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(sec_log_path, "a", encoding="utf-8") as f:
            f.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')} "
                f"severity={severity} "
                f"event={event_type} "
                f"student={student_id} "
                f"ip={ip_address} "
                f"details={details!r}\n"
            )
    except Exception as e:
        logger.error("Failed to write to security log file: %s", e)

    # 3. Python logger (captured by the rotating file handler on edumentor.agent)
    log_fn = logger.critical if severity == "CRITICAL" else logger.warning
    log_fn(
        "[SECURITY] severity=%s event=%s student=%s ip=%s details=%r",
        severity, event_type, student_id, ip_address, details
    )
