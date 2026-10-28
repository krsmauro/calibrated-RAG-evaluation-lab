"""Postgres full-text search on chunks: a stored, generated tsvector column (plan step 3.1).

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# The text-search configuration is part of strategy S1's identity (ADR 0009). `english` stems
# and drops stopwords, so "terminates" matches "termination"; `simple` only lowercases, which
# disables stemming. Switching it is the planned demo regression (plan step 8.5), so it is a
# deliberate change in two places: a new migration here and FTS_CONFIG in service/retrieval.py.
# The query must be parsed with the same configuration as the column; an integration test checks
# that they match.
# STORED, so a query does not re-parse every chunk of its document. Adding the column rewrites
# `chunks` (about 25k rows for CUAD: seconds).
# No GIN index on purpose: retrieval is per document (Design §5.1), at most a few hundred chunks
# that the unique index already finds, and the planner did not use a GIN index for it when one
# was offered (ADR 0009, measured in step 3.1). Add one if corpus-wide search ever exists.


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ADD COLUMN tsv tsvector"
        " GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunks DROP COLUMN tsv")
