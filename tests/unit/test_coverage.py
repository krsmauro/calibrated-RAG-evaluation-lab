"""Coverage of the paired cluster bootstrap on synthetic data (plan step 4.2).

Each check counts how many of N simulated 95% intervals hold the known truth. If the bootstrap is
right, that count is Binomial(N, 0.95), so the test accepts a share within 3.29 binomial
standard errors of 0.95 (a 99.9% band): fixed seeds make each run the same, and the band says how
far from 95% a correct bootstrap can land with N simulations. The full table, with more
simulations and contract counts down to 10, is `scripts/measure_coverage.py` (finding F-003).
"""

import math

import numpy as np
import pytest

from ragcalibrate.stats.coverage import coverage, draw

N = 400
BAND = 3.29 * math.sqrt(0.95 * 0.05 / N)  # about 0.036
TAIL_BAND = 3.29 * math.sqrt(0.025 * 0.975 / N)  # about 0.026, for a 2.5% rate


def test_the_cluster_bootstrap_covers_with_correlated_clusters_and_queries_do_not() -> None:
    # ICC 0.2 and about 13 queries per cluster: queries of one contract are far from
    # independent, so resampling queries understates the variance.
    def run(query_level: bool) -> float:
        return coverage(
            "gaussian",
            60,
            strength=0.2,
            delta=0.3,
            query_level=query_level,
            n_simulations=N,
            n_resamples=1000,
            seed=1,
        ).rate

    clustered, query_level = run(False), run(True)
    assert abs(clustered - 0.95) <= BAND
    assert query_level < 0.95 - BAND
    assert query_level < clustered - 0.1


def test_the_cluster_bootstrap_covers_a_null_shaped_like_cuad() -> None:
    # Mostly zero differences, an ICC near dev's: the case a false Fail is made of.
    result = coverage("discrete", 100, strength=1.0, n_simulations=N, n_resamples=1000, seed=2)
    assert abs(result.rate - 0.95) <= BAND
    assert result.covered + result.too_low + result.too_high == N
    assert result.too_low / N <= 0.025 + TAIL_BAND  # the nominal false-fail rate


def test_coverage_counts_are_reproducible() -> None:
    def run() -> object:
        return coverage("discrete", 20, strength=1.0, n_simulations=50, n_resamples=200, seed=3)

    assert run() == run()


def test_the_synthetic_data_has_the_correlation_asked_for() -> None:
    # One large draw, ICC estimated from cluster means: close to the 0.2 asked for.
    differences, cluster_of, truth = draw(np.random.default_rng(4), "gaussian", 2000, 0.2, 0.3)
    assert truth == 0.3
    clusters: dict[str, list[float]] = {}
    for q, d in differences.items():
        clusters.setdefault(cluster_of[q], []).append(d)
    means = np.array([np.mean(v) for v in clusters.values()])
    within = np.mean([np.var(v, ddof=1) for v in clusters.values() if len(v) > 1])
    sizes = np.array([len(v) for v in clusters.values()])
    between = means.var(ddof=1) - within * np.mean(1 / sizes)
    assert between / (between + within) == pytest.approx(0.2, abs=0.03)
    assert np.mean(list(differences.values())) == pytest.approx(0.3, abs=0.03)


def test_the_discrete_draw_is_a_null_only() -> None:
    with pytest.raises(ValueError, match="true difference of 0 only"):
        draw(np.random.default_rng(0), "discrete", 10, 1.0, 0.1)
