"""The service through its HTTP interface, on real Postgres and the real model (plan step 2.7).

The app runs its own lifespan (pool, model) and is called through httpx with no socket.
Responses are parsed with the contract models, exactly as the harness will parse them.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from ragcalibrate.contract import Problem, RetrieveRequest, RetrieveResponse
from ragcalibrate.corpora.schema import Document, Query
from ragcalibrate.harness.adapter import HttpSut, SutError
from ragcalibrate.harness.run import retrieve_all
from ragcalibrate.ingest.chunkers import c1_id, chunk_c1
from ragcalibrate.ingest.embedding import EMBEDDER_ID, Embedder, load_tokenizer
from ragcalibrate.ingest.load import embed_chunks, ingest_documents
from ragcalibrate.service import routes
from ragcalibrate.service.app import create_app

MODEL_DIR = Path(__file__).parents[2] / "data" / "models" / "bge-small-en-v1.5"

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not (MODEL_DIR / "onnx" / "model.onnx").exists(), reason="run `make models` first"
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
