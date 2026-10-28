"""Ingest against real Postgres: idempotent, resumable, exact offsets and vectors (plan step 2.6).

A small fake chunker and embedder stand in for C1 and bge-small, so these tests need no model
files; the real ones have their own tests, and `make ingest` runs them on all of CUAD.
"""

from collections.abc import Sequence
from typing import Any

import numpy as np
import psycopg
import pytest

from ragcalibrate.corpora.schema import Document
from ragcalibrate.ingest.chunkers import Chunk
from ragcalibrate.ingest.embedding import Vectors
from ragcalibrate.ingest.load import (
    IngestError,
    count_offset_mismatches,
    counts,
    embed_chunks,
    ingest_documents,
)

CORPUS, CHUNKER, EMBEDDER = "test", "fixed10", "fake3"
DOCUMENTS = [
    Document(id="a", text="The Licensee shall indemnify the Licensor against all claims."),
    # Non-ASCII on purpose: Postgres and Python must count the same characters.
    Document(id="b", text="Señor Müller’s agreement — governed by the laws of Zürich."),  # noqa: RUF001
    Document(id="c", text="Short."),
]


def chunk(text: str) -> list[Chunk]:
    return [Chunk(i, min(i + 10, len(text)), text[i : i + 10]) for i in range(0, len(text), 10)]


def embed(texts: Sequence[str], dimension: int = 3) -> Vectors:
    # Deterministic, unit length, and full of digits that a lossy round-trip would change.
    rng = [np.random.default_rng(sum(map(ord, t))) for t in texts]
    rows = np.array([r.standard_normal(dimension) for r in rng], dtype=np.float32)
    return (rows / np.linalg.norm(rows, axis=1, keepdims=True)).reshape(-1, dimension)


def load_all(conn: psycopg.Connection, batch_size: int = 4) -> None:
    ingest_documents(conn, CORPUS, DOCUMENTS, CHUNKER, chunk)
    embed_chunks(conn, CHUNKER, EMBEDDER, embed, batch_size)


def contents(conn: psycopg.Connection) -> tuple[list[tuple[Any, ...]], ...]:
    """Every stored row, identified by content instead of generated ids."""
    documents = conn.execute(
        "SELECT corpus, external_id, sha256, text FROM documents ORDER BY 1, 2"
    ).fetchall()
    chunks = conn.execute(
        "SELECT d.external_id, c.chunker_id, c.start_char, c.end_char, c.text"
        " FROM chunks c JOIN documents d ON d.id = c.document_id ORDER BY 1, 2, 3, 4"
    ).fetchall()
    embeddings = conn.execute(
        "SELECT d.external_id, c.start_char, e.embedder_id, e.embedding::text"
        " FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id"
        " JOIN documents d ON d.id = c.document_id ORDER BY 1, 2, 3"
    ).fetchall()
    return documents, chunks, embeddings


# 10-character chunks of 61, 58 and 6 characters: 7 + 6 + 1.
CHUNKS = 14


def test_ingest_twice_stores_each_row_once(conn: psycopg.Connection) -> None:
    load_all(conn)
    first = contents(conn)
    assert counts(conn, CORPUS, CHUNKER, EMBEDDER) == (3, CHUNKS, CHUNKS)

    assert ingest_documents(conn, CORPUS, DOCUMENTS, CHUNKER, chunk) == 0
    assert embed_chunks(conn, CHUNKER, EMBEDDER, embed, batch_size=4) == 0
    assert contents(conn) == first


