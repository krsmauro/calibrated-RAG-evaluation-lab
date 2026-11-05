# F-003: the cluster bootstrap under-covers below about 40 contracts

- **Status:** confirmed (synthetic data, then real dev subsets in step 4.6, F-014); the CI subset size is decided by power, not coverage (F-014, D9)
- **Date:** 2026-10-19 (hypothesis); measured 2026-11-04
- **Found by:** Claude, while writing the plan; measured in plan step 4.2
- **Evidence level:** measured on simulated data shaped like CUAD dev (command and output below); not yet on real subsets of dev, which is step 4.6
- **Affects:** 4.2, 4.4, 4.5, 4.6; Design §8.5; `docs/eval-spec.md` (CI subset)

## Finding
The gate resamples contracts. On synthetic comparisons shaped like CUAD dev (13 queries per contract on average, differences mostly 0, within-contract correlation 0.043 where dev's is 0.02 to 0.05), the paired cluster bootstrap's 95% interval holds the true difference 91.5% of the time with 10 contracts, 92.1% with 20, 93.3% with 30, and 94.6% to 95.2% from 40 contracts up. The share of intervals wholly below a true difference of 0, which is the gate's false-fail rate (nominal 2.5%), is 4.1%, 3.8% and 3.0% at 10, 20 and 30 contracts, and 2.2% to 3.2% from 40 up. So the hypothesis held: the percentile bootstrap is too narrow with few clusters. Resampling single queries instead is much worse at every size: 87% to 89% coverage and 5.7% to 7.2% false fails at dev's correlation, 72% to 76% and 12% to 14% at a correlation of 0.135. With strong correlation (Gaussian, 0.20) even the cluster bootstrap stays a little short, 93.6% to 94.3% at 60 to 200 contracts.

## Evidence
`uv run python scripts/measure_coverage.py --simulations 2000 --resamples 2000` (seed 42; about 12 minutes), using `ragcalibrate.stats.coverage`. Each row: 2,000 simulated comparisons, each with 2 to 24 queries per contract, a 95% interval per comparison; "coverage" is the share holding the truth (95% Wilson interval of that share in brackets), "below" the share lying wholly below it.

| Setting (ICC) | Method | 10 | 20 | 30 | 40 | 60 | 100 | 200 contracts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| discrete, dev-like (0.043) | cluster | 0.915 | 0.921 | 0.933 [0.921, 0.943] | 0.949 [0.938, 0.957] | 0.952 | 0.946 | 0.951 |
| | below (nominal 0.025) | 0.041 | 0.038 | 0.030 | 0.027 | 0.028 | 0.032 | 0.022 |
| | query | 0.885 | 0.875 | 0.875 | 0.884 | 0.881 | 0.868 | not run |
| | below | 0.060 | 0.057 | 0.057 | 0.059 | 0.060 | 0.072 | |
| discrete, strong (0.135) | cluster | 0.912 | 0.928 | 0.932 | 0.947 | 0.953 | 0.942 | 0.953 |
| | query | 0.752 | 0.755 | 0.724 | 0.746 | 0.738 | 0.740 | not run |
| gaussian (0.05) | cluster | 0.909 | 0.925 | 0.927 | 0.941 | 0.943 | 0.944 | 0.948 |
| | query | 0.865 | 0.859 | 0.850 | 0.858 | 0.858 | 0.860 | not run |
| gaussian (0.20) | cluster | 0.902 | 0.924 | 0.928 | 0.935 | 0.936 [0.925, 0.946] | 0.943 | 0.942 [0.930, 0.951] |
| | query | 0.666 | 0.660 | 0.649 | 0.670 | 0.668 | 0.664 | not run |

With 2,000 simulations a correct 95% interval lands within about ±0.010 of 0.95 (one Wilson half-width). The "discrete" draw is the one shaped like CUAD's recall@5 differences: a query changes with probability 1/4, up or down with its contract's tilt; its true difference is 0. Dev's correlation was measured on the stored S1, S2 and S3 runs (one-way ANOVA estimator on per-query recall@5 differences): S3 - S1 0.041, S1 - S2 0.053, S3 - S2 0.021; dev has 13.4 answerable queries per contract (2 to 32), and 66% to 81% of queries have a difference of 0. On the real dev runs the clustered intervals were 1.09 to 1.21 times as wide as query-level ones (step 4.1 Done note).

`tests/unit/test_coverage.py` checks the main claims with 400 simulations each (a ±0.036 band): the cluster bootstrap covers within the band at 60 contracts with correlation 0.20 and at 100 contracts on the CUAD-shaped null; the query-level one falls below the band.

## Consequence
- The CI subset (4.5) should hold at least 40 contracts, and 60 or more leaves a margin; below 30, the gate would fail a no-op change about 1.2 to 1.6 times as often as it claims. Dev has 408 contracts and retrieval is cheap (an S4 run on 40 contracts takes about 45 s), so this costs little. Step 4.6 measures the false-alarm rate on real dev subsets and sets the final size.
- `compare` (4.4) should treat a comparison with fewer than the minimum number of contracts as Inconclusive with that reason, not as a tight interval (skill STAT-HIGH-2); the gate rule in 4.3 does not check it.
- If a smaller subset is ever needed, the options are BCa or studentized intervals, or widening by the small-sample factor; none is built.
- The query-level bootstrap must never gate: at dev's own correlation it more than doubles the false-fail rate.

## Resolution
2026-11-05, step 4.6 (F-014): checked on real subsets of CUAD dev (stored S1 to S4 runs, 1,000 subsets per row, drawn with replacement within length terciles). The clustered gate's false-Fail rate is 2.4% to 3.1% at 40 contracts and 2.5% pooled over 40 to 408 contracts (four pairs of runs); the two tails together miss 5.0% to 6.2% at 40 and 60 contracts, matching the synthetic 94.9% to 95.2% coverage above. Resampling queries falsely Fails 3.7% (S4 against S1, 40 to 100 contracts): less excess than the synthetic 5.7% to 7.2%, since dev's correlation is low, but still 50% above nominal. The 40-contract minimum in `compare` stands. Coverage is not what limits the CI subset; power is (F-014).
