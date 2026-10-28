"""Load documents, chunks and embeddings into Postgres, idempotent and resumable (plan step 2.6).

Two stages, each safe to re-run and to interrupt:

1. `ingest_documents`: one transaction per document inserts it (if new) and COPYs its chunks for
   one chunker. A document that already has chunks for that chunker is skipped, so a re-run is a
   no-op and an interrupted run loses at most the document in flight.
2. `embed_chunks`: embeds the chunks of one chunker that have no vector yet for one embedder,
   committing every `batch_size` chunks. A second embedding model (plan step 4.10) is a second
   call over the same chunks.

Pass a connection opened with autocommit=True. Each `conn.transaction()` below is then a real
transaction that commits when its block ends. Without autocommit, the first query opens an
implicit transaction, every block becomes a savepoint inside it, and an interruption rolls back
the whole ingest instead of the last unit.
"""

import hashlib
import logging
from collections.abc import Callable, Sequence
from typing import NamedTuple

import psycopg

from ragcalibrate.corpora.schema import Document
from ragcalibrate.ingest.chunkers import Chunk
from ragcalibrate.ingest.embedding import Vectors

logger = logging.getLogger(__name__)


class IngestError(Exception):
    """The database holds something this ingest must not overwrite."""


class Counts(NamedTuple):
    documents: int
    chunks: int
    embeddings: int


def ingest_documents(
    conn: psycopg.Connection,
    corpus: str,
    documents: Sequence[Document],
    chunker_id: str,
    chunk: Callable[[str], Sequence[Chunk]],
) -> int:
    """Store each document and its chunks for `chunker_id`; returns how many were chunked now.

    A document's identity is (corpus, its dataset id). If any document is already stored with
    different text, nothing is written: chunk offsets, and the gold spans in the eval sets,
    point into the stored text. The data are pinned by checksum, so a mismatch means a different
    dataset version, which belongs in a fresh database.
    """
    _require_autocommit(conn)
    stored: dict[str, tuple[int, str]] = {
        external_id: (document_id, sha256)
        for external_id, document_id, sha256 in conn.execute(
            "SELECT external_id, id, sha256 FROM documents WHERE corpus = %s", (corpus,)
        )
    }
    hashes = [hashlib.sha256(doc.text.encode()).hexdigest() for doc in documents]
    changed = [
        doc.id
        for doc, sha256 in zip(documents, hashes, strict=True)
        if doc.id in stored and stored[doc.id][1] != sha256
    ]
    if changed:
        raise IngestError(
            f"{len(changed)} {corpus} documents are stored with different text,"
            f" first {changed[0]!r}; nothing was written"
        )
    chunked: set[int] = {
        document_id
        for (document_id,) in conn.execute(
            "SELECT DISTINCT document_id FROM chunks WHERE chunker_id = %s", (chunker_id,)
        )
    }
    done = 0
    for doc, sha256 in zip(documents, hashes, strict=True):
        document_id = stored[doc.id][0] if doc.id in stored else None
        if document_id in chunked:
            continue
        chunks = chunk(doc.text)
        with conn.transaction():
            if document_id is None:
                [(document_id,)] = conn.execute(
                    "INSERT INTO documents (corpus, external_id, text, sha256)"
                    " VALUES (%s, %s, %s, %s) RETURNING id",
                    (corpus, doc.id, doc.text, sha256),
                ).fetchall()
            with conn.cursor().copy(
                "COPY chunks (document_id, chunker_id, start_char, end_char, text) FROM STDIN"
            ) as copy:
                for c in chunks:
                    copy.write_row((document_id, chunker_id, c.start_char, c.end_char, c.text))
        done += 1
    logger.info(
        "ingest.documents.completed",
        extra={"corpus": corpus, "chunker_id": chunker_id, "chunked": done},
    )
    return done


def embed_chunks(
    conn: psycopg.Connection,
    chunker_id: str,
    embedder_id: str,
    embed: Callable[[Sequence[str]], Vectors],
    batch_size: int,
) -> int:
    """Embed every chunk of `chunker_id` that has no vector for `embedder_id`; returns how many.

    Pending chunks are taken in id order and committed `batch_size` at a time, so a resumed run
    continues where the last commit ended.
    """
    _require_autocommit(conn)
    pending: list[tuple[int, str]] = conn.execute(
        """
        SELECT c.id, c.text FROM chunks c
        WHERE c.chunker_id = %s AND NOT EXISTS (
            SELECT 1 FROM chunk_embeddings e WHERE e.chunk_id = c.id AND e.embedder_id = %s
        )
        ORDER BY c.id
        """,
        (chunker_id, embedder_id),
    ).fetchall()
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        vectors = embed([text for _, text in batch])
        with (
            conn.transaction(),
            conn.cursor().copy(
                "COPY chunk_embeddings (chunk_id, embedder_id, embedding) FROM STDIN"
            ) as copy,
        ):
            for (chunk_id, _), vector in zip(batch, vectors, strict=True):
                copy.write_row((chunk_id, embedder_id, vector_literal(vector)))
        logger.info(
            "ingest.embed.batch",
            extra={"embedder_id": embedder_id, "done": start + len(batch), "total": len(pending)},
        )
    return len(pending)


def count_offset_mismatches(conn: psycopg.Connection, corpus: str, chunker_id: str) -> int:
    """Chunks whose text is not their document's [start_char, end_char) slice; must be 0.

    Checked inside Postgres, so it proves the stored rows agree, not only the Python objects.
    The chunks table already checks that a chunk's length equals end_char - start_char.
    """
    [(mismatches,)] = conn.execute(
        """
        SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE d.corpus = %s AND c.chunker_id = %s
          AND substr(d.text, c.start_char + 1, c.end_char - c.start_char) <> c.text
        """,
        (corpus, chunker_id),
    ).fetchall()
    return mismatches


def counts(conn: psycopg.Connection, corpus: str, chunker_id: str, embedder_id: str) -> Counts:
    """Rows stored for one corpus: documents, chunks for one chunker, vectors for one model."""
    [row] = conn.execute(
        """
        SELECT
            (SELECT count(*) FROM documents WHERE corpus = %(corpus)s),
            (SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id
             WHERE d.corpus = %(corpus)s AND c.chunker_id = %(chunker_id)s),
            (SELECT count(*) FROM chunk_embeddings e
             JOIN chunks c ON c.id = e.chunk_id JOIN documents d ON d.id = c.document_id
             WHERE d.corpus = %(corpus)s AND c.chunker_id = %(chunker_id)s
               AND e.embedder_id = %(embedder_id)s)
        """,
        {"corpus": corpus, "chunker_id": chunker_id, "embedder_id": embedder_id},
    ).fetchall()
    return Counts(*row)


def vector_literal(vector: Vectors) -> str:
    """One vector in pgvector's text input format, for COPY or a `%s::vector` parameter."""
    # pgvector's text input. A float32 converted to a Python float is exact, and repr round-trips
    # it, so the stored float4 equals the computed value bit for bit (an integration test checks).
    return "[" + ",".join(map(repr, vector.tolist())) + "]"


def _require_autocommit(conn: psycopg.Connection) -> None:
    if not conn.autocommit:
        raise ValueError("open the connection with autocommit=True (see the module docstring)")
