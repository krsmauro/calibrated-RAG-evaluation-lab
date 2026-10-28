# ADR 0009: Postgres full-text search is named FTS, never BM25, and how S1 builds its query

- **Status:** accepted (naming 2026-10-19; query construction, ranking function and index 2026-10-28)
- **Date:** 2026-10-19, completed 2026-10-28
- **Step:** 1.9 (naming), 3.1 (query construction)

## Context
Strategy S1 is lexical retrieval with Postgres full-text search. A reader who sees "BM25" expects inverse document frequency weighting and length normalization with the standard parameters. Postgres's `ts_rank` and `ts_rank_cd` do not implement BM25. Calling S1 "BM25" would be an easy claim for a reviewer to refute and would make every comparison against dense retrieval look like it used a different method than it did.

Design §7 specified S1 as `websearch_to_tsquery` with `ts_rank_cd`. `websearch_to_tsquery` combines unquoted words with AND, and every CUAD question is one long template: `Highlight the parts (if any) of this contract related to "<category>" that should be reviewed by a lawyer. Details: <description>`. For "Governing Law" that becomes an AND of 13 terms, including `highlight`, `lawyer` and `detail`, which contract text rarely contains (finding F-002).

## Decision
**Naming.** The strategy is called **Postgres FTS** (wire id `fts`) in code, configs, docs, reports and the README. The text-search configuration (`english` or `simple`) is part of the strategy identity, because it changes stemming and so results. A real BM25 implementation is an optional extra strategy, not a rename of S1.

**Query construction (step 3.1).** S1 turns the query into an **OR over its distinct lexemes**: `to_tsvector('english', query)`, every lexeme quoted for the tsquery input syntax, joined with `|`. The whole question is used as sent; the service knows nothing about CUAD's template. A query with no lexemes (only stopwords or punctuation) matches nothing. Only chunks that share a lexeme with the query are returned, so S1 can return fewer than k chunks, or none, and that is a valid answer, not an error.

**Ranking.** `ts_rank` with default weights and no length normalization, not `ts_rank_cd`. Ties are broken by position in the document (`start_char`), as for dense search.

**Storage.** A stored generated column, `chunks.tsv = to_tsvector('english', text)` (migration 0003). The query's configuration (`FTS_CONFIG` in `service/retrieval.py`) must match it; an integration test checks that. **No GIN index**: retrieval is per document (Design §5.1), the unique index on `chunks` already finds a document's chunks (at most 351 in CUAD), and the planner did not use a GIN index when one was offered.

## Evidence
`uv run python scripts/measure_fts.py` on 2026-10-28: all 5,458 answerable dev queries, 408 contracts, chunker C1 (256/32), config `english`, k = 10. "Short" means fewer rows than min(k, chunks in the contract). Latency is the database round trip from a Python client on the development laptop (Apple Silicon, Docker Desktop), not the HTTP service.

| Query construction | Short | No rows | recall@5 | Hit@5 | MRR@10 | p50 ms | p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AND: full question, `websearch_to_tsquery`, `ts_rank_cd` (Design §7 as written) | 94.8% | 84.0% | 0.048 | 0.060 | 0.045 | 0.90 | 3.50 |
| OR: full question, `ts_rank_cd` | 7.4% | 0.2% | 0.515 | 0.573 | 0.399 | 0.65 | 1.99 |
| **OR: full question, `ts_rank` (chosen)** | 7.4% | 0.2% | **0.560** | **0.627** | **0.455** | 0.40 | 0.70 |
| OR: CUAD template wording removed, `ts_rank_cd` | 12.2% | 0.3% | 0.533 | 0.592 | 0.419 | 0.46 | 1.41 |
| AND: category name only, `plainto_tsquery`, `ts_rank_cd` | 87.7% | 48.2% | 0.314 | 0.343 | 0.292 | 0.33 | 0.54 |
| OR: category name only, `ts_rank_cd` | 47.7% | 3.5% | 0.589 | 0.643 | 0.501 | 0.31 | 0.44 |

