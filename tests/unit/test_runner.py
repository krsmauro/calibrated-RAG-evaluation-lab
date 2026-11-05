"""The full runner (plan step 3.7): resumable, one retry layer, responses checked against the
config. The system under test is a fake that answers from the request alone, so two runs of the
same queries give the same rows."""

import asyncio
import hashlib
import threading
from pathlib import Path

import httpx
import pytest

from ragcalibrate.contract import RetrievedChunk, RetrieveRequest, RetrieveResponse
from ragcalibrate.corpora.schema import Gold, GoldSpan, Query
from ragcalibrate.harness import runner
from ragcalibrate.harness.adapter import SutError
from ragcalibrate.harness.manifest import RunConfig, load_config
from ragcalibrate.harness.run import QueryResult, score
from ragcalibrate.harness.runner import RunFailed, execute, retrieve_with_retries
from ragcalibrate.harness.store import Run, RunStore

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


REPO = Path(__file__).resolve().parents[2]
CONFIG = RunConfig(
    corpus="cuad",
    split="dev",
    strategy="rerank",
    chunker_id="c1",
    embedder_id="bge",
    reranker_id="minilm",
    rrf_k=10,
    fusion_depth=100,
    rerank_depth=10,
)
QUERIES = [Query(id=f"q{i:02}", document_id=f"d{i % 5}", text=f"question {i}") for i in range(40)]
GOLD = {
    q.id: Gold(
        query_id=q.id,
        document_id=q.document_id,
        category=f"cat {i % 3}",
        spans=(GoldSpan(start=10 * (i % 13), end=10 * (i % 13) + 5, text="....."),),
    )
    for i, q in enumerate(QUERIES)
}


def answer(request: RetrieveRequest, embedder_id: str | None = None) -> RetrieveResponse:
    """What the fake service returns: ten chunks, ordered by a hash of the question."""
    seed = int(hashlib.sha256(request.query.encode()).hexdigest(), 16)
    starts = sorted(range(0, 200, 10), key=lambda s: (seed >> s) % 97)[: request.k]
    return RetrieveResponse(
        strategy=request.strategy,
        chunker_id=request.chunker_id,
        embedder_id=embedder_id or request.embedder_id,
        reranker_id="minilm" if request.strategy == "rerank" else None,
        chunks=[
            RetrievedChunk(chunk_id=s, start_char=s, end_char=s + 10, text="x" * 10, score=-r / 7)
            for r, s in enumerate(starts)
        ],
    )


class FakeSut:
    def __init__(self, *, fail_on_call: int | None = None, embedder_id: str | None = None) -> None:
        self.calls = 0
        self.answered = 0  # requests that got an answer: each is scored and must be stored
        self.fail_on_call = fail_on_call
        self.embedder_id = embedder_id
        self.reached = asyncio.Event()

    async def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        self.calls += 1
        call = self.calls  # before yielding: other queries move the counter meanwhile
        await asyncio.sleep(0)  # let other queries run, as a real request would
        if call == self.fail_on_call:
            raise SutError(400, "bad_request", "planted")
        self.answered += 1
        return answer(request, self.embedder_id)


class BlockingSut(FakeSut):
    """Answers `before` queries, then hangs every request: a run to be killed midway."""

    def __init__(self, before: int) -> None:
        super().__init__()
        self.before = before

    async def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        self.calls += 1
        if self.calls > self.before:
            self.reached.set()
            await asyncio.Event().wait()  # never set
        await asyncio.sleep(0)
        self.answered += 1
        return answer(request)


def open_store(tmp_path: Path, *run_ids: str) -> RunStore:
    store = RunStore.open(tmp_path / "runs.sqlite")
    for run_id in run_ids:
        store.add_run(
            Run(
                id=run_id,
                created_at="2026-11-04T10:00:00Z",
                git_sha="0" * 40,
                dirty=False,
                config_hash="c",
                evalset_hash="e",
                corpus="cuad",
                split="dev",
                strategy="rerank",
                chunker_id="c1",
                manifest_json="{}",
            )
        )
    return store


async def run(store: RunStore, run_id: str, sut: FakeSut) -> int:
    return await execute(sut, store, run_id, CONFIG, QUERIES, GOLD, concurrency=4)


async def test_every_query_is_stored_with_its_scores(tmp_path: Path) -> None:
    with open_store(tmp_path, "a") as store:
        assert await run(store, "a", FakeSut()) == len(QUERIES)
        expected = [
            score(answer(CONFIG.request(q.text, q.document_id)), GOLD[q.id]) for q in QUERIES
        ]
        assert store.queries("a") == expected  # QUERIES are already in query id order
        assert {r.metrics["recall@5"] for r in expected} == {0.0, 1.0}  # the fixture is not trivial


