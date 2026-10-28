# F-012: cross-encoder rerank (S4) lowers recall on CUAD's templated questions, and raises it on the question alone

- **Status:** confirmed on dev (provisional: no confidence interval yet, test split not run)
- **Date:** 2026-10-28
- **Found by:** Claude, plan step 3.3
- **Evidence level:** measured (commands and output below)
- **Affects:** 3.3, 3.9, 4.x (strategy table), 8.5 (demo PR A), `docs/eval-spec.md` §1 (query text), README step 6; Design §7

## Finding
S4 as specified, S3's top N rescored by a local cross-encoder (`ms-marco-MiniLM-L6-v2`, ADR 0013) with the CUAD question as sent, **lowers** recall@5 on all 5,458 answerable dev queries: S3 scores 0.576; S4 scores 0.561 at the top 10 (-1.5 points), 0.557 at the top 20 and 0.558 at the top 30, and MRR@10 falls from 0.477 to 0.471, 0.474 and 0.471. Paired per query at the top 10, S4 is better than S3 on 457 queries and worse on 583. Design §7 expected S4 to be the quality ceiling. Two larger cross-encoders do no better on a 300-query sample (ADR 0013: mxbai-rerank-xsmall-v1 -2.0 and -3.4 points at the top 10 and 20, bge-reranker-base -6.7 and -8.8). The same model, given only the specific part of the question (the text after "Details:") instead of the whole template, **raises** recall@5 on all of dev from 0.576 to 0.621 at the top 10 (+4.5 points) and 0.662 at the top 20 (+8.6; better on 938 queries, worse on 450), above S3 in 30 of 41 categories. On a 300-query pilot, giving it only the category name did about as well (+8.8 at the top 20).

## Evidence
- **Full dev, question as sent:** `uv run python scripts/measure_rerank.py tune --depths 10 20 30` (needs `make serve`): S3's top 30 for every answerable dev query, reranked offline with the service's `Reranker` and `rerank`. Recall@5 and MRR@10 on 5,458 queries, 408 contracts; better and worse are per query on recall@5 against S3:

  | | recall@5 | Hit@5 | recall@10 | MRR@10 | better | worse |
  | --- | --- | --- | --- | --- | --- | --- |
  | S3 hybrid | 0.576 | 0.641 | 0.704 | 0.477 | | |
  | S4, top 10 | 0.561 | 0.623 | 0.704 | 0.471 | 457 | 583 |
  | S4, top 20 | 0.557 | 0.620 | 0.702 | 0.474 | 609 | 790 |
  | S4, top 30 | 0.558 | 0.621 | 0.694 | 0.471 | 649 | 837 |

  At the top 10, S4 is above S3 in 17 of 41 categories and below in 24 (at the top 30: 12 above, 27 below). It helps most on the front-matter categories, the hardest for every strategy so far (F-008), and keeps helping there as it reranks deeper: Agreement Date 0.322 to 0.463 (n = 377; 0.645 at the top 30), Effective Date 0.500 to 0.622 (n = 320; 0.738), Parties 0.155 to 0.190 (n = 407; 0.249). It hurts most on clause categories, and more the deeper it goes: Covenant Not To Sue 0.465 to 0.236 (n = 76), Most Favored Nation 0.580 to 0.373 (n = 25), Revenue/Profit Sharing 0.474 to 0.312 (n = 131), Minimum Commitment 0.452 to 0.323 (n = 133), Warranty Duration 0.720 to 0.579 (n = 65), Termination For Convenience 0.852 to 0.742 (n = 154), Expiration Date 0.828 to 0.720 (n = 335). The 300-query pilot below put the loss at the top 10 at 2.5 points; on all of dev it is 1.5.
- **Three models, 300 queries:** the same sample (seed 33, 216 contracts), S3's top 10 and 20 reranked by each model through one ONNX scoring path that reproduces MiniLM's numbers from `measure_rerank.py` exactly; table in ADR 0013. Pilot scripts in the session scratchpad, not committed.
- **Question alone (diagnostic only, not a strategy):** `uv run python scripts/measure_rerank.py tune --depths 10 20 --question details` (or `category`; `--sample 300` for the pilot sample). S3's candidates still come from the whole question; only the reranker sees part of it, cut in the script, never in the service. All of dev, 5,458 queries:

  | Reranker given | Top 10: recall@5, MRR@10, change, better / worse | Top 20: recall@5, MRR@10, change, better / worse |
  | --- | --- | --- |
  | Whole template (as sent, S4) | 0.561, 0.471, -1.5, 457 / 583 | 0.557, 0.474, -1.9, 609 / 790 |
  | Text after "Details:" | 0.621, 0.528, +4.5, 619 / 355 | 0.662, 0.552, +8.6, 938 / 450 |

  With the "Details" text at the top 20, S4 is above S3 in 30 of 41 categories and below in 11. The front-matter categories gain most (Effective Date 0.500 to 0.820, Agreement Date 0.322 to 0.715, Document Name 0.206 to 0.504, Parties 0.155 to 0.329), and some clause categories still lose (Non-Transferable License 0.618 to 0.347, n = 116; Revenue/Profit Sharing 0.474 to 0.329, n = 131; Most Favored Nation 0.580 to 0.307, n = 25). The 300-query pilot (seed 33), S3 alone at recall@5 0.587, MRR@10 0.482, with the category name as a third form:

  | Query given to the reranker | Top 10: recall@5, MRR@10, change | Top 20: recall@5, MRR@10, change |
  | --- | --- | --- |
  | Whole template (as sent, S4) | 0.563, 0.451, -2.5 | 0.563, 0.453, -2.4 |
  | Text after "Details:" | 0.625, 0.540, +3.8 | 0.691, 0.566, +10.4 |
  | Category name only | 0.641, 0.577, +5.4 | 0.675, 0.596, +8.8 |

- **Scores:** on 197 dev pairs with the whole template every logit is negative (-11.0 to -2.0), including the governing-law clause for the governing-law question (-4.15 in the unit test's fixture). A hypothesis, not checked: the boilerplate ("Highlight the parts (if any) of this contract related to ... that should be reviewed by a lawyer") looks to a model trained on short MS MARCO search queries like a request no passage answers, so every chunk scores "irrelevant" and small differences decide the order. The date categories, whose "Details" are short ("The date of the contract"), are where S4 helps most even with the template (full dev, top 10: Agreement Date 0.322 to 0.463, Effective Date 0.500 to 0.622), which fits the hypothesis but does not test it.

## Consequence
- **3.3:** done as specified: the question goes to the reranker as sent. S4 is a measured regression; its latency cost is in `docs/results.md`.
- **Decision for the user (D7 in the plan):** whether a CUAD query's text should be the question a user would ask (the "Details" part, perhaps with the category name) instead of CUAD's template. It would have to change in the eval set, for every strategy, never in the service: a service that strips CUAD's template knows the benchmark, and the README (step 6) already rejects that for S1. Costs: `docs/eval-spec.md` §1 amended, a new eval-set hash, S1 to S4 rerun, S1's query construction and S3's fusion parameters re-checked on the new text. Caveat: the motivation came from looking at dev results; if adopted, the spec and the README must say so and when, and the test split must stay untouched. Until the user decides, nothing changes.
- **3.9 and 4.x:** S4 goes into the strategy table as measured, below S3.
- **8.5 (demo PR A):** "add a cross-encoder reranker" is a tidy change a reviewer would approve that lowers recall@5; a candidate for the seeded regression, to be measured on the CI subset first as the step says.
- **F-004 (ceiling):** S4 is further from a ceiling than S3.

## Resolution
