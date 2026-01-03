"""Centralized logging configuration for email_assistant_mcp."""

import contextvars
import json
import logging
import logging.handlers
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path


# Correlation ID context variable (thread-safe and async-safe)
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="no_context")


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return f"req_{uuid.uuid4().hex[:12]}"


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current context."""
    _correlation_id.set(correlation_id)


def get_correlation_id() -> str:
    """Get the correlation ID for the current context."""
    return _correlation_id.get()


def clear_correlation_id() -> None:
    """Clear the correlation ID for the current context."""
    _correlation_id.set("no_context")


class ContextFilter(logging.Filter):
    """Add correlation ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "correlation_id") and record.correlation_id != "no_context":
            log_data["correlation_id"] = record.correlation_id
        if record.exc_info:
            log_data["exception"] = traceback.format_exception(*record.exc_info)
        return json.dumps(log_data)


def configure_logging(
    level: str | None = None,
    format_type: str | None = None,
    log_file: str | None = None,
    console_enabled: bool = True,
) -> None:
    """Configure logging for the entire application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Output format ("text" or "json")
        log_file: Path to log file (enables file logging)
        console_enabled: Whether to log to console
    """
    log_level = (level or os.getenv("EMAIL_ASSISTANT_LOG_LEVEL", "INFO")).upper()
    format_type = (format_type or os.getenv("EMAIL_ASSISTANT_LOG_FORMAT", "text")).lower()
    log_file_path = log_file or os.getenv("EMAIL_ASSISTANT_LOG_FILE")

    root_logger = logging.getLogger("email_assistant_mcp")
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    formatter = (
        JSONFormatter() if format_type == "json"
        else logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | [%(correlation_id)s] | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    context_filter = ContextFilter()

    if console_enabled:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        handler.addFilter(context_filter)
        root_logger.addHandler(handler)

    if log_file_path:
        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_file_path, maxBytes=10485760, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        handler.addFilter(context_filter)
        root_logger.addHandler(handler)

    root_logger.info(
        "Logging configured | level=%s format=%s console=%s file=%s",
        log_level, format_type, console_enabled, log_file_path or "disabled"
    )