async def test_a_run_stopped_by_an_error_resumes_to_the_rows_of_an_unstopped_run(
    tmp_path: Path,
) -> None:
    with open_store(tmp_path, "whole", "stopped") as store:
        await run(store, "whole", FakeSut())
        stopped = FakeSut(fail_on_call=15)
        with pytest.raises(RunFailed, match="SutError: 400 bad_request: planted"):
            await run(store, "stopped", stopped)
        kept = len(store.query_ids("stopped"))
        assert 0 < kept < len(QUERIES)  # stopped midway, with whole queries stored
        assert kept == stopped.answered  # every answer it got was stored

        resumed = FakeSut()
        assert await run(store, "stopped", resumed) == len(QUERIES) - kept
        assert resumed.calls == len(QUERIES) - kept  # asked only for what was missing
        assert store.queries("stopped") == store.queries("whole")


async def test_a_cancelled_run_resumes_to_the_rows_of_an_unstopped_run(tmp_path: Path) -> None:
    # Cancelling is what Ctrl-C does to the run; a kill leaves the same rows (one transaction per
    # query), which the end-to-end check in the step's Done note covers.
    with open_store(tmp_path, "whole", "killed") as store:
        await run(store, "whole", FakeSut())
        sut = BlockingSut(before=12)
        task = asyncio.create_task(run(store, "killed", sut))
        await sut.reached.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        kept = len(store.query_ids("killed"))
        assert 0 < kept <= 12
        assert kept == sut.answered  # every answer it got was stored

        assert await run(store, "killed", FakeSut()) == len(QUERIES) - kept
        assert store.queries("killed") == store.queries("whole")


async def test_answers_queued_behind_a_slow_write_are_stored_when_the_run_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CI's failure, made certain: the store's thread is held on its first write while the run
    # fails, so the answers scored meanwhile wait in its queue. They must be stored, not dropped
    # with the run. A timer lets the held write go, so leaving the run does not wait forever.
    release = threading.Event()
    add_query = RunStore.add_query

    def held(self: RunStore, run_id: str, result: QueryResult) -> None:
        release.wait(timeout=5)
        add_query(self, run_id, result)

    monkeypatch.setattr(RunStore, "add_query", held)
    with open_store(tmp_path, "stopped") as store:
        sut = FakeSut(fail_on_call=15)
        timer = threading.Timer(0.2, release.set)
        timer.start()
        with pytest.raises(RunFailed, match="planted"):
            await run(store, "stopped", sut)
        timer.join()
        assert sut.answered > 1  # answers were queued behind the held write
        assert len(store.query_ids("stopped")) == sut.answered


async def test_store_writes_run_off_the_event_loop_one_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop_thread = threading.get_ident()
    threads: set[int] = set()
    active = 0
    add_query = RunStore.add_query

    def watched(self: RunStore, run_id: str, result: QueryResult) -> None:
        nonlocal active
        active += 1
        assert active == 1  # never two writes at once on the one connection
        threads.add(threading.get_ident())
        add_query(self, run_id, result)
        active -= 1

    monkeypatch.setattr(RunStore, "add_query", watched)
    with open_store(tmp_path, "a") as store:
        await run(store, "a", FakeSut())
    assert threads and loop_thread not in threads


async def test_a_response_from_another_model_stops_the_run(tmp_path: Path) -> None:
    with open_store(tmp_path, "a") as store:
        with pytest.raises(RunFailed, match="the config names"):
            await run(store, "a", FakeSut(embedder_id="another-model"))
        assert store.query_ids("a") == set()


class Flaky:
    """Fails each request with the given errors, in order, then answers."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    async def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return answer(request)


REQUEST = CONFIG.request("question 1", "d1")


async def test_errors_that_can_pass_are_retried_with_jittered_backoff() -> None:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    sut = Flaky(
        SutError(503, "unavailable", "x"), httpx.ConnectError("down"), SutError(429, "x", "")
    )
    assert await retrieve_with_retries(sut, REQUEST, sleep=sleep) == answer(REQUEST)
    assert sut.calls == 4
    # Retry n waits up to 0.5 * 2**(n-1) seconds: 0.5, 1, 2.
    assert len(waits) == 3
    assert all(0 <= w <= bound for w, bound in zip(waits, (0.5, 1.0, 2.0), strict=True))


async def test_retries_stop_after_the_last_attempt() -> None:
    async def sleep(seconds: float) -> None:
        pass

    sut = Flaky(*(SutError(500, "internal", "x") for _ in range(runner.ATTEMPTS)))
    with pytest.raises(SutError, match="500"):
        await retrieve_with_retries(sut, REQUEST, sleep=sleep)
    assert sut.calls == runner.ATTEMPTS


@pytest.mark.parametrize("status", [400, 404, 422])
async def test_a_client_error_is_not_retried(status: int) -> None:
    async def sleep(seconds: float) -> None:
        raise AssertionError("must not wait")

    sut = Flaky(SutError(status, "x", "y"))
    with pytest.raises(SutError):
        await retrieve_with_retries(sut, REQUEST, sleep=sleep)
    assert sut.calls == 1


def test_the_configs_in_the_repository_are_valid() -> None:
    configs = {p.name: load_config(p) for p in sorted((REPO / "configs").glob("*.yaml"))}
    assert {c.strategy for c in configs.values()} == {"fts", "dense", "hybrid", "rerank"}
