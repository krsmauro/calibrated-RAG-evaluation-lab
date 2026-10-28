"""The service through its HTTP interface, on real Postgres and the real model (plan step 2.7).

The app runs its own lifespan (pool, model) and is called through httpx with no socket.
Responses are parsed with the contract models, exactly as the harness will parse them.
"""

import asyncio
import threading
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from ragcalibrate.contract import Problem, RetrieveRequest, RetrieveResponse
from ragcalibrate.corpora.schema import Document, Query
from ragcalibrate.harness.adapter import HttpSut, SutError, SutNotReady
from ragcalibrate.harness.run import retrieve_all
from ragcalibrate.ingest.chunkers import c1_id, chunk_c1
from ragcalibrate.ingest.embedding import EMBEDDER_ID, Embedder, load_tokenizer
from ragcalibrate.ingest.load import embed_chunks, ingest_documents
from ragcalibrate.service import app as service_app
from ragcalibrate.service import routes
from ragcalibrate.service.app import create_app
from ragcalibrate.service.fusion import rrf
from ragcalibrate.service.rerank import RERANKER_ID, Reranker, rerank
from ragcalibrate.service.retrieval import FTS_CONFIG

MODELS = Path(__file__).parents[2] / "data" / "models"
MODEL_DIR = MODELS / "bge-small-en-v1.5"
RERANKER_DIR = MODELS / "ms-marco-MiniLM-L6-v2"

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not all((d / "onnx" / "model.onnx").exists() for d in (MODEL_DIR, RERANKER_DIR)),
        reason="run `make models` first",
    ),
]

CORPUS = "test"
CHUNKER = c1_id(EMBEDDER_ID, 20, 0)
ALPHA = (
    "1. Term. This Agreement starts on the Effective Date and lasts for three years.\n\n"
    "2. Payment. The Customer shall pay every invoice within thirty days of receipt.\n\n"
    "3. Confidentiality. Each party keeps the other party's information secret.\n\n"
    "4. Governing Law. This Agreement is governed by the laws of the State of Delaware.\n\n"
    "5. Termination. Either party may end this Agreement on ninety days written notice.\n"
)
BETA = "This short agreement has a single clause."


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def corpus(database_url: str) -> Iterator[None]:
    tokenizer = load_tokenizer(MODEL_DIR)
    with psycopg.connect(database_url, autocommit=True) as conn:
        documents = [Document(id="alpha", text=ALPHA), Document(id="beta", text=BETA)]
        ingest_documents(conn, CORPUS, documents, CHUNKER, lambda t: chunk_c1(t, tokenizer, 20, 0))
        embed_chunks(conn, CHUNKER, EMBEDDER_ID, Embedder(MODEL_DIR).embed, batch_size=64)
        yield
        conn.execute("TRUNCATE documents, chunks, chunk_embeddings RESTART IDENTITY")


@pytest.fixture(scope="module")
async def client(corpus: None, database_url: str) -> AsyncIterator[httpx.AsyncClient]:
    with pytest.MonkeyPatch.context() as env:
        env.setenv("RAGCALIBRATE_DATABASE_URL", database_url)
        app = create_app()
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                yield client


HYBRID: dict[str, Any] = {"strategy": "hybrid", "rrf_k": 60, "fusion_depth": 10}
RERANK: dict[str, Any] = HYBRID | {"strategy": "rerank", "rerank_depth": 5}


def request(**changes: Any) -> dict[str, Any]:
    base = {
        "query": "Which state's law governs this agreement?",
        "corpus": CORPUS,
        "doc_id": "alpha",
        "strategy": "dense",
        "chunker_id": CHUNKER,
        "k": 3,
    }
    return base | changes


async def retrieve(client: httpx.AsyncClient, **changes: Any) -> RetrieveResponse:
    response = await client.post("/retrieve", json=request(**changes))
    assert response.status_code == 200, response.text
    return RetrieveResponse.model_validate_json(response.content)


