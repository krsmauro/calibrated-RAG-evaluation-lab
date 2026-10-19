# ADR 0001: Postgres with pgvector rather than a dedicated vector database

- **Status:** accepted
- **Date:** 2026-10-19
- **Step:** 1.9 (decision implied by 1.3 and 1.4)

## Context
The system under test needs dense retrieval, lexical retrieval and a per-document filter, and the project compares hybrid strategies that fuse the two. The design (Design §5.1) makes retrieval within-document, so the candidate set per query is one contract's chunks, a few dozen to a few hundred rows (contracts have a median of about 33,000 characters, finding F-008). The project must also start with one command and run in CI without services that are hard to host.

## Decision
Use PostgreSQL with the pgvector extension for documents, chunks, embeddings and full-text search, in one database, started by Docker Compose (image pinned to an explicit tag).

## Alternatives considered
- **A dedicated vector database** (a separate service for embeddings, with Postgres or nothing else for text). Rejected for now: it adds a second system to run and keep consistent, and the per-document candidate set is small enough that exact search in Postgres is fast. Hybrid retrieval would need the lexical side somewhere else or duplicated.
- **SQLite with a vector extension.** Rejected: the service is meant to look like a normal backend (async pool, migrations, `EXPLAIN` evidence), and full-text search plus vectors under concurrent load is the point of the demonstration.
- **An in-memory index in the service process.** Rejected: state would be lost on restart, and the data model would not exercise a real database.

## Consequences
- One dependency for corpus storage, one place for `EXPLAIN ANALYZE` evidence, and full-text and vector search can be combined in SQL. The harness still sees only HTTP.
- This is a reasoned decision, not a measured one. Nothing has been benchmarked yet. Revisit if exact search under the per-document filter turns out too slow (ADR 0002, step 2.8), or if the project adds corpus-wide retrieval, where approximate indexes matter far more.
- pgvector and Postgres versions are pinned and recorded (0.8.7 on PostgreSQL 17.11 at the time of writing, step 1.3); a version change can change results.
