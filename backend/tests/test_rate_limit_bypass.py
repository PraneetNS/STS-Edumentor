"""
Unit tests for the rate-limit bypass token feature.

Tests cover:
- is_bypass_token(): empty config, correct token, wrong token, timing-safe comparison
- check_rate_limit() with bypass: limit is not enforced when token is valid
- check_voice_rate_limit() with bypass: voice limit is not enforced when token is valid
- Bypass is inert when RATE_LIMIT_BYPASS_TOKEN is empty (default)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent.rate_limiter import RateLimiter, is_bypass_token


# ── is_bypass_token() ─────────────────────────────────────────────────────────

class TestIsBypassToken:
    def test_returns_false_when_config_empty(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = ""
            assert is_bypass_token("any-token") is False

    def test_returns_false_when_token_empty(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "secret"
            assert is_bypass_token("") is False

    def test_returns_true_for_exact_match(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "my-secret-dev-token"
            assert is_bypass_token("my-secret-dev-token") is True

    def test_returns_false_for_wrong_token(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "correct-token"
            assert is_bypass_token("wrong-token") is False

    def test_token_comparison_is_case_sensitive(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "Secret"
            assert is_bypass_token("secret") is False
            assert is_bypass_token("SECRET") is False
            assert is_bypass_token("Secret") is True

    def test_strips_whitespace_from_both_sides(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "  token123  "
            assert is_bypass_token("token123") is True

    def test_config_attribute_missing_returns_false(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            del mock_cfg.RATE_LIMIT_BYPASS_TOKEN
            # Should return False, not AttributeError (uses getattr with default)
            assert is_bypass_token("anything") is False


# ── check_rate_limit() with bypass ────────────────────────────────────────────

class TestCheckRateLimitBypass:
    def _make_exhausted_limiter(self, student_id: str = "s1") -> RateLimiter:
        """Return a limiter that has already hit the per-minute cap."""
        rl = RateLimiter()
        # Manually fill window to max
        import time
        now = time.time()
        window_size = 100  # well above any realistic limit
        rl.requests_per_student[student_id] = [now] * window_size
        return rl

    def test_bypass_overrides_exhausted_limit(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "dev-token"
            mock_cfg.RATE_LIMIT_PER_MINUTE = 1
            rl = self._make_exhausted_limiter()
            # Without bypass → should be denied
            result_no_bypass = rl.check_rate_limit("s1", max_per_minute=1)
            assert result_no_bypass is False
            # With valid bypass → should be allowed
            result_bypass = rl.check_rate_limit("s1", max_per_minute=1, bypass_token="dev-token")
            assert result_bypass is True

    def test_bypass_does_not_apply_with_wrong_token(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "correct-token"
            mock_cfg.RATE_LIMIT_PER_MINUTE = 1
            rl = self._make_exhausted_limiter()
            result = rl.check_rate_limit("s1", max_per_minute=1, bypass_token="wrong-token")
            assert result is False

    def test_bypass_does_not_apply_when_config_empty(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = ""
            mock_cfg.RATE_LIMIT_PER_MINUTE = 1
            rl = self._make_exhausted_limiter()
            result = rl.check_rate_limit("s1", max_per_minute=1, bypass_token="any-token")
            assert result is False

    def test_bypass_does_not_increment_window(self):
        """Valid bypass should not add to the rate-limit window."""
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "dev-token"
            rl = RateLimiter()
            rl.check_rate_limit("s1", bypass_token="dev-token")
            # Window should still be empty
            assert len(rl.requests_per_student["s1"]) == 0


# ── check_voice_rate_limit() with bypass ──────────────────────────────────────

class TestCheckVoiceRateLimitBypass:
    def _make_voice_exhausted(self, student_id: str = "s1") -> RateLimiter:
        import time
        rl = RateLimiter()
        now = time.time()
        rl.requests_per_student[student_id] = [now] * 100
        return rl

    def test_bypass_overrides_voice_limit(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "dev-token"
            rl = self._make_voice_exhausted()
            ok, msg = rl.check_voice_rate_limit("s1", bypass_token="dev-token")
            assert ok is True
            assert msg == ""

    def test_voice_bypass_returns_empty_message(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "dev"
            rl = self._make_voice_exhausted()
            ok, msg = rl.check_voice_rate_limit("s1", bypass_token="dev")
            assert msg == ""

    def test_voice_no_bypass_with_wrong_token(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = "correct"
            rl = self._make_voice_exhausted()
            ok, _ = rl.check_voice_rate_limit("s1", bypass_token="wrong")
            assert ok is False

    def test_voice_bypass_inert_when_config_empty(self):
        with patch("agent.rate_limiter.Config") as mock_cfg:
            mock_cfg.RATE_LIMIT_BYPASS_TOKEN = ""
            rl = self._make_voice_exhausted()
            ok, _ = rl.check_voice_rate_limit("s1", bypass_token="any")
            assert ok is False
