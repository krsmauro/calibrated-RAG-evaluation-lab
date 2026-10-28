# Results ledger

The only place measured headline numbers are recorded. A number belongs here only if one command regenerates it. A number that cannot be reproduced is deleted, not softened. Do not copy a number into the README, a résumé or a pitch until its row is `final`.

Mirrors Design §14. Status: `empty` (nothing yet), `provisional` (dev data or pre-freeze config), `final` (frozen config, reproduced from a clean checkout).

| Result | Status | Value (with 95% CI and n) | Command | Run id / manifest | Date | Step |
| --- | --- | --- | --- | --- | --- | --- |
| recall@k and MRR per strategy S1 to S4, CUAD dev | empty | | | | | 2.10, 3.9 |
| S2 dense (bge-small-en-v1.5, C1 256/32), CUAD dev, answerable queries | provisional | recall@1 0.227, @3 0.395, **@5 0.488**, @10 0.631; Hit@5 0.550, Hit@10 0.691; **MRR@10 0.393**. n = 5,458 queries, 408 documents. 95% CI: not yet (document-clustered bootstrap is step 4.1). Per category: in the run JSON | `make up && make ingest && make serve`, then `uv run ragcalibrate run` | git b0b3aea (clean tree), evalset 34987d1bf1ea. Same summary as the two earlier runs on 014cd8c plus then-uncommitted changes, which were identical to each other per query. Recall@5 corrected on 2026-10-28 from 0.489: the exact mean is 0.48846, which had been rounded twice (0.4885, then 0.489); no other value in this row or the S1 row was affected | 2026-10-28 | 2.10 |
| S1 Postgres FTS (`english`, OR over the question's lexemes, `ts_rank`; ADR 0009), C1 256/32, CUAD dev, answerable queries | provisional | recall@1 0.274, @3 0.457, **@5 0.560**, @10 0.697; Hit@5 0.627, Hit@10 0.754; **MRR@10 0.455**. n = 5,458 queries, 408 documents; 500 queries get fewer than 10 chunks, 13 get none. 95% CI: not yet (step 4.1). Query construction and ranking function chosen on dev (ADR 0009), so somewhat optimistic; S1 vs S2: finding F-011. Per category: in the run JSON | `make up && make ingest && make serve`, then `uv run ragcalibrate run --strategy fts` | git 8875b32 (clean tree), evalset 34987d1bf1ea. Per-query rankings and scores identical to the two earlier runs on b5b075c plus the then-uncommitted step 3.1 changes | 2026-10-28 | 3.1 |
| S3 hybrid: RRF over S1 and S2 (`rrf_k` 10, `fusion_depth` 100), C1 256/32, CUAD dev, answerable queries | provisional | recall@1 0.293, @3 0.484, **@5 0.576**, @10 0.704; Hit@5 0.641, Hit@10 0.758; **MRR@10 0.477**. n = 5,458 queries, 408 documents. Paired with S1 on recall@5: better on 583 queries, worse on 446, tied on 4,429; above S1 in 21 of 41 categories, below in 19, below both S1 and S2 in none. Both fusion parameters chosen on dev, the best of 30 settings (`scripts/measure_rrf.py`), so somewhat optimistic; the usual `rrf_k` 60 at the same depth gives recall@5 0.569, MRR@10 0.474. 95% CI: not yet (step 4.1). Per category: in the run JSON; discussion in finding F-011 | `make up && make ingest && make serve`, then `uv run ragcalibrate run --strategy hybrid` | git 8875b32 plus the uncommitted step 3.2 changes (dirty tree), evalset 34987d1bf1ea; two runs gave identical rankings, and per query they equal the offline fusion in `scripts/measure_rrf.py`. Rerun on the clean commit and repoint this row | 2026-10-28 | 3.2 |
| recall@k and MRR per strategy S1 to S4, CUAD test | empty | | | | | 4.8, 9.4 |
| S2 embedding-model comparison, bge-small-en-v1.5 vs text-embedding-3-small, CUAD dev (delta with 95% CI and n, per category, latency, cost) | empty | | | | | 4.10 |
| Character precision/recall at a token budget, per chunker | empty | | | | | 3.9 |
| Rerank latency cost vs quality gain | empty | | | | | 3.3 |
| Presence accuracy, abstention precision and recall, citation precision | empty | | | | | 5.8 |
| Judge κ vs blind human labels, per criterion | empty | | | | | 7.2 |
| Judge intra-rater (human) κ and judge repeat consistency | empty | | | | | 7.2 |
| Bias effects: position flip rate, verbosity shift, citation trust | empty | | | | | 7.4 |
| One mitigation, before and after | empty | | | | | 7.5 |
| Gate false-alarm rate, retrieval (subsampling): query-level vs cluster-level | empty | | | | | 4.6 |
| Gate false-alarm rate, LLM stages (A/A, cache off) | empty | | | | | 7.6 |
| Minimum detectable recall drop at 80% power on the CI subset | empty | | | | | 4.6 |
| Cost per full run (cold and warm) and per CI run | empty | | | | | 5.8, 8.8 |
| p95 latency: `/retrieve` per strategy, `/answer` end to end | empty | | | | | 8.7 |
| Headline table repeated on QASPER | empty | | | | | 9.3 |
