# ADR 0005: Gold labels live in the harness, never in the system under test

- **Status:** accepted
- **Date:** 2026-10-19
- **Step:** 1.9

## Context
The evaluation compares retrieved chunks with human-labeled gold spans. If the labels, the `answerable` flag or the expected answer were visible to the RAG service, a bug or a shortcut could leak them into retrieval or generation, and the numbers would be inflated without any visible error. An outside team plugging in their own RAG service must not have to expose or accept labels either.

## Decision
Queries and gold spans are versioned, hashed files read only by the harness (`evalsets/`). The Postgres corpus holds documents and chunks only. The service accepts a query, an optional `doc_id`, a strategy, a chunker and k, and nothing else; no field named `gold`, `answerable` or `expected` may appear in a request body or a service table. The harness talks to the service over HTTP only, and `service/` never imports `harness/` or reads `evalsets/`.

## Alternatives considered
- **Store labels next to chunks for convenience** (for example a `is_gold` column). Rejected: it makes leakage possible by construction and breaks the claim that the service is a black box.
- **Rely on code review to keep labels out.** Rejected: a rule that is not enforced mechanically is eventually broken. The import boundary is enforced by import-linter once there are two packages to separate (step 2.7).
- **A shared in-process library for both sides.** Rejected: it would remove the HTTP boundary that makes the tool usable on other systems.

## Consequences
- The service is exercised exactly as an external system would be, and the leakage claim is checkable: grep for the forbidden field names, run import-linter, read the request model.
- The wire models for `/retrieve` and `/answer` are defined once in a shared module imported by both sides, so the two cannot drift.
- The harness must send the `doc_id` (a document identifier is allowed; a label is not). Per-category query templates still tell the service which clause is wanted; that is a property of the task, discussed in the threats to validity (lexical alignment, Design §10).
- Gold labels in a harness-owned judge prompt (the correctness judge sees the gold span) are not leakage: the judge is part of the instrument.
