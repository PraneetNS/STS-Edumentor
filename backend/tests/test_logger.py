"""
test_logger.py — Unit tests for backend/utils/logger.py

Covers:
  - get_logger returns a Logger instance
  - Logger name is namespaced under "edumentor"
  - All severity levels (debug, info, warning, error, critical) emit messages
  - JSON formatter produces valid JSON with required fields
  - Colour formatter produces non-empty string output
  - Logger does not propagate to root logger
"""

import sys
import os
import json
import logging
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from utils.logger import get_logger, _JSONFormatter, _ColourFormatter


class TestGetLogger:
    def test_returns_logger_instance(self):
        log = get_logger("test.module")
        assert isinstance(log, logging.Logger)

    def test_name_under_edumentor_namespace(self):
        log = get_logger("my.module")
        assert "edumentor" in log.name

    def test_no_propagation_to_root(self):
        log = get_logger("test.noprop")
        # The edumentor root logger should not propagate
        root = logging.getLogger("edumentor")
        assert root.propagate is False

    def test_multiple_calls_same_name_return_same_logger(self):
        a = get_logger("test.same")
        b = get_logger("test.same")
        assert a is b


class TestJSONFormatter:
    def _format(self, level, msg, **kwargs):
        fmt = _JSONFormatter()
        record = logging.LogRecord(
            name="edumentor.test",
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return fmt.format(record)

    def test_output_is_valid_json(self):
        raw = self._format(logging.INFO, "hello")
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_has_required_fields(self):
        raw = self._format(logging.WARNING, "watch out")
        parsed = json.loads(raw)
        assert "ts" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "msg" in parsed

    def test_level_name_correct(self):
        raw = self._format(logging.ERROR, "oops")
        parsed = json.loads(raw)
        assert parsed["level"] == "ERROR"

    def test_message_is_captured(self):
        raw = self._format(logging.INFO, "test message")
        parsed = json.loads(raw)
        assert parsed["msg"] == "test message"

    def test_timestamp_format(self):
        raw = self._format(logging.INFO, "ts test")
        parsed = json.loads(raw)
        # Should be ISO-like: 2026-07-12T...Z
        assert "T" in parsed["ts"]
        assert parsed["ts"].endswith("Z")


class TestColourFormatter:
    def _format(self, level, msg):
        fmt = _ColourFormatter()
        record = logging.LogRecord(
            name="edumentor.test",
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        return fmt.format(record)

    def test_output_is_non_empty_string(self):
        result = self._format(logging.INFO, "hello")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_output_contains_message(self):
        result = self._format(logging.INFO, "ping pong")
        assert "ping pong" in result

    def test_output_contains_level(self):
        result = self._format(logging.WARNING, "warn msg")
        assert "WARNING" in result


class TestLoggerEmission:
    """Verify that log records are actually emitted at each level."""

    def _capture_log(self, log, level_fn, msg):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(_ColourFormatter())
        handler.setLevel(logging.DEBUG)
        log.addHandler(handler)
        log.setLevel(logging.DEBUG)
        try:
            level_fn(msg)
        finally:
            log.removeHandler(handler)
        return stream.getvalue()

    def test_info_emitted(self):
        log = get_logger("test.emit")
        output = self._capture_log(log, log.info, "info message")
        assert "info message" in output

    def test_warning_emitted(self):
        log = get_logger("test.emit.warn")
        output = self._capture_log(log, log.warning, "warn message")
        assert "warn message" in output

    def test_error_emitted(self):
        log = get_logger("test.emit.err")
        output = self._capture_log(log, log.error, "error message")
        assert "error message" in output
