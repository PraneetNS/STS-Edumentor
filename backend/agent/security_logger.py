import logging
import os
import time
from config import Config

logger = logging.getLogger("edumentor.agent.security")

async def log_security_event(
    student_id: str | None,
    ip_address: str,
    event_type: str,
    details: str
):
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

    # Also print to a separate log file, not mixed with normal conversation logs
    log_dir = os.path.dirname(Config.AGENT_LOG_FILE)
    sec_log_path = os.path.join(log_dir, "security.log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(sec_log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | [SECURITY] {event_type} | student={student_id} | ip={ip_address} | {details}\n")
    except Exception as e:
        logger.error("Failed to write to security log file: %s", e)

    print(f"[SECURITY] {event_type} | student={student_id} | {details}")
