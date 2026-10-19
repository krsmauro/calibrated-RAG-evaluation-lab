# ADR 0003: A separate SQLite run store next to the Postgres corpus store

- **Status:** accepted
- **Date:** 2026-10-19
- **Step:** 1.9

## Context
The project stores two different kinds of data. The corpus index (documents, chunks, embeddings) is part of the system under test: rebuilding it changes what retrieval returns. Run results (retrievals, per-query metrics, answers, judgments, manifests) belong to the measuring instrument: they are the evidence behind every reported number and must survive a rebuild of the index. A reviewer will ask why there are two databases.

## Decision
Run results go in a SQLite file owned by the harness. The LLM cache is a third, separate SQLite file. Postgres holds the corpus only. The harness never writes to Postgres and the service never reads the run store.

## Alternatives considered
- **Run results in the same Postgres.** Rejected: re-ingesting or dropping the index could touch past results, and a run store tied to a live server cannot be uploaded as a CI artifact, diffed or queried offline.
- **Results as JSONL files only.** Rejected: paired comparisons are joins on `query_id`, and the long-format metrics table is easier to query and constrain (one row per run, query and metric) in SQL.
- **One SQLite file for results and cache.** Rejected: the cache must be deletable or bypassable without touching results (A/A runs, ADR 0008).

## Consequences
- A run store is one file: uploadable as an artifact, inspectable with any SQLite client, no server needed to compare runs.
- Two schemas to migrate. The SQLite store carries an explicit schema version and forward-only steps (database rules), while Postgres uses Alembic (migration 0001 exists).
- SQLite is synchronous: the runner writes through one writer or `asyncio.to_thread`, never from the event loop directly.
- Revisit only if multiple runners must write one store concurrently at a scale SQLite's single writer cannot serve.
