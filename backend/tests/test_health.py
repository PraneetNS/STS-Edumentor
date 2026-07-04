"""
Tests — Health Utility
"""

import sys
import os
import pytest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.health import check_llm_reachable, check_gpu_memory, get_health_report


@pytest.mark.asyncio
async def test_check_llm_reachable_success():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    
    with mock.patch("httpx.AsyncClient.get", new_callable=mock.AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await check_llm_reachable("http://dummy-url")
        assert res["ok"] is True
        assert "dummy-url" in res["url"]


@pytest.mark.asyncio
async def test_check_llm_reachable_failure():
    with mock.patch("httpx.AsyncClient.get", new_callable=mock.AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        res = await check_llm_reachable("http://dummy-url")
        assert res["ok"] is False
        assert res["error"] == "LLM server unreachable"


def test_check_gpu_memory_unavailable():
    with mock.patch("utils.health._TORCH_AVAILABLE", False):
        res = check_gpu_memory()
        assert res["available"] is False

    with mock.patch("torch.cuda.is_available", return_value=False):
        res = check_gpu_memory()
        assert res["available"] is False


def test_check_gpu_memory_available():
    mock_properties = mock.Mock()
    mock_properties.total_memory = 8 * 1024 * 1024 * 1024  # 8 GB
    
    with mock.patch("utils.health._TORCH_AVAILABLE", True), \
         mock.patch("torch.cuda.is_available", return_value=True), \
         mock.patch("torch.cuda.current_device", return_value=0), \
         mock.patch("torch.cuda.get_device_properties", return_value=mock_properties), \
         mock.patch("torch.cuda.get_device_name", return_value="RTX 4090"), \
         mock.patch("torch.cuda.memory_reserved", return_value=2 * 1024 * 1024 * 1024), \
         mock.patch("torch.cuda.memory_allocated", return_value=1 * 1024 * 1024 * 1024):
         
        res = check_gpu_memory()
        assert res["available"] is True
        assert res["device"] == "RTX 4090"
        assert res["total_mb"] == 8192
        assert res["allocated_mb"] == 1024
        assert res["reserved_mb"] == 2048
        assert res["free_mb"] == 6144  # 8GB total - 2GB reserved


@pytest.mark.asyncio
async def test_get_health_report():
    mock_llm = {"ok": True, "latency_ms": 12.5, "url": "http://dummy/health"}
    mock_gpu = {"available": False}
    
    with mock.patch("utils.health.check_llm_reachable", new_callable=mock.AsyncMock) as mock_llm_reach, \
         mock.patch("utils.health.check_gpu_memory", return_value=mock_gpu):
         
        mock_llm_reach.return_value = mock_llm
        res = await get_health_report("http://dummy")
        assert res["status"] == "healthy"
        assert res["llm"] == mock_llm
        assert res["gpu"] == mock_gpu
