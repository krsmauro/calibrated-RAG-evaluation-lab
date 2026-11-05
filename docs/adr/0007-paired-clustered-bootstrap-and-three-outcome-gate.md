# ADR 0007: Paired, document-clustered bootstrap and the three-outcome gate

- **Status:** accepted
- **Date:** 2026-11-05
- **Step:** 4.9. It records decisions built in steps 4.1 (bootstrap), 4.3 (gate rule) and 4.4 (`compare` and its guards), checked in 4.2 (coverage, F-003) and 4.6 (subsampling study, F-014), and sized by decision D9. It also records the deviation from Design §8.5 for generator changes that `docs/eval-spec.md` §6.1 assigns to this ADR.

## Context
The gate has to say whether a change makes retrieval worse by a margin worth blocking, and how sure it is. A difference in means cannot say that alone. Two facts about the data shape the method:

- **The values are paired.** Both runs score the same queries, so each query gives one difference, candidate minus baseline.
- **Queries about one contract are correlated.** They share its chunking quirks, formatting and vocabulary. On the stored dev runs the intraclass correlation of per-query differences is 0.021 to 0.053 (step 4.2). Dev has 408 contracts and 5,458 answerable queries, 13.4 a contract on average and at least 2 each.

Retrieval here is deterministic: two runs of one config are identical query by query (step 3.8), so a change that touches nothing gives exactly [0, 0]. The noise the gate must handle is sampling noise: dev's contracts are one draw from the contracts the system could face. A real change also moves many queries up and down at once ("churn"). Swapping one strategy for another changes the recall@5 of a fifth to a quarter of the queries (F-014).

