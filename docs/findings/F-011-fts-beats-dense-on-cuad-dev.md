# F-011: lexical search (S1) beats dense search (S2) on CUAD dev

- **Status:** confirmed on dev (provisional: no confidence interval yet, test split not run)
- **Date:** 2026-10-28
- **Found by:** Claude, plan step 3.1
- **Evidence level:** measured (commands and output below)
- **Affects:** 3.2, 3.3, 3.9, 4.10, 8.5; Design §7

## Finding
On all 5,458 answerable dev queries (408 contracts, chunker C1), S1 (Postgres FTS, ADR 0009) scores recall@5 **0.560** against S2's **0.488** (+7.2 points), and MRR@10 0.455 against 0.393. Paired per query, S1 has the higher recall@5 on 1,137 queries, the lower on 689, and ties on 3,632. S1 is ahead in 29 of 41 categories. The biggest gains are where exact legal terms decide relevance: Non-Transferable License 0.699 vs 0.283 (n = 116), Irrevocable Or Perpetual License 0.846 vs 0.423 (n = 57), License Grant 0.500 vs 0.288 (n = 205), Governing Law 0.939 vs 0.758 (n = 354). S2 is ahead where clauses tend to paraphrase the question: Insurance 0.619 vs 0.795 (n = 134), Revenue/Profit Sharing 0.360 vs 0.489 (n = 131), Liquidated Damages 0.418 vs 0.518 (n = 47), No-Solicit Of Employees 0.724 vs 0.823 (n = 49), Termination For Convenience 0.773 vs 0.843 (n = 154).

## Evidence
Both runs on git b5b075c plus the uncommitted step 3.1 changes, evalset 34987d1bf1ea, same service: `uv run ragcalibrate run --strategy fts` and `uv run ragcalibrate run --strategy dense` (written to the gitignored `runs/s1-fts-dev-3.1.json` and `runs/s2-dense-dev-3.1-check.json`). The S2 run's per-query rankings are identical to the committed baseline run (b0b3aea), so the step 3.1 changes did not move S2. Per-category and per-query numbers come from comparing the two run files.

Two things limit how much this says:
- **No confidence interval.** The document-clustered bootstrap is step 4.1. With 408 clusters and a 7-point gap the sign is unlikely to flip, but that is a judgment, not a measurement.
- **S1 was tuned on dev, S2 was not.** S1's ranking function (`ts_rank` over `ts_rank_cd`) was chosen among six variants on these same queries. The untuned variant (`ts_rank_cd`, recall@5 0.515) also beats S2, so the sign does not rest on that choice, but the size is somewhat optimistic for S1.

A hypothesis, not checked: the CUAD question template ("Highlight the parts (if any) of this contract related to ... that should be reviewed by a lawyer") may hurt the embedding more than the lexical match, because in an OR query the template words add roughly the same score to every chunk, while in a 384-dimension embedding they are mixed into the whole vector.

## Consequence
- **3.2, 3.3:** hybrid (S3) and rerank (S4) should be read against S1, the strongest single strategy so far, not only against S2. A hybrid that only matches S1 is not a gain.
  - Note (2026-10-28, measured in step 3.2): S3 (RRF, `rrf_k` 10, depth 100, both chosen on dev) reaches recall@5 **0.576**, only 1.6 points above S1 (0.560; MRR@10 0.477 vs 0.455). At the usual `rrf_k` 60 the gain is 0.9 points. Per query on recall@5, S3 is better than S1 on 583, worse on 446. The small net gain hides two larger movements that cancel: fusion recovers most of S2's lead where clauses paraphrase the question (Insurance 0.813, against S1 0.619 and S2 0.795; Revenue/Profit Sharing 0.474, against 0.360 and 0.489; Warranty Duration 0.720, above both) and gives back part of S1's lead where exact legal terms decide (Irrevocable Or Perpetual License 0.676, against S1 0.846 and S2 0.423; Non-Transferable License 0.618, against 0.699 and 0.283). S3 is above S1 in 21 of 41 categories, below in 19, and below both S1 and S2 in none. Consequences: S4 (3.3) must be read against S3 and S1; with no CI yet, a 1.6-point gain may not be distinguishable from zero (step 4.1 decides). Weighted fusion, which could keep more of S1's lead, is Design §7's optional ablation and is on the cut list (Design §11), so it is not planned.
- **3.9:** this is the "S1 beating S2" case the step anticipated; report it per category as above, with the tuning caveat.
- **4.10 (embedding-model comparison):** the interesting question becomes whether a stronger embedder closes the gap to FTS; keep S1 in that table as a reference row.
- **8.5 (demo regression):** S1 relies on exact terms, and stemming is part of that, so switching `english` to `simple` is likely to move S1's metric. The step still has to measure it on the CI subset.
- **F-004 (ceiling):** S1's recall@5 of 0.560 is far from the 0.95 threshold too.
- **README and claims:** nothing to publish until the test split (4.8) and a confidence interval exist.

## Resolution
