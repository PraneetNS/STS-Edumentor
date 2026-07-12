"""
logger.py — Structured application logger for the EduMentor Voice backend.

Wraps Python's standard ``logging`` module with:
  - JSON-formatted output (production)
  - Human-readable coloured output (development / TTY)
  - Automatic inclusion of module name, level, and ISO timestamp
  - Helper ``get_logger(name)`` factory used throughout the backend

Usage::

    from utils.logger import get_logger
    log = get_logger(__name__)

    log.info("Server started", extra={"port": 8765})
    log.warning("Slow LLM response", extra={"latency_ms": 4200})
    log.error("WebSocket error", exc_info=True)
"""

import logging
import os
import sys
import json
import time
from typing import Any


# ---------------------------------------------------------------------------
# Detect environment
# ---------------------------------------------------------------------------

_ENV = os.getenv("APP_ENV", "development").lower()
_LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)
_IS_TTY = sys.stderr.isatty()


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_COLOURS = {
    "DEBUG":    "\033[36m",   # cyan
    "INFO":     "\033[32m",   # green
    "WARNING":  "\033[33m",   # yellow
    "ERROR":    "\033[31m",   # red
    "CRITICAL": "\033[35m",   # magenta
}


class _ColourFormatter(logging.Formatter):
    """Coloured human-readable formatter for TTY / development output."""

    def format(self, record: logging.LogRecord) -> str:
        colour = _COLOURS.get(record.levelname, "")
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        level = f"{colour}{record.levelname:<8}{_RESET}"
        msg = super().format(record)
        return f"{ts} {level} [{record.name}] {record.getMessage()}"


class _JSONFormatter(logging.Formatter):
    """Machine-readable JSON formatter for production / log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Merge any ``extra`` fields the caller passed
        for key, val in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                payload[key] = val
        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Root handler (configured once)
# ---------------------------------------------------------------------------

_handler = logging.StreamHandler(sys.stderr)

if _IS_TTY or _ENV == "development":
    _handler.setFormatter(_ColourFormatter())
else:
    _handler.setFormatter(_JSONFormatter())

_root = logging.getLogger("edumentor")
_root.setLevel(_LOG_LEVEL)
if not _root.handlers:
    _root.addHandler(_handler)
_root.propagate = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """
    Return a child logger under the ``edumentor`` namespace.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A ``logging.Logger`` pre-configured with the application handler.
    """
    # Strip redundant package prefix for brevity
    short = name.replace("edumentor.", "")
    return _root.getChild(short)
