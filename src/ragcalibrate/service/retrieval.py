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


async def _why_empty(
    conn: AsyncConnection, corpus: str, doc_id: str, chunker_id: str, embedder_id: str
) -> RagError:
    # An empty result is never a silent "nothing relevant": it means a typo or a missing ingest,
    # and scoring it as zero recall would hide that.
    cursor = await conn.execute(
        "SELECT 1 FROM documents WHERE corpus = %s AND external_id = %s", (corpus, doc_id)
    )
    if await cursor.fetchone() is None:
        return DocumentNotFound(f"no {corpus} document {doc_id!r}")
    return NotIndexed(
        f"{corpus} document {doc_id!r} has no chunks for chunker {chunker_id!r}"
        f" with vectors from {embedder_id!r}"
    )
