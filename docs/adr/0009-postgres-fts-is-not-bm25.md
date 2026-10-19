# ADR 0009: Postgres full-text search is named FTS, never BM25

- **Status:** accepted for the naming; the S1 query-construction part is added in step 3.1 (see Open)
- **Date:** 2026-10-19
- **Step:** 1.9, completed in 3.1

## Context
Strategy S1 is lexical retrieval with Postgres full-text search (`ts_rank_cd`). A reader who sees "BM25" expects inverse document frequency weighting and length normalization with the standard parameters. Postgres's `ts_rank` and `ts_rank_cd` do not implement BM25. Calling S1 "BM25" would be an easy claim for a reviewer to refute and would make every comparison against dense retrieval look like it used a different method than it did.

## Decision
The strategy is called **Postgres FTS** (id `s1` or similar) in code, configs, docs, reports and the README. The text-search configuration (`english` or `simple`) is part of the strategy identity, because it changes stemming and so results. A real BM25 implementation is an optional extra strategy, not a rename of S1.

## Alternatives considered
- **Call it BM25 and note the difference in a footnote.** Rejected: the name appears in tables and tags, where footnotes are lost.
- **Add a BM25 extension (for example ParadeDB's `pg_search`) now.** Deferred: it adds an extension to the image and to CI before there is evidence that FTS is the weak point. Revisit after the first strategy comparison (Phase 3), as an extra strategy.

## Consequences
- Results can state exactly what was run, and the planned demo regression (switching the text-search configuration) is a deliberate, versioned change.
- A comparison "FTS vs dense" is honest about what FTS is. If FTS looks weak, whether that is FTS or an AND-semantics problem in the query is a separate question.
- **Open (step 3.1):** the query construction. `websearch_to_tsquery` combines terms with AND, and CUAD's templated questions are long, so S1 may match almost nothing until the query is built differently (finding F-002). The chosen construction is added to this ADR when 3.1 measures it.
