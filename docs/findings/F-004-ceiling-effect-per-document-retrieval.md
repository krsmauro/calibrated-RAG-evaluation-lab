# F-004: Per-document retrieval may saturate recall@5

- **Status:** refuted for S2 (measured 2026-10-28, step 2.10); still to check for S4 in 3.9
- **Date:** 2026-10-19
- **Found by:** Claude, while writing the plan
- **Evidence level:** measured for S2 on CUAD dev; hypothesis for the other strategies
- **Affects:** 1.8, 2.10, 4.6, 8.5; Design §5.1, §8.5

## Finding
Retrieval is filtered to one contract, so the candidate pool is a few hundred chunks. With k = 5 and clauses that often sit in a few chunks, recall@5 might be near 1.0 for all four strategies. A metric with no headroom cannot show a difference, so the gate would have little power on it, and the strategy comparison could end in a four-way tie that says more about the metric than about the strategies. Design §16 accepts "every strategy ties" as a legitimate finding, but only when the metric was capable of separating them.

## Evidence
Not checked. Step 2.10 reports recall at several k from the first baseline run. If recall@5 is above roughly 0.95 for the weakest strategy, headroom is a problem.

## Consequence
If confirmed, choose the primary gating metric and k with headroom (for example recall@1 or @3, MRR, or character-level precision/recall at a small token budget) in `eval-spec.md`, before the power study, and say why. Do this by looking at dev numbers for headroom only, never by choosing the metric on which a favored strategy wins.

## Resolution
Partly addressed in `docs/eval-spec.md` §6.1 and §8 (draft, 2026-10-19): a pre-registered fallback order for the primary retrieval metric, checked on dev only, plus a note that a ceiling mainly hurts strategy comparison and improvement detection, and probably gating less than first written (hypothesis, to be measured in 4.6). Still open until dev numbers exist (step 2.10).

2026-10-28, step 2.10: dense retrieval (S2, chunker C1 at 256 tokens, bge-small-en-v1.5) on all 5,458 answerable dev queries (408 contracts): Hit@1 0.275, @3 0.453, @5 0.550, @10 0.691; recall@1 0.227, @3 0.395, @5 0.489, @10 0.631; MRR@10 0.393. Far from the 0.95 threshold above, so recall@5 has ample headroom for S2. A stronger strategy (S4 with a reranker) could move closer to the ceiling, so the check is repeated on the S1 to S4 numbers in step 3.9 before eval-spec §6.1 picks the primary metric. Command and manifest: `docs/results.md`, first row.
