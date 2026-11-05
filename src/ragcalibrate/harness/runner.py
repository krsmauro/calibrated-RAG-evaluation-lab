"""The full retrieval runner (plan step 3.7): an experiment's queries, scored and stored one by one.

Resumable: each query is stored in one transaction as soon as it is scored, and a resumed run
skips the queries its run already has, so a run stopped at any point (a crash, Ctrl-C, a kill)
ends, once resumed, with the same rows as a run that was never stopped.

One retry layer, here and nowhere else (the adapter does not retry), with exponential backoff
and full jitter, for errors that can pass: no connection, a timeout, 429 or 5xx. Any other error
is a bug in the request or the service and stops the run at once, as does a query still failing
after its last attempt. What was stored stays; a resume continues from it.

Every response must name the strategy, chunker and models of the config, or the run stops: one
run never mixes models, even if the service was restarted with another one before a resume.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

import httpx
from pydantic import ValidationError

from ragcalibrate.contract import RetrieveRequest, RetrieveResponse
from ragcalibrate.corpora.schema import Gold, Query
from ragcalibrate.harness.adapter import SutError
from ragcalibrate.harness.manifest import RunConfig
from ragcalibrate.harness.run import score
from ragcalibrate.harness.store import RunStore

log = logging.getLogger(__name__)

ATTEMPTS = 4  # the first try and three retries
BASE_DELAY = 0.5  # seconds: retry n waits a random time up to BASE_DELAY * 2**(n-1)
PROGRESS_EVERY = 500  # queries between progress log lines

Sleep = Callable[[float], Awaitable[None]]


class Retriever(Protocol):
    """What the runner needs from the system under test; `HttpSut` is the real one."""

    async def retrieve(self, request: RetrieveRequest) -> RetrieveResponse: ...


class RunFailed(Exception):
    """The run stopped: a query failed for good, or a response did not match the config. The
    queries stored before it stay, and the run can be resumed."""


def _retryable(exc: SutError | httpx.TransportError) -> bool:
    if isinstance(exc, SutError):
        return exc.status == 429 or exc.status >= 500
    return True  # no connection, or a timeout: the service may be restarting


async def retrieve_with_retries(
    sut: Retriever, request: RetrieveRequest, *, sleep: Sleep = asyncio.sleep
) -> RetrieveResponse:
    attempt = 1
    while True:
        try:
            return await sut.retrieve(request)
        except (SutError, httpx.TransportError) as exc:
            if attempt == ATTEMPTS or not _retryable(exc):
                raise
            log.warning("retrieve.retry", extra={"attempt": attempt, "error": repr(exc)})
        # Full jitter: a random wait up to the bound, so retries from many queries spread out.
        await sleep(random.uniform(0, BASE_DELAY * 2 ** (attempt - 1)))  # noqa: S311 (not security)
        attempt += 1


def check_response(config: RunConfig, response: RetrieveResponse) -> None:
    expected = (config.strategy, config.chunker_id, config.embedder_id, config.reranker_id)
    got = (response.strategy, response.chunker_id, response.embedder_id, response.reranker_id)
    if got != expected:
        raise RunFailed(
            f"the service answered with strategy, chunker, embedder and reranker {got};"
            f" the config names {expected}"
        )


async def execute(
    sut: Retriever,
    store: RunStore,
    run_id: str,
    config: RunConfig,
    queries: Sequence[Query],
    gold_of: Mapping[str, Gold],
    *,
    concurrency: int,
    sleep: Sleep = asyncio.sleep,
) -> int:
    """Retrieve, score and store each query the run has not stored yet; return how many."""
    loop = asyncio.get_running_loop()
    # One thread does every store call, so they never overlap, even when a task is cancelled
    # while its write is running; the writes stay off the event loop (skill DB-HIGH-4). Leaving
    # the block waits for a write still running (milliseconds), so no caller closes the store
    # under it.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="run-store") as writer:
        stored = await loop.run_in_executor(writer, store.query_ids, run_id)
        todo = [q for q in queries if q.id not in stored]
        # Built before any is sent, so a bad parameter fails once, here.
        requests = [config.request(q.text, q.document_id) for q in todo]
        limit = asyncio.Semaphore(concurrency)
        done = 0

        async def one(query: Query, request: RetrieveRequest) -> None:
            nonlocal done
            async with limit:
                response = await retrieve_with_retries(sut, request, sleep=sleep)
            check_response(config, response)
            result = score(response, gold_of[query.id])
            # Shielded: when the run stops (an error, Ctrl-C), cancelling this task must not
            # cancel a write still queued behind a slow one, or answers already scored are
            # dropped (CI lost all of them on a slow runner). Leaving the `with` block below
            # waits for every queued write.
            await asyncio.shield(loop.run_in_executor(writer, store.add_query, run_id, result))
            done += 1
            if done % PROGRESS_EVERY == 0:
                total = len(stored) + done
                log.info("run.progress", extra={"stored": total, "of": len(queries)})

        try:
            async with asyncio.TaskGroup() as group:
                for query, request in zip(todo, requests, strict=True):
                    group.create_task(one(query, request))
        except* (SutError, httpx.HTTPError, ValidationError, RunFailed) as failed:
            first = failed.exceptions[0]
            raise RunFailed(f"{type(first).__name__}: {first}") from failed
    return done
