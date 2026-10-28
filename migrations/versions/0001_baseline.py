"""Baseline corpus schema: the vector extension, documents and chunks.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Deliberately absent, each added by the step that has the evidence for it:
# - chunks.embedding and its model id: the embedding model (so the dimension) is chosen in
#   plan step 2.5; a guessed vector(d) now would only force an ALTER later. (Migration 0002
#   stores embeddings in their own table instead.)
# - chunks.tsv and its GIN index: plan phase 3 (Postgres FTS strategy).
# - any HNSW index: plan step 2.8 measures exact search against HNSW before adding one.


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE documents (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            corpus      text   NOT NULL,
            external_id text   NOT NULL,
            text        text   NOT NULL,
            sha256      text   NOT NULL,
            metadata    jsonb  NOT NULL DEFAULT '{}',
            created_at  timestamptz NOT NULL DEFAULT now(),
            -- Identity is the source dataset's own id. sha256 is kept to detect changed content
            -- on re-ingest; it is not unique, since two filings can have identical text.
            UNIQUE (corpus, external_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE chunks (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            document_id bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            chunker_id  text   NOT NULL,
            start_char  integer NOT NULL,
            end_char    integer NOT NULL,
            text        text   NOT NULL,
            -- Offsets are half-open character offsets into documents.text. Postgres and Python
            -- both count code points, so the length must match. (text[start:end] == chunk text
            -- needs the document row, so that check lives in tests and a post-ingest check.)
            CHECK (start_char >= 0 AND end_char > start_char),
            CHECK (char_length(text) = end_char - start_char),
            -- Idempotent re-chunking. Its index also serves the per-document lookup
            -- (document_id, chunker_id) that every retrieval makes, so no separate btree.
            UNIQUE (document_id, chunker_id, start_char, end_char)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE chunks")
    op.execute("DROP TABLE documents")
    op.execute("DROP EXTENSION vector")
