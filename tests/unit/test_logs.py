import io
import json
import logging
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from ragcalibrate.logs import JsonFormatter, query_id, run_id


@pytest.fixture
def emit() -> Iterator[Any]:
    """Return a function that logs one record and gives back the parsed JSON line."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.logs")
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    def _emit(event: str, **extra: Any) -> dict[str, Any]:
        stream.seek(0)
        stream.truncate()
        logger.info(event, extra=extra)
        return json.loads(stream.getvalue())

    yield _emit
    logger.handlers.clear()


def test_line_has_event_level_and_extra_fields(emit: Any) -> None:
    line = emit("retrieve.completed", strategy="s2", latency_ms=12)
    assert line["event"] == "retrieve.completed"
    assert line["level"] == "INFO"
    assert line["logger"] == "test.logs"
    assert line["strategy"] == "s2"
    assert line["latency_ms"] == 12
    assert "ts" in line


def test_run_and_query_ids_come_from_context(emit: Any) -> None:
    run_token = run_id.set("run-1")
    query_token = query_id.set("q-7")
    try:
        line = emit("judge.completed")
    finally:
        run_id.reset(run_token)
        query_id.reset(query_token)
    assert line["run_id"] == "run-1"
    assert line["query_id"] == "q-7"


def test_ids_are_absent_when_not_set(emit: Any) -> None:
    line = emit("service.started")
    assert "run_id" not in line
    assert "query_id" not in line


def test_explicit_extra_wins_over_context(emit: Any) -> None:
    token = query_id.set("from-context")
    try:
        line = emit("retrieve.completed", query_id="from-extra")
    finally:
        query_id.reset(token)
    assert line["query_id"] == "from-extra"


def test_exception_traceback_is_kept() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "x",
            logging.ERROR,
            __file__,
            1,
            "run.failed",
            None,
            exc_info=sys.exc_info(),
        )
    line = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in line["exception"]
