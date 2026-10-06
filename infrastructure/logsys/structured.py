"""
Centralized structured logging system.

Features:
  - Structured JSON logging for production
  - Human-readable text logging for development
  - Log levels with granular filtering
  - Automatic request ID tracking via context vars
  - Log rotation
  - Audit trail support
  - Structured metadata in every log entry
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from contextvars import ContextVar
from enum import Enum

# Import stdlib logging BEFORE our package to avoid namespace shadowing
import logging as _logging
from logging.handlers import RotatingFileHandler as _RotatingFileHandler


request_id_var: ContextVar[str] = ContextVar("request_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def to_int(self) -> int:
        return {
            "DEBUG": _logging.DEBUG,
            "INFO": _logging.INFO,
            "WARNING": _logging.WARNING,
            "ERROR": _logging.ERROR,
            "CRITICAL": _logging.CRITICAL,
        }[self.value]


class StructuredFormatter(_logging.Formatter):
    """JSON formatter for structured logging."""

    def __init__(self, fmt: str = "json", service_name: str = "jarvis"):
        super().__init__()
        self.format_type = fmt
        self.service_name = service_name

    def format(self, record: _logging.LogRecord) -> str:
        if self.format_type == "json":
            return self._format_json(record)
        return self._format_text(record)

    def _format_json(self, record: _logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        req_id = request_id_var.get()
        if req_id:
            log_entry["request_id"] = req_id
        sess_id = session_id_var.get()
        if sess_id:
            log_entry["session_id"] = sess_id
        uid = user_id_var.get()
        if uid:
            log_entry["user_id"] = uid
        if hasattr(record, "context") and record.context:
            log_entry["context"] = record.context
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)

    def _format_text(self, record: _logging.LogRecord) -> str:
        req_id = request_id_var.get()
        prefix = f"[{req_id}] " if req_id else ""
        return f"{self.formatTime(record)} | {record.levelname:8s} | {record.name:20s} | {prefix}{record.getMessage()}"


class StructuredLogger:
    """
    Structured logger with context propagation.

    Usage:
        logger = StructuredLogger("jarvis.api")
        logger.info("Server started", context={"port": 8000})
        logger.error("Connection failed", exception=e)
    """

    def __init__(
        self,
        name: str,
        level: str = "INFO",
        format_type: str = "json",
        log_dir: Optional[Path] = None,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 10,
        enable_console: bool = True,
        enable_file: bool = True,
        service_name: str = "jarvis",
    ):
        self.name = name
        self.logger = _logging.getLogger(name)
        self.logger.setLevel(getattr(_logging, level.upper(), _logging.INFO))
        self.logger.handlers.clear()
        self.service_name = service_name

        formatter = StructuredFormatter(fmt=format_type, service_name=service_name)

        if enable_console:
            console = _logging.StreamHandler(sys.stdout)
            console.setFormatter(formatter)
            console.setLevel(getattr(_logging, level.upper(), _logging.INFO))
            self.logger.addHandler(console)

        if enable_file and log_dir:
            log_dir = Path(log_dir)
            log_path = log_dir / f"{name.replace('.', '/')}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = _RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(_logging.DEBUG)
            self.logger.addHandler(file_handler)

    def _log(
        self,
        level: LogLevel,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        exception: Optional[BaseException] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        extra_record = {"context": context or {}}
        if extra:
            extra_record.update(extra)
        if exception:
            self.logger.log(level.to_int(), message, exc_info=exception, extra=extra_record)
        else:
            self.logger.log(level.to_int(), message, extra=extra_record)

    def debug(self, message: str, **kwargs):
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log(LogLevel.CRITICAL, message, **kwargs)

    def audit(self, action: str, resource: str, user_id: str, details: Optional[Dict[str, Any]] = None):
        self.info(
            f"Audit: {action} on {resource}",
            context={
                "audit": True,
                "action": action,
                "resource": resource,
                "user_id": user_id,
                "details": details or {},
            },
        )

    def bind(self, **kwargs):
        child = StructuredLogger(
            name=self.name,
            log_dir=None,
            enable_console=False,
            enable_file=False,
            service_name=self.service_name,
        )
        child.logger = self.logger
        return child


_loggers: Dict[str, StructuredLogger] = {}
_default_config = {
    "level": os.getenv("JARVIS_LOG_LEVEL", "INFO"),
    "format_type": os.getenv("JARVIS_LOG_FORMAT", "json"),
    "log_dir": Path(os.getenv("JARVIS_LOG_DIR", "logs")),
}


def get_logger(name: str = "jarvis") -> StructuredLogger:
    if name not in _loggers:
        try:
            _loggers[name] = StructuredLogger(
                name=name,
                level=_default_config["level"],
                format_type=_default_config["format_type"],
                log_dir=_default_config["log_dir"],
            )
        except Exception:
            _loggers[name] = StructuredLogger(
                name=name,
                level=_default_config["level"],
                format_type=_default_config["format_type"],
                log_dir=None,
            )
    return _loggers[name]


def get_audit_logger() -> StructuredLogger:
    return get_logger("jarvis.audit")


def set_request_context(request_id: str = "", session_id: str = "", user_id: str = ""):
    if request_id:
        request_id_var.set(request_id)
    if session_id:
        session_id_var.set(session_id)
    if user_id:
        user_id_var.set(user_id)


def clear_request_context():
    request_id_var.set("")
    session_id_var.set("")
    user_id_var.set("")
