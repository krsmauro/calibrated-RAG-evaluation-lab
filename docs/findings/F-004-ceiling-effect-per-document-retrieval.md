# F-004: Per-document retrieval may saturate recall@5

- **Status:** refuted for S1 to S4 on C1 (measured: S2 2026-10-28, step 2.10; S1 to S4 2026-11-04, step 3.9)
- **Date:** 2026-10-19
- **Found by:** Claude, while writing the plan
- **Evidence level:** measured for S1 to S4 on CUAD dev, chunker C1
- **Affects:** 1.8, 2.10, 4.6, 8.5; Design §5.1, §8.5

## Finding
Retrieval is filtered to one contract, so the candidate pool is a few hundred chunks. With k = 5 and clauses that often sit in a few chunks, recall@5 might be near 1.0 for all four strategies. A metric with no headroom cannot show a difference, so the gate would have little power on it, and the strategy comparison could end in a four-way tie that says more about the metric than about the strategies. Design §16 accepts "every strategy ties" as a legitimate finding, but only when the metric was capable of separating them.

## Evidence
Not checked. Step 2.10 reports recall at several k from the first baseline run. If recall@5 is above roughly 0.95 for the weakest strategy, headroom is a problem.

## Consequence
If confirmed, choose the primary gating metric and k with headroom (for example recall@1 or @3, MRR, or character-level precision/recall at a small token budget) in `eval-spec.md`, before the power study, and say why. Do this by looking at dev numbers for headroom only, never by choosing the metric on which a favored strategy wins.

## Resolution
Partly addressed in `docs/eval-spec.md` §6.1 and §8 (draft, 2026-10-19): a pre-registered fallback order for the primary retrieval metric, checked on dev only, plus a note that a ceiling mainly hurts strategy comparison and improvement detection, and probably gating less than first written (hypothesis, to be measured in 4.6). Still open until dev numbers exist (step 2.10).

2026-10-28, step 2.10: dense retrieval (S2, chunker C1 at 256 tokens, bge-small-en-v1.5) on all 5,458 answerable dev queries (408 contracts): Hit@1 0.275, @3 0.453, @5 0.550, @10 0.691; recall@1 0.227, @3 0.395, @5 0.488, @10 0.631; MRR@10 0.393. Far from the 0.95 threshold above, so recall@5 has ample headroom for S2. A stronger strategy (S4 with a reranker) could move closer to the ceiling, so the check is repeated on the S1 to S4 numbers in step 3.9 before eval-spec §6.1 picks the primary metric. Command and manifest: `docs/results.md`, first row.

2026-10-28, step 3.1: S1 (Postgres FTS) on the same queries: recall@5 0.560, MRR@10 0.455 (`docs/results.md`, S1 row). Also far from 0.95. The check on S3 and S4 remains for step 3.9.

2026-11-04, step 3.9: all four strategies on chunker C1, rerun through the run store on a clean commit (4bad31f; run ids in `docs/results.md`, row "recall@k and MRR per strategy S1 to S4, CUAD dev"): recall@5 S1 0.560, S2 0.488, S3 0.576, S4 0.561; recall@10 at most 0.704 (S3 and S4); MRR@10 at most 0.477 (S3). The strongest strategy is about 0.37 below the 0.95 threshold at k = 5, so recall@5 has headroom for every strategy. The reranker did not move toward the ceiling: with CUAD's templated question it scores below S3 (F-012). This does not settle power on a CI-sized subset, which step 4.6 measures.

2026-11-05, step 4.6 (F-014): power on a CI-sized subset measured. Recall@5 (0.49 to 0.58) has room both ways, and the gate's power is limited by how many queries a change reshuffles (about a quarter for a strategy swap), not by a ceiling. A seeded 2-point drop with no other change is detected in 93% to 98% of subsets at any size from 40 contracts; with a strategy swap's noise it needs all 408 dev contracts. No other primary metric or k is needed.
