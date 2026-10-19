"""Structured JSON logging: one object per line, with run and query IDs from context.

Library modules only call logging.getLogger(__name__); the entrypoint (CLI or app factory)
calls configure_logging() once. The message is a stable event name such as
"retrieve.completed" and the data goes in `extra`. Never log document text or secrets.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Set by the runner/service around the work; asyncio tasks copy the context when created.
run_id: ContextVar[str | None] = ContextVar("run_id", default=None)
query_id: ContextVar[str | None] = ContextVar("query_id", default=None)

# Attributes every LogRecord has; anything else on a record came from `extra`.
_RECORD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RECORD_ATTRIBUTES:
                payload[key] = value
        # Explicit extra wins; context fills in only what the call site did not say.
        for key, var in (("run_id", run_id), ("query_id", query_id)):
            if key not in payload and (value := var.get()) is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Send JSON logs to stderr (stdout is for CLI output). Call once, from the entrypoint."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
