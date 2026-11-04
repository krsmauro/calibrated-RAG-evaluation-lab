"""The paired, document-clustered bootstrap (plan step 4.1), against hand-computed answers.

With two clusters the bootstrap distribution can be enumerated: each resample draws two
clusters with replacement, so it is (a, a) with probability 1/4, a and b with 1/2, (b, b) with
1/4. With 10,000 resamples the share of each outcome is within a few points of that, so the
2.5th and 97.5th percentiles fall inside the outer blocks and the 30th and 70th inside the
middle one: those percentiles are exact values, not approximations.
"""

import statistics

import numpy as np
import pytest

from ragcalibrate.stats.bootstrap import Interval, paired_cluster_bootstrap


def test_two_clusters_by_hand() -> None:
    # Cluster a: differences +1 and 0 (mean 0.5). Cluster b: difference -1.
    candidate = {"q1": 1.0, "q2": 0.5, "q3": 0.0}
    baseline = {"q1": 0.0, "q2": 0.5, "q3": 1.0}
    cluster_of = {"q1": "a", "q2": "a", "q3": "b"}
    # Resample means: (a, a) 0.5; a and b (1 + 0 - 1) / 3 = 0; (b, b) -1. Observed mean 0.
    result = paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=1)
    assert result == Interval(
        mean=0.0,
        lo=-1.0,
        hi=0.5,
        n_queries=3,
        n_clusters=2,
        n_resamples=10_000,
        confidence=0.95,
        seed=1,
    )
    middle = paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=1, confidence=0.4)
    assert (middle.lo, middle.hi) == (0.0, 0.0)


def test_a_resample_mean_weighs_queries_not_clusters() -> None:
    # Cluster a: three queries, each +1; cluster b: one query, 0. Over queries the mean is 3/4;
    # a mean of cluster means would say 1/2.
    candidate = {"a1": 1.0, "a2": 1.0, "a3": 1.0, "b1": 0.0}
    baseline = dict.fromkeys(candidate, 0.0)
    cluster_of = {q: q[0] for q in candidate}
    result = paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=2)
    assert (result.mean, result.lo, result.hi) == (0.75, 0.0, 1.0)
    middle = paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=2, confidence=0.4)
    assert (middle.lo, middle.hi) == (0.75, 0.75)


def test_pairing_removes_the_baseline_spread() -> None:
    # The baselines vary from 0 to 1, but the candidate is the baseline plus 0.25 on every
    # query: every resample's mean difference is 0.25, so the interval has no width.
    rng = np.random.default_rng(3)
    baseline = {f"q{i}": int(rng.integers(5)) / 4 for i in range(60)}
    candidate = {q: v + 0.25 for q, v in baseline.items()}
    cluster_of = {q: f"d{i % 12}" for i, q in enumerate(baseline)}
    result = paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=3)
    assert (result.mean, result.lo, result.hi) == (0.25, 0.25, 0.25)


def noisy(
    n_clusters: int, per_cluster: int, seed: int
) -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
    """Clustered data: each cluster shares one random effect, so its queries are correlated."""
    rng = np.random.default_rng(seed)
    candidate: dict[str, float] = {}
    baseline: dict[str, float] = {}
    cluster_of: dict[str, str] = {}
    for c in range(n_clusters):
        shared = float(rng.normal(0, 1))
        for i in range(per_cluster):
            q = f"d{c}-q{i}"
            baseline[q] = float(rng.random())
            candidate[q] = baseline[q] + shared + float(rng.normal(0, 0.1))
            cluster_of[q] = f"d{c}"
    return candidate, baseline, cluster_of


def test_the_result_depends_on_the_seed_and_not_on_the_input_order() -> None:
    candidate, baseline, cluster_of = noisy(30, 4, seed=4)
    result = paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=7)
    assert paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=7) == result
    shuffled = [str(q) for q in np.random.default_rng(5).permutation(list(candidate))]
    assert (
        paired_cluster_bootstrap(
            {q: candidate[q] for q in shuffled},
            {q: baseline[q] for q in reversed(shuffled)},
            dict(reversed(cluster_of.items())),
            seed=7,
        )
        == result
    )
    assert paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=8) != result


def test_the_vectorized_resampling_equals_a_plain_loop() -> None:
    candidate, baseline, cluster_of = noisy(9, 3, seed=6)
    result = paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=11, n_resamples=500)
    # The same draws, made the same way, then each resample's mean taken query by query.
    clusters = sorted(set(cluster_of.values()))
    queries_of = {c: [q for q in candidate if cluster_of[q] == c] for c in clusters}
    drawn = np.random.default_rng(11).integers(0, len(clusters), size=(500, len(clusters)))
    means = [
        statistics.fmean(
            candidate[q] - baseline[q] for i in row for q in queries_of[clusters[int(i)]]
        )
        for row in drawn
    ]
    lo, hi = np.percentile(means, [2.5, 97.5])
    assert (result.lo, result.hi) == pytest.approx((lo, hi), abs=1e-12)
    assert result.mean == pytest.approx(
        statistics.fmean(candidate[q] - baseline[q] for q in candidate)
    )


def test_correlated_clusters_widen_the_interval_over_a_query_level_one() -> None:
    # Ten queries per cluster share most of their difference. Treating each query as its own
    # cluster (the query-level bootstrap) pretends there are ten times more independent units.
    candidate, baseline, cluster_of = noisy(20, 10, seed=9)
    clustered = paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=1)
    query_level = paired_cluster_bootstrap(candidate, baseline, {q: q for q in candidate}, seed=1)
    assert clustered.mean == pytest.approx(query_level.mean)
    assert (clustered.hi - clustered.lo) > 2 * (query_level.hi - query_level.lo)


@pytest.mark.parametrize(
    ("candidate", "baseline", "cluster_of", "message"),
    [
        ({"q1": 1.0, "q2": 0.0}, {"q1": 1.0}, {"q1": "a", "q2": "b"}, "not paired"),
        ({"q1": 1.0}, {"q2": 1.0}, {"q1": "a", "q2": "b"}, "not paired"),
        ({"q1": 1.0, "q2": 0.0}, {"q1": 1.0, "q2": 0.0}, {"q1": "a"}, "have no cluster"),
        ({"q1": float("nan"), "q2": 0.0}, {"q1": 1.0, "q2": 0.0}, {"q1": "a", "q2": "b"}, "finite"),
        ({"q1": 1.0, "q2": 0.0}, {"q1": 1.0, "q2": 0.0}, {"q1": "a", "q2": "a"}, "two clusters"),
        ({}, {}, {}, "two clusters"),
    ],
)
def test_inputs_that_cannot_be_compared_are_refused(
    candidate: dict[str, float],
    baseline: dict[str, float],
    cluster_of: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        paired_cluster_bootstrap(candidate, baseline, cluster_of, seed=0)


@pytest.mark.parametrize(("option", "value"), [("confidence", 1.0), ("n_resamples", 0)])
def test_settings_out_of_range_are_refused(option: str, value: float) -> None:
    data = {"q1": 1.0, "q2": 0.0}
    clusters = {"q1": "a", "q2": "b"}
    with pytest.raises(ValueError, match=option):
        paired_cluster_bootstrap(data, data, clusters, seed=0, **{option: value})  # type: ignore[arg-type]
