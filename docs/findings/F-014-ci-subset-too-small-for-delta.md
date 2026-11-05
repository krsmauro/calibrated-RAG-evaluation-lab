# F-014: the gate holds its false-alarm rate, but 60 contracts cannot detect a 2-point regression

- **Status:** resolved (D9 answered 2026-11-05: the retrieval gate runs on all of dev, δ stays 0.02)
- **Date:** 2026-11-05
- **Found by:** Claude (Opus 5.5, VS Code session), plan step 4.6
- **Evidence level:** measured (command and output below), on subsets of CUAD dev drawn from the stored S1 to S4 runs
- **Affects:** 4.6, 4.7, 4.9 (ADR 0007), 8.x (demo PRs); `docs/eval-spec.md` §6.3, §6.4, §7; Design §8.5; F-003, F-004

## Finding
On random subsets of CUAD dev, the paired, document-clustered gate falsely Fails a change with a true difference of zero 2.5% of the time, as it claims: 696 of 28,000 subsets (4 pairs of runs, 7 sizes from 40 to 408 contracts, 1,000 subsets each), every row between 1.2% and 3.4%. Resampling single queries instead falsely Fails 3.7%. The power side is the problem. When a change reshuffles results the way swapping retrieval strategies does (about a quarter of queries change their recall@5), the smallest regression the gate Fails 80% of the time is 0.051 at the CI subset's 60 contracts, 0.025 at 200, 0.021 at 300 and 0.018 on all 408 dev contracts. Only all of dev gets below δ = 0.02. At 60 contracts the gate calls 70% of harmless strategy-sized changes and 74% of 2-point regressions Inconclusive. A change that only hurts, touching nothing else, is easy: 40 contracts detect a regression of 0.016.

## Evidence
`uv run python scripts/measure_power.py` (seed 20261105, 1,000 subsets per row, 10,000 resamples per interval as in `compare`, δ 0.02 on recall@5; 18 minutes on an Apple M5). It reads the S1 to S4 dev runs of `docs/results.md` (chunker C1 at 256, git 4bad31f: 5,458 answerable queries, 408 contracts, 13.4 queries each) and the CUAD zip for contract lengths. Code: `ragcalibrate.stats.subsampling`.

**How a subset is drawn.** Like the CI subset, a third from each length tercile, but with replacement within the tercile: a model of a population of contracts larger than dev. Drawn without replacement, large subsets of only 408 contracts overlap so much that they vary less than new contracts would, and the gate looks quieter than it is. The table below shows this. A contract drawn twice counts as two clusters.

**False alarms.** Each pair's per-query differences are shifted by their mean on all of dev, so the true difference is exactly 0 while every query keeps its real noise. S4 against S1 is the pair whose dev difference is already about zero (+0.0005), as the step asks; the three other pairs are other kinds of churn. Share of subsets whose interval lies wholly below 0, a false Fail (nominal 0.025), with its 95% Wilson interval where it matters:

| Contracts | S4 - S1 (25% of queries differ) | S1 - S3 (19%) | S4 - S3 (19%) | S2 - S3 (20%) | S4 - S1, without replacement | S4 - S1, query-level |
| --- | --- | --- | --- | --- | --- | --- |
| 40 | 0.025 | 0.028 | 0.031 | 0.024 | 0.018 | 0.037 [0.027, 0.051] |
| 60 | 0.019 | 0.029 | 0.031 | 0.024 | 0.025 | 0.037 [0.027, 0.051] |
| 100 | 0.023 | 0.021 | 0.033 | 0.027 | 0.013 | 0.037 [0.027, 0.051] |
| 150 | 0.031 | 0.030 | 0.030 | 0.015 | 0.007 | not run |
| 200 | 0.027 | 0.021 | 0.034 | 0.022 | 0.004 | not run |
| 300 | 0.025 | 0.023 | 0.022 | 0.025 | 0.000 [0.000, 0.004] | not run |
| 408 | 0.019 | 0.024 | 0.012 | 0.021 | (every draw is all of dev) | not run |

The Wilson interval of a clustered row (1,000 subsets) is about ±0.01. Twenty-six of the 28 clustered rows hold 0.025; the other two lie below it (0.012 and 0.015), on the safe side. The other tail, an interval wholly above 0, is 0.027 pooled (0.017 to 0.038 by row). Counting both tails, the clustered interval misses the truth 5.0% to 6.2% of the time at 40 and 60 contracts, close to F-003's synthetic 94.9% to 95.2% coverage. Resampling queries misses it 8.1% to 8.9% of the time (S4 - S1, 40 to 100 contracts): 3.7% false Fails and 4.4% to 5.2% wholly above zero, against the clustered 1.9% to 2.5% and 3.3%. That is less inflation than F-003's synthetic data showed (5.7% to 7.2%), because dev's within-contract correlation is low, but it is still a 50% excess.

**Power.** A regression of known size: recall@5 set to 0 on random queries ("the relevant chunks fell out of the top 5") until the dev mean has fallen by the drop. It is put on top of two kinds of noise. "Strategy swap" is S4 with the drop against S1, shifted as above: the noise of the changes the gate is for, such as swapping a strategy, model or chunker, with about a quarter of queries changing. "None" is S3 with the drop against S3, where only the dropped queries change. Share of subsets that Fail, strategy-swap noise:

