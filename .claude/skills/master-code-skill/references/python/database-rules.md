# Backend — Database Rules

Postgres (+ pgvector, full-text search) for the corpus; SQLite for run results and the LLM cache; Alembic for Postgres schema.

## DB-CRITICAL-1 — Schema changes go through Alembic; never `create_all` at startup

- Every Postgres schema change is a migration in `migrations/`, reviewed like code.
- Verify on a real Postgres with pgvector: `alembic upgrade head` from empty, and `downgrade -1` + `upgrade head` for the new revision. CI runs `upgrade head` on a fresh container.
- Destructive or long-locking changes (drop column, rewrite table, build index on a big table) get a note in the migration; use `CREATE INDEX CONCURRENTLY` (needs `autocommit` block in Alembic) for large live tables.
- `/readyz` fails if the DB isn't at the head revision.
- SQLite run store: the schema is created by the harness with an explicit `schema_version` table (`PRAGMA user_version` or a table) and forward-only migration steps. Never silently alter a store that holds past results.

## DB-CRITICAL-2 — Parameterized queries, explicit transactions

See `SEC-CRITICAL-2`. Multi-statement writes that must be atomic (a query's retrievals + metrics + answer) use one transaction. Don't hold a connection open across an LLM/HTTP call.

## DB-HIGH-1 — Postgres: indexes need evidence

- Plan: `btree (document_id, chunker_id)`, `GIN (tsv)`, optional HNSW on `embedding`. Under a per-document filter, **exact** search (sequential scan within the document's chunks) is the baseline; an ANN index can change results (recall < 1) and must be measured, not assumed. Record `EXPLAIN (ANALYZE, BUFFERS)` evidence in the ADR.
- ANN index parameters (`m`, `ef_construction`, `hnsw.ef_search`) are part of the experiment config; changing them changes results.
- Distance operator must match the index operator class (`vector_cosine_ops` ↔ `<=>`); a mismatch silently falls back to a seq scan.
- Embedding dimension and model ID are recorded with the chunks. Mixing models in one column silently ruins retrieval.

## DB-HIGH-2 — Full-text search is not BM25

`ts_rank`/`ts_rank_cd` don't implement IDF-based BM25. Name the strategy "Postgres FTS" in code, config, docs and reports. The text-search configuration (`english` vs `simple`) is part of the strategy ID — switching it changes stemming and results (this is the planned "demo regression"; changing it must be a deliberate, versioned change). S1 does not use `websearch_to_tsquery`: it ANDs every word, and on CUAD's long templated questions 84% of dev queries matched nothing (F-002). S1 builds an OR over the query's lexemes, each quoted for the tsquery syntax, and ranks with `ts_rank` (ADR 0009). `tsv` is a stored generated column (migration 0003); the query's `FTS_CONFIG` must match the column's configuration (an integration test checks it). No GIN index under the per-document filter: the planner does not use it (ADR 0009).

## DB-HIGH-3 — Bulk load with `COPY`; keep ingestion idempotent

Chunks and embeddings load via `COPY` (or `executemany` in batches) inside a transaction. Idempotency key = document `sha256` (+ `chunker_id`); enforce with a unique constraint and `ON CONFLICT`. Chunk offsets must satisfy `document.text[start_char:end_char] == chunk.text`; assert it in tests and in a post-ingest check.

## DB-HIGH-4 — SQLite run store: one writer, WAL, long format

- Open with `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=...`. `sqlite3` is synchronous: use `to_thread` or a single writer task, never from the event loop directly.
- Long-format metrics (`query_metrics(run_id, query_id, metric, value)`) so paired comparisons are a join on `query_id`. Add primary keys/unique constraints that enforce one row per `(run_id, query_id, metric)`.
- Runs are append-only. Corrections are new runs. The file must be uploadable as a CI artifact and queryable without a running DB: don't depend on server-side features.
- The LLM cache is a **separate** SQLite file so it can be deleted or bypassed without touching results.

## DB-MEDIUM-1 — Types and time

Store timestamps as UTC (`timestamptz` in Postgres; ISO-8601 UTC text or integer epoch in SQLite). Use `jsonb` for flexible metadata, but query-critical fields get real columns. Large text stays out of hot tables' indexes. Use `NUMERIC`/integers for money if aggregated; `float` is fine for per-call cost estimates if documented.
