# Phase 4: Paired cluster bootstrap and the retrieval-only gate (Design Week 4)

**Goal:** the headline feature in a cheap, deterministic form. After this phase a credible project exists even if later phases slip.
**Entry:** Phase 3 done (stored runs for S1 to S4).
**Exit criterion:** bootstrap coverage test passes; the clustered false-alarm rate is close to nominal.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 4.1 [ ] Paired cluster bootstrap
- **Do:** `stats/bootstrap.py`, pure functions, seeded RNG, no I/O. Input: per-query metric values for candidate and baseline, joined on `query_id`, with a cluster label (`document_id`). Resample clusters, take all queries of each sampled cluster, compute the mean paired difference. Percentile CI, 10,000 resamples by default. Seed is returned with the result. Use numpy (already needed); no new dependency.
- **Verify:** known-answer tests on tiny hand-computed inputs (for example two clusters, where the bootstrap distribution is enumerable); same seed gives the same CI; unpaired or mismatched query sets raise.
- **Refs:** Design §8.5; skill EVAL-CRITICAL-3.

#### 4.2 [ ] Coverage test on synthetic data
- **Do:** simulate data with a known true delta and within-cluster correlation. Check that about 95 percent of 95 percent intervals contain the truth for the cluster bootstrap, and show that the query-level bootstrap under-covers when clusters are correlated. Run it for several cluster counts, **including small ones** (about 20 to 40 contracts), because percentile bootstraps can under-cover with few clusters.
- **Verify:** test asserts coverage within a tolerance band computed from the number of simulations; the small-cluster result is recorded in a finding. If coverage is poor at the planned CI-subset size, record it and escalate (options: larger subset, BCa intervals, a t-based interval). Do not proceed on a silent shortfall.
- **Refs:** Design §8.5; finding F-003.

#### 4.3 [ ] Gate decision function
- **Do:** `stats/gate.py`: given `[lo, hi]` and δ, return Pass, Fail or Inconclusive per the rule in Design §8.5, including the "small regression detected" note. Holm-Bonferroni helper only if more than one metric gates (default: one primary metric).
- **Verify:** property tests on every boundary (`lo == -δ`, `hi == 0`); exhaustive table test of the three outcomes.
- **Refs:** Design §8.5.

#### 4.4 [ ] `rageval compare` and the first report
- **Do:** compare two stored runs, output a Markdown table (metric, baseline, candidate, delta, CI, outcome, n queries, n documents) and an HTML report. Secondary metrics are shown but never gate.
- **Verify:** the strategy comparison table on dev for S1 to S4 regenerates from one command. Every number shows its n.
- **Refs:** Design §8.5, §14.

#### 4.5 [ ] Fixed CI subset
- **Do:** a fixed, stratified sample of dev contracts, written to a hashed file in `evalsets/`. Size is **provisional** until 4.6 produces the power curve; make it easy to regenerate at another size.
- **Verify:** reproducible from a seed; no overlap with test.
- **Refs:** Design §8.1.

#### 4.6 [ ] Subsampling study: false alarms, power, MDE
- **Do:** treat all of dev as the population, run each configuration once on all of dev, then draw 1,000 random CI-sized subsets of contracts and apply the gate to each using only stored results.
  1. False-alarm rate for two configurations with about zero full-dev delta, with query-level and cluster-level resampling side by side.
  2. Power: seed regressions of known size (for example drop the relevant chunks from the top k on a random p percent of queries) and plot the share of subsets that Fail against the size. Read off the minimum detectable effect.
  3. Use the power curve to set the CI-subset size and δ. The size comes from this, not from a guess.
- **Verify:** script plus output committed (or regenerable by one command); numbers in `docs/results.md`; a finding states the chosen subset size and δ with the evidence. Watch for ceiling effects (F-004): if recall@5 is near 1.0, power on it will be poor and another primary metric or k may be needed.
- **Refs:** Design §8.5; findings F-003, F-004.

#### 4.7 [ ] Retrieval-only GitHub Action
- **Do:** composite action in `action/`: bring up the stack, run the CI subset for candidate and baseline, compare, post or update one sticky PR comment, set the exit code (fail on Fail; neutral on Inconclusive). Baseline for retrieval is recomputed at the merge base in the same job. Least-privilege permissions; no secrets needed for this stage; never `pull_request_target`.
- **Verify:** runs end to end on a test PR (the user pushes; mark `[!]` blocked-on-user until confirmed); the comment updates rather than duplicating.
- **Refs:** Design §8.5 (baseline management, fork PRs, PR comment), §12 (ADR 10).

#### 4.8 [ ] Freeze retrieval configs and run CUAD test once (needs user go-ahead)
- **Do:** only when the user says the retrieval configs are final: freeze them (config hashes in the plan), run the test split once per final config, record in `docs/results.md`. Never tune after seeing test numbers.
- **Verify:** `docs/results.md` rows reference run IDs; a finding records which configs were frozen and when.
- **Refs:** Design §8.1.

#### 4.9 [ ] ADRs and skill reference
- **Do:** ADR 0004 (span-overlap relevance and token-budget metrics), 0007 (paired clustered bootstrap and the three-outcome gate), 0010 (baseline management). Write `references/eval/stats-rules.md`.
- **Verify:** ADR index in the plan updated; the reference file exists.
