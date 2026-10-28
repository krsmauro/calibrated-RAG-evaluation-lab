"""Chunk embeddings in their own table, one row per (chunk, embedding model).

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Why a separate table and an untyped `vector` column (plan step 2.6, ADR 0011):
# - A second embedding model (plan step 4.10) embeds the same chunks without a schema change, so
#   a model comparison changes one thing only. A vector(384) column on `chunks` would not allow it.
# - Models differ in dimension (bge-small 384, text-embedding-3-small 1536). An untyped column
#   holds both; exact search works on it as is. One embedder must use one dimension: the ingest
#   writes one model's vectors per embedder_id, and pgvector raises an error if a query compares
#   vectors of different dimensions, so a mix fails loudly instead of ranking silently.
# - An HNSW index on an untyped column needs an expression and a partial index per model, e.g.
#   ON chunk_embeddings USING hnsw ((embedding::vector(384)) vector_cosine_ops)
#   WHERE embedder_id = '<id>'; checked to build on pgvector 0.8.7. Plan step 2.8 decides
#   whether any ANN index is worth having; until then retrieval is exact (no index here).
# The primary key also serves the retrieval join: chunks of one document, then one lookup each.


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE chunk_embeddings (
            chunk_id    bigint NOT NULL REFERENCES chunks (id) ON DELETE CASCADE,
            -- The model and its pinned revision, e.g. EMBEDDER_ID in ingest/embedding.py.
            embedder_id text   NOT NULL,
            embedding   vector NOT NULL,
            PRIMARY KEY (chunk_id, embedder_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE chunk_embeddings")