For comparison, S2 (dense, same queries): recall@5 0.488, MRR@10 0.393 (`docs/results.md`). The chosen construction run through the service and harness (`uv run ragcalibrate run --strategy fts`) gives the same recall@5 0.560 and MRR@10 0.455; two runs gave identical rankings and scores.

GIN check (same script): with a GIN index on `tsv` created inside a rolled-back transaction, `EXPLAIN ANALYZE` for both the AND and the OR query on the largest dev contract (351 chunks) shows an index scan on `chunks_document_id_chunker_id_start_char_end_char_key` with the `@@` test as a filter; the GIN index is not used. The OR query takes 1.1 ms there.

No confidence intervals: the document-clustered bootstrap is step 4.1. The gaps that decide this ADR (AND vs OR, 0.05 vs 0.56; `ts_rank` vs `ts_rank_cd`, 4.5 points of recall@5 on 5,458 paired queries) are large, but they are dev point estimates.

## Alternatives considered
- **Call it BM25 and note the difference in a footnote.** Rejected: the name appears in tables and tags, where footnotes are lost.
- **Add a BM25 extension (for example ParadeDB's `pg_search`) now.** Deferred: it adds an extension to the image and to CI. Revisit after the first strategy comparison (step 3.9), as an extra strategy. Note that S1 already beats S2 on dev (finding F-011), so the case for it is now "how much does IDF add", not "FTS is the weak point".
- **`websearch_to_tsquery` (AND), as in Design §7.** Rejected: 84% of dev queries return no rows at all.
- **Category name only, or the template wording removed.** The category-only OR form scores highest on dev (recall@5 0.589). Rejected for S1 because it parses CUAD's question template inside the service: S1 would get a query rewrite that S2 does not, so a strategy comparison would mix two changes, and it fails on any corpus without that template (QASPER in Phase 9). Rewriting the query is a fair experiment, but as its own change applied to every strategy, not as part of what "S1" means.
- **`ts_rank_cd` (cover density), as in Design §7.** Rejected on dev numbers: 4.5 points lower recall@5 and 5.6 points lower MRR@10 than `ts_rank` with the same query. Picking the ranking function on dev is tuning, which `docs/eval-spec.md` §7 puts on dev only; the test split is not used until step 4.8.
- **OR via `plainto_tsquery` with `&` replaced by `|`.** Not chosen: hyphenated words become phrase queries (`'non-compet' <-> 'non' <-> 'compet'`), so "non compete" without the hyphen would not match the compound. The OR over lexemes treats each lexeme as its own term.
- **A GIN index on `tsv`.** Not added: the planner does not use it for per-document queries, so it would only cost write time and disk. Add it if corpus-wide search ever exists.
- **No stored column (`to_tsvector` at query time).** Not chosen: it would make the configuration a one-line change, but would re-parse every chunk of a contract on every query. The stored column follows Design §6.

## Consequences
- Results can state exactly what S1 is: Postgres FTS, `english`, OR over the question's lexemes, `ts_rank`. A comparison "FTS vs dense" is honest about what FTS is, including that it has no IDF: common words such as `contract` and `parti` count as much as rare ones.
- S1 can return fewer than k chunks (500 of 5,458 dev queries get fewer than 10, 13 get none). Recall@k counts the missing rows as misses, which is correct. RRF (step 3.2) must handle a short or empty list from S1.
- The planned demo regression (switching `english` to `simple`, step 8.5) is a deliberate change in two places: a new migration that rebuilds `chunks.tsv` and `FTS_CONFIG`. The integration test fails if only one of them changes.
- Design §7's `websearch_to_tsquery` and `ts_rank_cd` are superseded by this ADR; the design file is left unchanged as the original plan.
- The choice was made on dev, among six variants, while S2 got no comparable tuning. On dev that makes S1 look slightly better than it would on unseen data; the test split (step 4.8) is the fair comparison.
