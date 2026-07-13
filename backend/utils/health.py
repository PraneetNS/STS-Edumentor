"""
Backend health-check utility.

Provides a /health endpoint and internal liveness probes used by
the process manager (systemd, Docker HEALTHCHECK, etc.) to determine
whether the EduMentor Voice server is fully operational.

Checks:
  1. WebSocket server reachability (port binding confirmed)
  2. LLM server HTTP reachability (GET /health or /v1/models)
  3. Optional: GPU memory availability via torch

Returns structured JSON so monitoring dashboards can parse it directly.
"""

import os
import socket
import time
import asyncio
from typing import Any

_VERSION = os.getenv("APP_VERSION", "dev")

try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


async def check_llm_reachable(base_url: str, timeout: float = 3.0) -> dict[str, Any]:
    """Probe the LLM server HTTP endpoint."""
    if not _HTTPX_AVAILABLE:
        return {"ok": False, "error": "httpx not installed"}

    probe_urls = [
        f"{base_url.rstrip('/')}/health",
        f"{base_url.rstrip('/')}/v1/models",
    ]

    start = time.monotonic()
    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in probe_urls:
            try:
                resp = await client.get(url)
                if resp.status_code < 500:
                    elapsed = round((time.monotonic() - start) * 1000, 1)
                    return {"ok": True, "latency_ms": elapsed, "url": url}
            except Exception:
                continue

    return {"ok": False, "error": "LLM server unreachable", "tried": probe_urls}


def check_ws_port(host: str = "127.0.0.1", port: int = 8765, timeout: float = 1.0) -> dict[str, Any]:
    """Verify the WebSocket server is accepting TCP connections."""
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = round((time.monotonic() - start) * 1000, 1)
            return {"ok": True, "latency_ms": elapsed, "host": host, "port": port}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "host": host, "port": port}


def check_gpu_memory() -> dict[str, Any]:
    """Return GPU memory stats if CUDA is available."""
    if not _TORCH_AVAILABLE or not torch.cuda.is_available():
        return {"available": False}

    device = torch.cuda.current_device()
    total = torch.cuda.get_device_properties(device).total_memory
    reserved = torch.cuda.memory_reserved(device)
    allocated = torch.cuda.memory_allocated(device)
    free = total - reserved

    return {
        "available": True,
        "device": torch.cuda.get_device_name(device),
        "total_mb": round(total / 1024 ** 2),
        "allocated_mb": round(allocated / 1024 ** 2),
        "reserved_mb": round(reserved / 1024 ** 2),
        "free_mb": round(free / 1024 ** 2),
    }


async def get_health_report(llm_base_url: str) -> dict[str, Any]:
    """
    Aggregate all health sub-checks into a single report dict.

    Returns:
        {
            "status": "healthy" | "degraded" | "unhealthy",
            "timestamp": <iso>,
            "llm": {...},
            "gpu": {...},
            "uptime_s": <float>
        }
    """
    llm_status = await check_llm_reachable(llm_base_url)
    gpu_status = check_gpu_memory()
    ws_host, _, ws_port_str = llm_base_url.replace("http://", "").partition(":")
    ws_status = check_ws_port(port=8765)

    overall = "healthy" if llm_status["ok"] else "degraded"

    return {
        "status": overall,
        "version": _VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "llm": llm_status,
        "websocket": ws_status,
        "gpu": gpu_status,
        "uptime_s": round(time.monotonic(), 1),
    }