def test_interrupted_document_stage_resumes_to_the_clean_result(
    conn: psycopg.Connection,
) -> None:
    def chunk_then_fail_mid_copy(text: str) -> list[Chunk]:
        # The second document's last chunk breaks the table's CHECK, so the failure happens
        # inside its transaction, after the document row and some chunks were sent.
        if text == DOCUMENTS[1].text:
            return [*chunk(text), Chunk(5, 5, "")]
        return chunk(text)

    with pytest.raises(psycopg.errors.CheckViolation):
        ingest_documents(conn, CORPUS, DOCUMENTS, CHUNKER, chunk_then_fail_mid_copy)
    # The first document is committed; the one in flight left nothing behind.
    stored = conn.execute("SELECT external_id FROM documents").fetchall()
    assert stored == [("a",)]
    assert counts(conn, CORPUS, CHUNKER, EMBEDDER).chunks == 7

    assert ingest_documents(conn, CORPUS, DOCUMENTS, CHUNKER, chunk) == 2
    embed_chunks(conn, CHUNKER, EMBEDDER, embed, batch_size=4)
    resumed = contents(conn)

    conn.execute("TRUNCATE documents, chunks, chunk_embeddings")
    load_all(conn)
    assert resumed == contents(conn)


def test_interrupted_embedding_stage_resumes_without_redoing_committed_batches(
    conn: psycopg.Connection,
) -> None:
    ingest_documents(conn, CORPUS, DOCUMENTS, CHUNKER, chunk)
    calls: list[int] = []

    def embed_then_crash(texts: Sequence[str]) -> Vectors:
        calls.append(len(texts))
        if len(calls) == 2:
            raise RuntimeError("interrupted")
        return embed(texts)

    with pytest.raises(RuntimeError, match="interrupted"):
        embed_chunks(conn, CHUNKER, EMBEDDER, embed_then_crash, batch_size=4)
    assert counts(conn, CORPUS, CHUNKER, EMBEDDER).embeddings == 4

    # Only the chunks without a vector are embedded on the second run.
    assert embed_chunks(conn, CHUNKER, EMBEDDER, embed, batch_size=4) == CHUNKS - 4
    resumed = contents(conn)

    conn.execute("TRUNCATE documents, chunks, chunk_embeddings")
    load_all(conn)
    assert resumed == contents(conn)


def test_changed_document_text_is_refused_and_nothing_is_written(
    conn: psycopg.Connection,
) -> None:
    load_all(conn)
    before = contents(conn)
    edited = [*DOCUMENTS[:2], Document(id="c", text="Longer.")]
    with pytest.raises(IngestError, match="stored with different text, first 'c'"):
        ingest_documents(conn, CORPUS, edited, "another-chunker", chunk)
    assert contents(conn) == before


def test_offsets_slice_the_stored_text_and_the_check_catches_a_bad_chunk(
    conn: psycopg.Connection,
) -> None:
    ingest_documents(conn, CORPUS, DOCUMENTS, CHUNKER, chunk)
    assert count_offset_mismatches(conn, CORPUS, CHUNKER) == 0

    # Same length (the table's CHECK allows it), wrong content: only the slice check sees it.
    conn.execute("UPDATE chunks SET text = 'xxxxxxxxxx' WHERE start_char = 0 AND end_char = 10")
    assert count_offset_mismatches(conn, CORPUS, CHUNKER) == 2


def test_vectors_round_trip_bit_for_bit(conn: psycopg.Connection) -> None:
    load_all(conn)
    rows = conn.execute(
        "SELECT c.text, e.embedding::text"
        " FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id"
    ).fetchall()
    stored = np.array([[float(x) for x in v.strip("[]").split(",")] for _, v in rows], np.float32)
    assert np.array_equal(stored, embed([text for text, _ in rows]))


def test_a_second_embedder_reuses_the_same_chunks(conn: psycopg.Connection) -> None:
    load_all(conn)

    def embed5(texts: Sequence[str]) -> Vectors:
        return embed(texts, dimension=5)

    assert embed_chunks(conn, CHUNKER, "fake5", embed5, batch_size=4) == CHUNKS
    dims = conn.execute(
        "SELECT embedder_id, vector_dims(embedding), count(*) FROM chunk_embeddings"
        " GROUP BY 1, 2 ORDER BY 1"
    ).fetchall()
    assert dims == [("fake3", 3, CHUNKS), ("fake5", 5, CHUNKS)]
    assert counts(conn, CORPUS, CHUNKER, "fake5").chunks == CHUNKS
