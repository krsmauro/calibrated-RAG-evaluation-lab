"""Retrieval strategies over the corpus in Postgres: plain async functions, no FastAPI here."""

from psycopg import AsyncConnection

from ragcalibrate.contract import RetrievedChunk
from ragcalibrate.ingest.embedding import Vectors
from ragcalibrate.ingest.load import vector_literal
from ragcalibrate.service.errors import DocumentNotFound, NotIndexed, RagError

# Exact search on purpose: every chunk of the one document is scored (at most 351 in CUAD), so
# the top k is exact. An ANN index under a per-document filter can return fewer or different
# rows; plan step 2.8 measures whether one is worth having (ADR 0002). Equal scores are ordered
# by position in the document, so ties always come back in the same order.
DENSE_SQL = """
SELECT c.id, c.start_char, c.end_char, c.text,
       1 - (e.embedding <=> %(query)s::vector) AS score
FROM documents d
JOIN chunks c ON c.document_id = d.id AND c.chunker_id = %(chunker_id)s
JOIN chunk_embeddings e ON e.chunk_id = c.id AND e.embedder_id = %(embedder_id)s
WHERE d.corpus = %(corpus)s AND d.external_id = %(doc_id)s
ORDER BY score DESC, c.start_char
LIMIT %(k)s
"""

# S1, Postgres FTS (ADR 0009: not BM25). The configuration must be the one migration 0003 builds
# chunks.tsv with; an integration test checks it. Changing it to `simple` turns off stemming.
# No GIN index: under the per-document filter the planner reads the document's chunks through
# the unique index and filters them, and it did not pick a GIN index when one was offered.
FTS_CONFIG = "english"
# The query becomes an OR over its distinct lexemes, not websearch_to_tsquery's AND: CUAD's
# questions are long templates, and an AND of all their words matched no chunk for 84% of dev
# queries (finding F-002). Ranked by ts_rank, not ts_rank_cd as Design §7 had it: better on dev.
# ADR 0009 has the measurements and the rejected options. Neither function weighs a term by its
# rarity (no IDF), so common words count as much as rare ones. Each lexeme is quoted for the
# tsquery input syntax: a lexeme can contain a quote (a URL such as x.com/o'brien is one), and
# unescaped it would break the query or change its structure.
# A query with no lexemes (only stopwords or punctuation) builds NULL and matches nothing.
# Ties are ordered by position, as in DENSE_SQL.
FTS_SQL = r"""
WITH q AS (
    SELECT string_agg(
        '''' || replace(replace(lexeme, '\', '\\'), '''', '''''') || '''', ' | '
    )::tsquery AS query
    FROM unnest(to_tsvector(%(config)s::regconfig, %(query)s))
)
SELECT c.id, c.start_char, c.end_char, c.text, ts_rank(c.tsv, q.query) AS score
FROM q, documents d
JOIN chunks c ON c.document_id = d.id AND c.chunker_id = %(chunker_id)s
WHERE d.corpus = %(corpus)s AND d.external_id = %(doc_id)s AND c.tsv @@ q.query
ORDER BY score DESC, c.start_char
LIMIT %(k)s
"""


async def dense(
    conn: AsyncConnection,
    *,
    corpus: str,
    doc_id: str,
    chunker_id: str,
    embedder_id: str,
    query_vector: Vectors,
    k: int,
) -> list[RetrievedChunk]:
    """S2: the k chunks of one document closest to the query by cosine similarity, best first."""
    params = {
        "query": vector_literal(query_vector),
        "corpus": corpus,
        "doc_id": doc_id,
        "chunker_id": chunker_id,
        "embedder_id": embedder_id,
        "k": k,
    }
    rows = await (await conn.execute(DENSE_SQL, params)).fetchall()
    if not rows:
        raise await _why_empty(conn, corpus, doc_id, chunker_id, embedder_id)
    return [
        RetrievedChunk(chunk_id=chunk_id, start_char=start, end_char=end, text=text, score=score)
        for chunk_id, start, end, text, score in rows
    ]


async def fts(
    conn: AsyncConnection, *, corpus: str, doc_id: str, chunker_id: str, query: str, k: int
) -> list[RetrievedChunk]:
    """S1: the k chunks of one document that best match the query's words, best first.

    Only chunks that share a word with the query come back, so there can be fewer than k, or
    none. Unlike dense search, an empty list is then the answer, not an error.
    """
    params = {
        "config": FTS_CONFIG,
        "query": query,
        "corpus": corpus,
        "doc_id": doc_id,
        "chunker_id": chunker_id,
        "k": k,
    }
    rows = await (await conn.execute(FTS_SQL, params)).fetchall()
    if not rows and not await _has_chunks(conn, corpus, doc_id, chunker_id):
        raise await _why_empty(conn, corpus, doc_id, chunker_id, embedder_id=None)
    return [
        RetrievedChunk(chunk_id=chunk_id, start_char=start, end_char=end, text=text, score=score)
        for chunk_id, start, end, text, score in rows
    ]


async def _has_chunks(conn: AsyncConnection, corpus: str, doc_id: str, chunker_id: str) -> bool:
    cursor = await conn.execute(
        "SELECT 1 FROM documents d JOIN chunks c ON c.document_id = d.id AND c.chunker_id = %s"
        " WHERE d.corpus = %s AND d.external_id = %s LIMIT 1",
        (chunker_id, corpus, doc_id),
    )
    return await cursor.fetchone() is not None


async def _why_empty(
    conn: AsyncConnection, corpus: str, doc_id: str, chunker_id: str, embedder_id: str | None
) -> RagError:
    # An empty result is never a silent "nothing relevant" when the cause is a typo or a missing
    # ingest: scoring that as zero recall would hide it.
    cursor = await conn.execute(
        "SELECT 1 FROM documents WHERE corpus = %s AND external_id = %s", (corpus, doc_id)
    )
    if await cursor.fetchone() is None:
        return DocumentNotFound(f"no {corpus} document {doc_id!r}")
    vectors = f" with vectors from {embedder_id!r}" if embedder_id else ""
    return NotIndexed(
        f"{corpus} document {doc_id!r} has no chunks for chunker {chunker_id!r}{vectors}"
    )