| Contracts | drop 0.010 | 0.015 | 0.020 | 0.025 | 0.030 | 0.040 | 0.060 | MDE (80% Fail) | Pass at drop 0 | Inconclusive at drop 0.02 | MDE, no noise |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 40 | 0.069 | 0.112 | 0.158 | 0.221 | 0.310 | 0.478 | 0.799 | above 0.06 | 0.21 | 0.81 | 0.016 |
| 60 | 0.079 | 0.143 | 0.227 | 0.307 | 0.424 | 0.656 | 0.918 | 0.051 | 0.28 | 0.74 | 0.016 |
| 100 | 0.110 | 0.212 | 0.345 | 0.468 | 0.645 | 0.839 | 0.989 | 0.038 | 0.39 | 0.62 | 0.017 |
| 150 | 0.160 | 0.301 | 0.482 | 0.662 | 0.833 | 0.965 | 1.000 | 0.029 | 0.51 | 0.50 | 0.018 |
| 200 | 0.213 | 0.431 | 0.636 | 0.796 | 0.916 | 0.990 | 1.000 | 0.025 | 0.60 | 0.34 | 0.018 |
| 300 | 0.309 | 0.559 | 0.772 | 0.909 | 0.980 | 0.999 | 1.000 | 0.021 | 0.79 | 0.21 | 0.019 |
| 408 | 0.377 | 0.676 | 0.893 | 0.973 | 0.999 | 1.000 | 1.000 | 0.018 | 0.90 | 0.08 | 0.019 |

The realized drops on all of dev are within 0.0002 of the nominal ones. At drop 0 the gate Fails 1.9% to 3.1% of subsets (the false-alarm rate again) and passes the rest or calls them Inconclusive. A 2-point regression almost never Passes (2% to 4% at every size), which is the gate's guarantee: low power shows up as Inconclusive, not as a false Pass. The exception is no noise at 40 contracts, where it Passes 7%. A few large losses among zeros is the skewed case where a percentile interval on few clusters comes out too narrow (F-003). With no noise the gate Fails a 2-point regression 93% to 98% of the time at every size. In that case the MDE creeps up with size toward δ, because a big sample can rule out δ for a regression smaller than δ, and then the gate passes it with "small regression detected".

**Real regressions**, S1 and S4 against S3 as stored (dev deltas -0.0158 and -0.0152, below δ), and S2 against S3 (-0.0874). Share Pass / Inconclusive / Fail:

| Contracts | S1 - S3 | S4 - S3 | S2 - S3 |
| --- | --- | --- | --- |
| 60 | 0.05 / 0.73 / 0.22 | 0.07 / 0.70 / 0.23 | 0 / 0 / 1.00 |
| 200 | 0.08 / 0.40 / 0.52 | 0.10 / 0.29 / 0.61 | 0 / 0 / 1.00 |
| 300 | 0.09 / 0.18 / 0.72 | 0.12 / 0.09 / 0.79 | 0 / 0 / 1.00 |
| 408 | 0.12 / 0.05 / 0.84 | 0.16 / 0.00 / 0.84 | 0 / 0 / 1.00 |

Every size in the script's output (40 to 408) shows the same pattern. Both real 1.5-point regressions behave like the seeded curve, slightly better, because their noise is a little lower than S4 against S1's (dev interval half-widths 0.0105 and 0.0094 against 0.0122). Eval-spec §6.4's observation is confirmed: Fail does not need the regression to reach δ. On all of dev the gate Fails 84% of these 1.5-point regressions, and with no noise it Fails a 1-point regression 41% of the time at 40 contracts.

Recall@5 is not near a ceiling (0.49 to 0.58, F-004). Power is limited by how many queries a change reshuffles, not by saturation.

## Consequence
- **False alarms: Phase 4's exit criterion holds.** The clustered false-alarm rate is close to nominal on real dev subsets from 40 to 408 contracts. The query-level bootstrap must not gate (F-003, confirmed on real data). The 40-contract minimum in `compare` stands.
- **Size and δ, by the rule in eval-spec §6.3** (δ chosen first; if the MDE is above δ, enlarge the subset, and only then raise δ). At strategy-swap noise, no stratified subset smaller than all of dev reaches δ = 0.02 (300 contracts: MDE 0.021, 77% Fail at δ). The rule therefore gives **all 408 dev contracts, δ unchanged at 0.02**: MDE 0.018, false Fail 1.2% to 2.4%, and 90% of harmless strategy-sized changes Pass. The CI gate would run the full dev set, and the 60-contract subset of step 4.5 would not gate.
- **Why this needs the user (D9).** It changes step 4.7's scope. CI would ingest 408 contracts instead of 60, about 80% of the corpus: about 6 minutes on an Apple M5 locally, longer on a GitHub runner unless embeddings are cached. An S4 run on all of dev takes about 7.5 minutes locally. The alternatives are 300 contracts (borderline MDE 0.021, about a quarter less CI time), or a small subset with δ raised to its MDE (0.05 at 60), which would let through regressions three times the size of the S1-to-S3 gap. Choosing the strategy-swap noise as the yardstick is also a judgment call: a change that alters only a few queries is detected at 40 contracts. Until D9 is answered, `CI_SIZE` stays 60 and nothing is regenerated.
- **Method note for ADR 0007 (4.9):** a subsampling study on a finite dev set must draw with replacement, or it understates false alarms and overstates power at large subset sizes. The design's literal version (random subsets of dev) would have reported 0 false Fails and near-perfect Passes at 300 contracts.

## Resolution
2026-11-05: the user accepted the recommendation (D9): the retrieval gate runs on all 408 dev contracts, and δ stays 0.02. Applied in `docs/eval-spec.md` §6.3, §6.4 and §7. The gate exists as a local command, `make gate` (`scripts/gate.py`, plan step 4.7a): it runs a config on all of dev at the merge base and on the working tree, compares the two, and exits 1 on a Fail. The GitHub Action (4.7b) will wrap it. `evalsets/cuad-dev-ci.json` (step 4.5) stays in the repository but is not used by the gate.