## Decision
1. **Comparison** (`stats/bootstrap.py`). Join per-query values on query id and take candidate minus baseline. Resample contracts with replacement, as many as there are, keeping all their queries. Take the mean over all queries in the resample, so a contract weighs by its number of queries and the estimand is the per-query mean the reports print. Use 10,000 resamples and a percentile 95% interval (numpy's linear interpolation). The seed is 20261104, fixed in `compare` and printed with the report. Contracts are sorted before drawing, so one seed gives one interval whatever order the inputs come in. The two query sets must be identical.
2. **Rule** (`stats/gate.py`), with δ = 0.02:
   - Pass if `lo >= -δ`, with the note "small regression detected" if `hi < 0` as well.
   - Fail if `hi < 0` and `lo < -δ`.
   - Inconclusive otherwise.
3. **One primary metric per kind of change.** Retrieval changes gate on recall@5 (eval-spec §6.1: no candidate metric is saturated on dev, F-004). Every other metric is shown with its interval and never gates.
4. **Guards** (`report/compare.py`):
   - Below 40 contracts the outcome is Inconclusive and no interval is computed (F-003).
   - Two runs with different chunker ids get no outcome until decision D8.
   - Different eval-set hashes or splits are refused unless forced.
   - Different query sets are always refused.
5. **Size.** The pull-request gate runs on all 408 dev contracts (D9).
6. **Generator and prompt changes** (Phases 5 and 8; not built). The primary metric is the end-to-end correct rate over all queries. The faithfulness pass rate over answers that say "present" is a guard metric. Both gate, each at the Holm-Bonferroni corrected level, and δ is 0.05 (provisional). This deviates from Design §8.5, which names the faithfulness pass rate alone. The user approved the change with the spec on 2026-10-19: faithfulness alone can be gamed by a prompt that abstains more often, which removes unfaithful answers from its denominator.

## How the gate was validated
- **Coverage** (step 4.2, F-003; synthetic data with a known true difference, 2,000 simulations of 2,000 resamples each). At dev's correlation, the clustered interval covers 94.6% to 95.2% from 40 contracts up. At 10, 20 and 30 contracts it covers 91.5%, 92.1% and 93.3%, with false Fails of 4.1%, 3.8% and 3.0%. That shortfall sets the 40-contract floor. The query-level interval covers 87% to 89% at every size, with 5.7% to 7.2% false Fails.
- **False alarms on real data** (step 4.6, F-014). The runs were 1,000 stratified subsets per size, from 40 to 408 contracts, drawn from four pairs of stored dev runs whose differences were shifted to a true mean of exactly 0. The clustered gate falsely Fails 2.5% (696 of 28,000; every row between 1.2% and 3.4%). Resampling queries instead falsely Fails 3.7% (S4 against S1, 40 to 100 contracts). This meets Phase 4's exit criterion.
- **Power** (F-014). At a strategy swap's churn, the smallest regression Failed 80% of the time is 0.051 at 60 contracts, 0.025 at 200, 0.021 at 300 and 0.018 at 408. When only the regressed queries change, it is 0.016 to 0.019 at every size from 40. A 2-point regression almost never Passes (2% to 4% of subsets): low power shows up as Inconclusive, not as a false Pass.
- **Method.** Subsets are drawn with replacement within length terciles, as a model of a population of contracts larger than dev. Drawn without replacement, large subsets of a 408-contract set overlap so much that the gate looks quieter and stronger than it is: 0.000 false Fails at 300 contracts. Design §8.5's literal recipe ("random CI-sized subsets") would have reported that.
- **End to end** (step 4.7a, `make gate`). A tree with no service change gives [+0.0000, +0.0000] and Pass. `rrf_k` 10 to 60 gives -0.0070 [-0.0121, -0.0020]: a Pass with "small regression detected". Dense in place of hybrid gives -0.0874 [-0.0973, -0.0775] and Fail.

## Alternatives considered
- **Query-level bootstrap.** Loses: it treats correlated queries as independent and under-covers. False Fails are 3.7% on real dev subsets (a 50% excess) and 5.7% to 7.2% in the simulation. It is kept in the code only to show that difference.
- **Unpaired comparison of the two means.** Loses on principle (Design §8.5): both runs score the same queries, and an unpaired interval counts each query's shared difficulty as noise, so it comes out wider. Not measured.
- **Mean of contract means** (each contract weighed equally). Loses: it changes the estimand from the per-query mean every report prints to a per-contract mean. Step 4.1's tests catch this as a planted bug.
- **BCa, or a t-interval on contract means.** The spec allows BCa only if percentile intervals under-cover. They under-cover only below 40 contracts, where the gate computes no interval. Not measured.
- **Two outcomes** (Fail whenever the interval excludes zero, or a p-value test). Loses: on all of dev it would Fail regressions far too small to block, and on a few contracts it would Pass almost anything. It cannot say "too small to tell". The three-outcome rule also Fails some regressions below δ, by design: 84% of fresh 408-contract samples Fail the real 1.5-point regressions of S1 and S4 against S3.
- **Several gating metrics.** Loses for retrieval: eight metrics at 2.5% each would fail about 18% of harmless changes if independent (Design §8.5). With two generator metrics, Holm-Bonferroni applies (decision 6).
- **The 60-contract CI subset of step 4.5.** Loses: its MDE at a strategy swap's churn is 0.051. It could gate only with δ raised to about 0.05, which lets through regressions three times the S1-to-S3 gap. D9 chose all of dev.
- **Another floor.** 30 contracts under-cover (93.3%, false Fails 3.0%). 60 add margin but would refuse valid smaller comparisons. 40 is where coverage reached the nominal band.

## Consequences
- The gate's error rates are measured, not assumed. Changes with churn but no true effect are falsely Failed 2.5% of the time. A change that alters nothing always Passes, with [0, 0].
- A Fail does not mean the regression is at least δ. It means the change is worse and a regression of δ cannot be ruled out. The report states the interval, so a reader can see how large the regression is.
- Every gate costs two runs on all of dev: about 45 s locally for the default S3 config. A gate on an S4 config would take about 15 minutes, since one S4 run on dev takes about 7.5. CI also has to build the index (ADR 0010).
- The interval treats dev's contracts as a sample of contracts like them. It says nothing about another corpus, or about the test split.
- `compare` with several candidates prints each interval uncorrected. Only one baseline-against-candidate decision is a gate.
- Revisit:
  - when D8 says what gates a chunker change;
  - when the LLM stages arrive, since an A/A study may show run-to-run noise that needs repeats or a variance component (Design §8.5);
  - if dev changes size (rerun `scripts/measure_power.py`, about 18 minutes).