async def test_the_closest_chunks_come_first_with_exact_offsets(client: httpx.AsyncClient) -> None:
    result = await retrieve(client)
    assert (result.strategy, result.chunker_id, result.embedder_id) == (
        "dense",
        CHUNKER,
        EMBEDDER_ID,
    )
    assert len(result.chunks) == 3
    # The 20-token windows split clause 4, so the check is the project's relevance rule (R1):
    # the best chunk overlaps the governing-law clause.
    clause_start, clause_end = ALPHA.index("4. Governing Law"), ALPHA.index("5. Termination")
    best = result.chunks[0]
    assert best.start_char < clause_end and clause_start < best.end_char
    scores = [c.score for c in result.chunks]
    assert scores == sorted(scores, reverse=True)
    for c in result.chunks:
        assert ALPHA[c.start_char : c.end_char] == c.text


async def test_a_document_with_fewer_chunks_than_k_returns_all_it_has(
    client: httpx.AsyncClient,
) -> None:
    result = await retrieve(client, doc_id="beta", k=10)
    assert [c.text for c in result.chunks] == [BETA]


async def test_concurrent_requests_give_the_same_answers_as_sequential_ones(
    client: httpx.AsyncClient,
) -> None:
    queries = ["governing law", "when must invoices be paid", "how to terminate", "secrets"]
    sequential = [await retrieve(client, query=q) for q in queries]
    concurrent = await asyncio.gather(*(retrieve(client, query=q) for q in queries * 5))
    assert concurrent == sequential * 5


@pytest.mark.parametrize(
    ("method", "path", "body", "status", "code"),
    [
        ("POST", "/retrieve", request(doc_id="nope"), 404, "document_not_found"),
        ("POST", "/retrieve", request(chunker_id="c9"), 404, "not_indexed"),
        ("POST", "/retrieve", request(embedder_id="other-model"), 422, "unknown_embedder"),
        ("POST", "/retrieve", request(strategy="fts", doc_id="nope"), 404, "document_not_found"),
        ("POST", "/retrieve", request(strategy="fts", chunker_id="c9"), 404, "not_indexed"),
        (
            "POST",
            "/retrieve",
            request(strategy="fts", embedder_id=EMBEDDER_ID),
            422,
            "invalid_request",
        ),
        ("POST", "/retrieve", request(**HYBRID, doc_id="nope"), 404, "document_not_found"),
        ("POST", "/retrieve", request(**HYBRID, chunker_id="c9"), 404, "not_indexed"),
        ("POST", "/retrieve", request(**HYBRID, embedder_id="other"), 422, "unknown_embedder"),
        ("POST", "/retrieve", request(strategy="hybrid"), 422, "invalid_request"),
        ("POST", "/retrieve", request(rrf_k=60), 422, "invalid_request"),
        ("POST", "/retrieve", request(**RERANK, doc_id="nope"), 404, "document_not_found"),
        ("POST", "/retrieve", request(**RERANK, chunker_id="c9"), 404, "not_indexed"),
        ("POST", "/retrieve", request(**RERANK, embedder_id="other"), 422, "unknown_embedder"),
        ("POST", "/retrieve", request(**HYBRID | {"strategy": "rerank"}), 422, "invalid_request"),
        ("POST", "/retrieve", request(**HYBRID, rerank_depth=5), 422, "invalid_request"),
        ("POST", "/retrieve", request(gold=[[0, 5]]), 422, "invalid_request"),
        ("POST", "/retrieve", request(k=101), 422, "invalid_request"),
        ("GET", "/nowhere", None, 404, "http_error"),
    ],
)
async def test_errors_are_problem_details(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    status: int,
    code: str,
) -> None:
    response = await client.request(method, path, json=body)
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    problem = Problem.model_validate_json(response.content)
    assert (problem.status, problem.code) == (status, code)


