"""Tests for infrastructure.logsys — StructuredLogger."""

from __future__ import annotations
import json
import logging
from contextlib import contextmanager
import pytest
from infrastructure.logsys.structured import StructuredFormatter


class TestStructuredLogger:
    def test_creates_logger_with_name(self, structured_logger):
        assert structured_logger.name == "test-logger"

    def test_info_emits_structured_json(self, structured_logger):
        with _capture_logs(structured_logger) as records:
            structured_logger.info("Hello world", context={"user": "test"})
            assert len(records) == 1
            data = json.loads(records[0])
            assert data["message"] == "Hello world"
            assert data["level"] == "INFO"
            assert data["context"]["user"] == "test"
            assert "timestamp" in data

    def test_error_with_exception(self, structured_logger):
        with _capture_logs(structured_logger) as records:
            try:
                raise ValueError("test error")
            except ValueError as e:
                structured_logger.error("Something failed", exception=e)
            assert len(records) == 1
            data = json.loads(records[0])
            assert data["level"] == "ERROR"
            assert "exception" in data

    def test_warning(self, structured_logger):
        with _capture_logs(structured_logger) as records:
            structured_logger.warning("Warning message", context={"code": 42})
            assert len(records) == 1
            data = json.loads(records[0])
            assert data["level"] == "WARNING"
            assert data["context"]["code"] == 42

    def test_debug_not_emitted_by_default(self):
        from infrastructure.logsys import StructuredLogger
        logger = StructuredLogger("debug-test", level="INFO")
        with _capture_logs(logger) as records:
            logger.debug("Debug message")
            assert len(records) == 0

    def test_debug_when_level_set(self):
        from infrastructure.logsys import StructuredLogger
        logger = StructuredLogger("debug-test-2", level="DEBUG")
        with _capture_logs(logger) as records:
            logger.debug("Debug message")
            assert len(records) == 1

    def test_critical(self, structured_logger):
        with _capture_logs(structured_logger) as records:
            structured_logger.critical("System down")
            assert len(records) == 1
            data = json.loads(records[0])
            assert data["level"] == "CRITICAL"

    def test_audit_log(self, structured_logger):
        with _capture_logs(structured_logger) as records:
            structured_logger.audit("create", "knowledge.document", user_id="admin", details={"doc_id": "d1"})
            assert len(records) == 1
            data = json.loads(records[0])
            assert "Audit: create on knowledge.document" in data["message"]
            assert data["context"]["audit"] is True
            assert data["context"]["action"] == "create"

    def test_console_output_disabled(self):
        from infrastructure.logsys import StructuredLogger
        logger = StructuredLogger("no-console", enable_console=False)
        assert len(logger.logger.handlers) == 0

    def test_context_is_passed_through(self, structured_logger):
        with _capture_logs(structured_logger) as records:
            structured_logger.info("With context", context={"request_id": "req-1"})
            data = json.loads(records[0])
            assert data["context"]["request_id"] == "req-1"

    def test_bind_creates_child(self, structured_logger):
        child = structured_logger.bind(component="api")
        assert child.name == structured_logger.name
        assert child.logger is structured_logger.logger

    def test_service_name_in_output(self):
        from infrastructure.logsys import StructuredLogger
        logger = StructuredLogger("svc-test", service_name="my-service")
        with _capture_logs(logger) as records:
            logger.info("Service check")
            data = json.loads(records[0])
            assert data["service"] == "my-service"


@contextmanager
def _capture_logs(logger):
    """Capture log output from a StructuredLogger into a list of strings."""
    records = []

    class CaptureHandler(logging.Handler):
        def emit(self, record):
            json_str = self.format(record)
            records.append(json_str)

    handler = CaptureHandler()
    formatter = StructuredFormatter(service_name=getattr(logger, 'service_name', 'jarvis'))
    handler.setFormatter(formatter)
    logger.logger.addHandler(handler)

    yield records

    logger.logger.removeHandler(handler)
