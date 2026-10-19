# F-004: Per-document retrieval may saturate recall@5

- **Status:** open
- **Date:** 2026-10-19
- **Found by:** Claude, while writing the plan
- **Evidence level:** hypothesis (not checked)
- **Affects:** 1.8, 2.10, 4.6, 8.5; Design §5.1, §8.5

## Finding
Retrieval is filtered to one contract, so the candidate pool is a few hundred chunks. With k = 5 and clauses that often sit in a few chunks, recall@5 might be near 1.0 for all four strategies. A metric with no headroom cannot show a difference, so the gate would have little power on it, and the strategy comparison could end in a four-way tie that says more about the metric than about the strategies. Design §16 accepts "every strategy ties" as a legitimate finding, but only when the metric was capable of separating them.

## Evidence
Not checked. Step 2.10 reports recall at several k from the first baseline run. If recall@5 is above roughly 0.95 for the weakest strategy, headroom is a problem.

## Consequence
If confirmed, choose the primary gating metric and k with headroom (for example recall@1 or @3, MRR, or character-level precision/recall at a small token budget) in `eval-spec.md`, before the power study, and say why. Do this by looking at dev numbers for headroom only, never by choosing the metric on which a favored strategy wins.

## Resolution
