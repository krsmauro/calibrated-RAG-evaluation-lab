# F-002: A full templated question may match almost nothing under websearch_to_tsquery

- **Status:** resolved (confirmed, then fixed in step 3.1)
- **Date:** 2026-10-19
- **Found by:** Claude, while writing the plan
- **Evidence level:** measured (2026-10-28, step 3.1; was a hypothesis)
- **Affects:** 3.1, 3.9; Design §7 (S1), §5.9

## Finding
Design §7 specifies S1 as `websearch_to_tsquery` with `ts_rank_cd`. As I understand Postgres, `websearch_to_tsquery` combines unquoted words with AND, and CUAD queries are long templated sentences ("Highlight the parts (if any) of this contract related to ..."). An AND over all of those terms could return few or no chunks, which would make S1 look much worse than lexical retrieval really is and distort every comparison with S2 to S4.

## Evidence
Originally not checked; the check proposed was to run S1 on dev and count queries that return fewer than k rows, for the plain approach and for alternatives.

Measured 2026-10-28 with `uv run python scripts/measure_fts.py` (5,458 answerable dev queries, 408 contracts, C1 chunks, `english`, k = 10). `websearch_to_tsquery` on the full question: 94.8% of queries get fewer rows than the contract could give, **84.0% get no rows at all**, recall@5 0.048. An OR over the question's lexemes: 7.4% short, 0.2% empty, recall@5 0.515 with `ts_rank_cd` and 0.560 with `ts_rank`. The full table, with the template-stripping and category-only variants, is in ADR 0009. The hypothesis was right, and the effect was larger than feared: as written in Design §7, S1 would have been almost useless.

## Consequence
If confirmed, S1's query construction becomes a documented decision (ADR 0009) and part of what "S1" means in the results table. Whatever is chosen must be tuned on dev only, and must not use gold information.

## Resolution
2026-10-28, step 3.1: S1 builds an OR over the distinct lexemes of the whole question and ranks with `ts_rank` (ADR 0009, `FTS_SQL` in `service/retrieval.py`). It uses no CUAD-specific rewriting and no gold information, and was chosen on dev only. With it, S1 beats S2 on dev (finding F-011). Step 3.9 still compares S1 to S4 per category.
