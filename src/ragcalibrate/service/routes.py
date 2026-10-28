"""HTTP routes: validate the request (the contract models), call one function, shape the reply."""

import asyncio
import logging
import time
from http import HTTPStatus
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends
from psycopg_pool import PoolTimeout

from ragcalibrate.contract import Problem, RetrievedChunk, RetrieveRequest, RetrieveResponse
from ragcalibrate.service import retrieval
from ragcalibrate.service.deps import Resources, get_resources
from ragcalibrate.service.errors import PROBLEM_JSON, NotReady, UnknownEmbedder

logger = logging.getLogger(__name__)

# The migration the code expects; /readyz fails until the database is at it. A test checks that
# this equals Alembic's head, so a new migration cannot be forgotten here.
SCHEMA_REVISION = "0003"

router = APIRouter()


def _problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """Document error responses as problem+json, as the handler in errors.py sends them.

    The schema is inlined: FastAPI's `model=` would file it under application/json instead.
    Listing 422 also replaces FastAPI's default validation-error schema, which is never sent.
    """
    schema = Problem.model_json_schema(mode="serialization")
    return {
        status: {
            "description": HTTPStatus(status).phrase,
            "content": {PROBLEM_JSON: {"schema": schema}},
        }
        for status in statuses
    }


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up. Touches nothing else."""
    return {"status": "ok"}


@router.get("/readyz", responses=_problems(503))
async def readyz(resources: Annotated[Resources, Depends(get_resources)]) -> dict[str, str]:
    """Readiness: the database answers and its schema is at the revision this code expects."""
    try:
        async with resources.pool.connection(timeout=2) as conn:
            cursor = await conn.execute("SELECT version_num FROM alembic_version")
            row = await cursor.fetchone()
    except (PoolTimeout, psycopg.Error) as exc:
        raise NotReady(f"database unavailable: {type(exc).__name__}") from exc
    revision = row[0] if row else None
    if revision != SCHEMA_REVISION:
        raise NotReady(f"database schema is at {revision!r}, expected {SCHEMA_REVISION!r}")
    return {"status": "ready"}


@router.post("/retrieve", responses=_problems(404, 422, 500))
async def retrieve(
    body: RetrieveRequest, resources: Annotated[Resources, Depends(get_resources)]
) -> RetrieveResponse:
    """The k best chunks of one document for a query, with offsets into the raw text."""
    started = time.perf_counter()
    match body.strategy:
        case "fts":
            embedder_id = None
            async with resources.pool.connection() as conn:
                chunks = await retrieval.fts(
                    conn,
                    corpus=body.corpus,
                    doc_id=body.doc_id,
                    chunker_id=body.chunker_id,
                    query=body.query,
                    k=body.k,
                )
        case "dense":
            embedder_id, chunks = await _dense(body, resources)
    logger.info(
        "retrieve.completed",
        extra={
            "doc_id": body.doc_id,
            "strategy": body.strategy,
            "k": body.k,
            "returned": len(chunks),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    return RetrieveResponse(
        strategy=body.strategy, chunker_id=body.chunker_id, embedder_id=embedder_id, chunks=chunks
    )


async def _dense(body: RetrieveRequest, resources: Resources) -> tuple[str, list[RetrievedChunk]]:
    embedder_id = body.embedder_id or resources.default_embedder_id
    embed = resources.embedders.get(embedder_id)
    if embed is None:
        loaded = sorted(resources.embedders)
        raise UnknownEmbedder(f"{embedder_id!r} is not loaded; loaded: {loaded}")
    [query_vector] = await asyncio.to_thread(embed, [body.query])
    async with resources.pool.connection() as conn:
        chunks = await retrieval.dense(
            conn,
            corpus=body.corpus,
            doc_id=body.doc_id,
            chunker_id=body.chunker_id,
            embedder_id=embedder_id,
            query_vector=query_vector,
            k=body.k,
        )
    return embedder_id, chunks
