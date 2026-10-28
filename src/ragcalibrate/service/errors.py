"""Errors the service raises on purpose, and the one place every error becomes a response.

Routes raise a `RagError` subclass and never build error responses. `register` sends that,
a request that fails validation, an unknown route and any unexpected exception through one
handler, which answers with RFC 9457 problem details (`contract.Problem`). The `code` is the
contract the harness branches on; the detail is for people. Tracebacks go to the log only.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from ragcalibrate.contract import Problem

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


class RagError(Exception):
    status = 500
    code = "internal"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class DocumentNotFound(RagError):
    status, code = 404, "document_not_found"


class NotIndexed(RagError):
    """The document exists, but has no chunks for that chunker or no vectors for that model."""

    status, code = 404, "not_indexed"


class UnknownEmbedder(RagError):
    status, code = 422, "unknown_embedder"


class NotReady(RagError):
    status, code = 503, "not_ready"


def problem(status: int, code: str, detail: str) -> JSONResponse:
    body = Problem(title=HTTPStatus(status).phrase, status=status, detail=detail, code=code)
    return JSONResponse(body.model_dump(), status_code=status, media_type=PROBLEM_JSON)


async def _handle(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, RagError):
        return problem(exc.status, exc.code, exc.detail)
    if isinstance(exc, RequestValidationError):
        # Field locations and messages only; the rejected input is not echoed back.
        errors = "; ".join(
            f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return problem(422, "invalid_request", errors)
    if isinstance(exc, HTTPException):
        return problem(exc.status_code, "http_error", str(exc.detail))
    logger.error("request.failed", exc_info=exc, extra={"path": request.url.path})
    return problem(500, "internal", "Unexpected error; the service log has the details.")


def register(app: FastAPI) -> None:
    for exc_type in (RagError, RequestValidationError, HTTPException, Exception):
        app.add_exception_handler(exc_type, _handle)