async def test_ready_only_at_the_expected_schema_revision(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).json() == {"status": "ready"}
    monkeypatch.setattr(routes, "SCHEMA_REVISION", "9999")
    response = await client.get("/readyz")
    assert response.status_code == 503
    assert Problem.model_validate_json(response.content).code == "not_ready"


async def test_the_harness_checks_readiness_before_a_run(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await HttpSut(client).check_ready()
    at_head = routes.SCHEMA_REVISION
    monkeypatch.setattr(routes, "SCHEMA_REVISION", "9999")
    with pytest.raises(SutNotReady, match=f"503 not_ready: database schema is at '{at_head}'"):
        await HttpSut(client).check_ready()


async def test_the_harness_adapter_speaks_the_contract(client: httpx.AsyncClient) -> None:
    sut = HttpSut(client)
    assert await sut.retrieve(RetrieveRequest.model_validate(request())) == await retrieve(client)
    with pytest.raises(SutError) as error:
        await sut.retrieve(RetrieveRequest.model_validate(request(doc_id="nope")))
    assert (error.value.status, error.value.code) == (404, "document_not_found")


async def test_retrieve_all_keeps_query_order_under_concurrency(client: httpx.AsyncClient) -> None:
    texts = ["governing law", "payment", "termination", "secrets", "term"] * 4
    queries = [Query(id=str(i), document_id="alpha", text=t) for i, t in enumerate(texts)]
    responses = await retrieve_all(
        HttpSut(client), queries, corpus=CORPUS, strategy="dense", chunker_id=CHUNKER, k=3,
        concurrency=4,
    )  # fmt: skip
    assert responses == [await retrieve(client, query=t) for t in texts]


async def test_fts_ranks_chunks_that_share_words_with_the_query(
    client: httpx.AsyncClient,
) -> None:
    result = await retrieve(client, strategy="fts", query="Which state's law governs?")
    assert (result.strategy, result.embedder_id) == ("fts", None)
    clause_start, clause_end = ALPHA.index("4. Governing Law"), ALPHA.index("5. Termination")
    best = result.chunks[0]
    assert best.start_char < clause_end and clause_start < best.end_char
    # Best first, and equal scores in document order (the same tiebreak as dense).
    order = [(-c.score, c.start_char) for c in result.chunks]
    assert order == sorted(order)
    for c in result.chunks:
        assert ALPHA[c.start_char : c.end_char] == c.text


@pytest.mark.parametrize(
    ("query", "must_contain"),
    [
        ("Delaware", ["Delaware"]),  # in one chunk only: one result, not k
        ("terminating", ["Termination"]),  # `english` stems both to the same lexeme
        ("xylophone", []),  # no chunk shares a word: an empty answer, not an error
        ("the of and", []),  # only stopwords: no lexemes, so nothing matches
    ],
)
async def test_fts_returns_only_chunks_that_match(
    client: httpx.AsyncClient, query: str, must_contain: list[str]
) -> None:
    result = await retrieve(client, strategy="fts", query=query, k=3)
    assert len(result.chunks) == len(must_contain)
    for chunk, word in zip(result.chunks, must_contain, strict=True):
        assert word in chunk.text


@pytest.mark.parametrize(
    "query",
    [
        "it's the other party's O'Brien",
        "terms at http://example.com/o'brien/law",  # a URL gives a lexeme with a quote in it
        r"C:\path\to a back\\slash \' \\'",
        "law | secret & !pay <-> (term) :* law:A",
        '"governing law" -delaware or payment',
        "%s %(k)s {} 100% ;-- DROP TABLE chunks",
    ],
)
async def test_fts_takes_any_text_as_words_not_as_query_syntax(
    client: httpx.AsyncClient, query: str
) -> None:
    # Quotes, backslashes and tsquery operators in the text must neither break the query nor
    # change its structure.
    await retrieve(client, strategy="fts", query=query)


def test_fts_parses_queries_with_the_configuration_the_column_was_built_with(
    corpus: None, database_url: str
) -> None:
    sql = "SELECT bool_and(tsv = to_tsvector(%s::regconfig, text)) FROM chunks"
    with psycopg.connect(database_url) as conn:
        assert conn.execute(sql, (FTS_CONFIG,)).fetchone() == (True,)
        # The check can fail: without stemming the same text gives different lexemes.
        assert conn.execute(sql, ("simple",)).fetchone() == (False,)


@pytest.mark.parametrize(
    "query",
    [
        "Which state's law governs this agreement?",  # both sides rank the chunks
        "xylophone",  # fts returns nothing: the order is dense's alone
    ],
)
async def test_hybrid_is_rrf_over_the_fts_and_dense_rankings(
    client: httpx.AsyncClient, query: str
) -> None:
    # The fusion itself is unit- and property-tested; this checks the service feeds it the two
    # rankings at fusion_depth and returns its top k, with the dense side's embedder.
    lexical = await retrieve(client, strategy="fts", query=query, k=10)
    semantic = await retrieve(client, query=query, k=10)
    result = await retrieve(client, **HYBRID, query=query, k=3)
    assert (result.strategy, result.embedder_id) == ("hybrid", EMBEDDER_ID)
    assert result.chunks == rrf([lexical.chunks, semantic.chunks], rrf_k=60, k=3)
    assert len(result.chunks) == 3
    if not lexical.chunks:
        assert result.chunks == [
            c.model_copy(update={"score": 1 / (60 + rank)})
            for rank, c in enumerate(semantic.chunks[:3], start=1)
        ]


async def test_rerank_reorders_the_hybrid_top_n_by_the_cross_encoder(
    client: httpx.AsyncClient,
) -> None:
    # The reordering is unit-tested; this checks the service hands the reranker the hybrid's
    # top rerank_depth and returns its top k, with both models' ids.
    query = "Which state's law governs this agreement?"
    candidates = await retrieve(client, **HYBRID, query=query, k=RERANK["rerank_depth"])
    result = await retrieve(client, **RERANK, query=query, k=3)
    assert (result.strategy, result.embedder_id, result.reranker_id) == (
        "rerank",
        EMBEDDER_ID,
        RERANKER_ID,
    )
    scores = Reranker(RERANKER_DIR).score(query, [c.text for c in candidates.chunks])
    assert result.chunks == rerank(candidates.chunks, scores, k=3)
    clause_start, clause_end = ALPHA.index("4. Governing Law"), ALPHA.index("5. Termination")
    best = result.chunks[0]
    assert best.start_char < clause_end and clause_start < best.end_char
    other = await retrieve(client, **HYBRID, query=query)
    assert (other.reranker_id, (await retrieve(client, query=query)).reranker_id) == (None, None)


async def test_the_reranker_is_loaded_once_and_scores_off_the_event_loop(
    corpus: None, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded: list[object] = []
    scored_in: list[threading.Thread] = []

    class CountingReranker:
        def __init__(self) -> None:
            loaded.append(self)

        def score(self, query: str, texts: Sequence[str]) -> list[float]:
            scored_in.append(threading.current_thread())
            return [float(len(t)) for t in texts]

    monkeypatch.setattr(service_app, "Reranker", CountingReranker)
    monkeypatch.setenv("RAGCALIBRATE_DATABASE_URL", database_url)
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as fresh:
            for query in ("governing law", "payment", "termination"):
                result = await retrieve(fresh, **RERANK, query=query)
                # The fake scores by length, so the response follows it: longest text first.
                lengths = [len(c.text) for c in result.chunks]
                assert lengths == sorted(lengths, reverse=True)
    assert len(loaded) == 1
    assert len(scored_in) == 3
    assert threading.main_thread() not in scored_in  # the event loop runs in the main thread
