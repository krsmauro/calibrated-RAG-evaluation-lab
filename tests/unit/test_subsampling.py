"""The gate on subsets of contracts (plan step 4.6): known answers, worked out by hand.

The full study, on the stored dev runs, is `scripts/measure_power.py` (finding F-014).
"""

from collections import Counter

import numpy as np
import pytest

from ragcalibrate.stats.subsampling import Tally, gate_on_subsets, seed_regression, stratified_draw

DELTA = 0.02


def _one_query_each(differences: dict[str, float]) -> tuple[dict[str, float], dict[str, str]]:
    """Clusters of one query each, the query named after its cluster."""
    return {f"{c}.q": d for c, d in differences.items()}, {f"{c}.q": c for c in differences}


def test_each_stratum_gives_its_quota_and_only_its_own_clusters() -> None:
    strata = [["a", "b"], ["c", "d", "e"], ["f"]]
    for seed in range(20):
        drawn = stratified_draw(strata, [2, 3, 4], np.random.default_rng(seed))
        assert len(drawn) == 9
        assert sum(d in strata[0] for d in drawn) == 2
        assert sum(d in strata[1] for d in drawn) == 3
        assert drawn.count("f") == 4  # with replacement: a stratum of one gives it four times


def test_the_draw_is_with_replacement_and_reproducible() -> None:
    strata = [[f"s{i}" for i in range(10)]]
    draws = [stratified_draw(strata, [10], np.random.default_rng(seed)) for seed in range(50)]
    assert any(len(set(d)) < 10 for d in draws)  # 10 of 10 with replacement repeats, nearly always
    again = stratified_draw(strata, [10], np.random.default_rng(3))
    assert again == draws[3]
    assert draws[3] != draws[4]


def test_a_quota_must_fit_the_strata() -> None:
    with pytest.raises(ValueError, match="quota"):
        stratified_draw([["a"], ["b"]], [1], np.random.default_rng(0))
    with pytest.raises(ValueError, match="quota"):
        stratified_draw([["a"]], [-1], np.random.default_rng(0))


def test_a_regression_of_equal_values_zeroes_exactly_that_share_of_queries() -> None:
    # Ten queries at 1.0: a fall of 0.3 in the mean is three queries set to 0, no more.
    values = {f"q{i}": 1.0 for i in range(10)}
    for seed in range(20):
        dropped = seed_regression(values, 0.3, np.random.default_rng(seed))
        assert sorted(dropped.values()) == [0.0] * 3 + [1.0] * 7
        assert values == {f"q{i}": 1.0 for i in range(10)}  # the input is not changed


def test_a_regression_falls_by_at_least_the_drop_and_overshoots_by_less_than_one_query() -> None:
    rng = np.random.default_rng(5)
    values = {f"q{i}": float(v) for i, v in enumerate(rng.choice([0, 0.25, 0.5, 1], 200))}
    mean = sum(values.values()) / 200
    for drop in (0.01, 0.05, 0.2):
        dropped = seed_regression(values, drop, np.random.default_rng(1))
        fall = mean - sum(dropped.values()) / 200
        assert drop <= fall < drop + 1.0 / 200
        changed = [q for q in values if dropped[q] != values[q]]
        assert all(dropped[q] == 0.0 for q in changed)  # a changed query is set to 0, nothing else


def test_no_drop_changes_nothing_and_a_drop_past_the_mean_or_below_zero_raises() -> None:
    values = {"a": 0.5, "b": 0.0}
    assert seed_regression(values, 0.0, np.random.default_rng(0)) == values
    assert seed_regression(values, 0.25, np.random.default_rng(0)) == {"a": 0.0, "b": 0.0}
    with pytest.raises(ValueError, match="mean"):
        seed_regression(values, 0.26, np.random.default_rng(0))
    with pytest.raises(ValueError, match="drop"):
        seed_regression(values, -0.01, np.random.default_rng(0))
    with pytest.raises(ValueError, match="negative"):
        seed_regression({"a": -0.5, "b": 1.0}, 0.1, np.random.default_rng(0))


def test_a_regression_is_the_same_for_the_same_seed() -> None:
    values = {f"q{i}": 1.0 for i in range(100)}
    first = seed_regression(values, 0.1, np.random.default_rng(7))
    assert first == seed_regression(values, 0.1, np.random.default_rng(7))
    assert first != seed_regression(values, 0.1, np.random.default_rng(8))


def test_outcomes_on_enumerable_subsets() -> None:
    # Two clusters of one query, differences -1 (A) and 0 (B). Subset [A, B]: a resample's mean
    # is -1, -0.5 or 0 with chances 1/4, 1/2, 1/4, so the 95% interval is [-1, 0]: Inconclusive.
    # [A, A]: a cluster drawn twice is two clusters, interval [-1, -1]: Fail. [B, B]: [0, 0]: Pass.
    differences, cluster_of = _one_query_each({"A": -1.0, "B": 0.0})
    tally = gate_on_subsets(
        differences, cluster_of, [["A", "B"], ["A", "A"], ["B", "B"]], delta=DELTA, seed=1
    )
    assert tally == Tally(n_subsets=3, passed=1, failed=1, inconclusive=1, below=1, above=0)


def test_a_constant_difference_passes_below_delta_and_fails_beyond_it() -> None:
    # Binary fractions, so every resample's mean is exact and the interval is [c, c].
    def run(c: float) -> Tally:
        differences, cluster_of = _one_query_each({x: c for x in "ABCD"})
        return gate_on_subsets(
            differences, cluster_of, [["A", "B", "C", "D"]] * 5, delta=DELTA, seed=2
        )

    assert run(-1 / 64) == Tally(5, passed=5, failed=0, inconclusive=0, below=5, above=0)
    assert run(-1 / 32) == Tally(5, passed=0, failed=5, inconclusive=0, below=5, above=0)
    assert run(1 / 64) == Tally(5, passed=5, failed=0, inconclusive=0, below=0, above=5)
    assert run(0.0) == Tally(5, passed=5, failed=0, inconclusive=0, below=0, above=0)


def test_resampling_queries_ignores_the_clusters() -> None:
    # A: eight queries at -1, B: eight at 0. By cluster, [A, B] is [-1, 0]: Inconclusive. By
    # query, a resample's mean is -K/16 with K ~ Binomial(16, 1/2); P(K <= 3) = 0.011 and
    # P(K <= 4) = 0.038, so the upper end is -4/16 and the interval is wholly below 0: Fail.
    differences = {f"{c}{i}": (-1.0 if c == "A" else 0.0) for c in "AB" for i in range(8)}
    cluster_of = {q: q[0] for q in differences}
    subsets = [["A", "B"]]
    by_cluster = gate_on_subsets(differences, cluster_of, subsets, delta=DELTA, seed=3)
    by_query = gate_on_subsets(
        differences, cluster_of, subsets, delta=DELTA, seed=3, query_level=True
    )
    assert (by_cluster.inconclusive, by_query.failed) == (1, 1)


def test_tallies_are_reproducible_and_add_up() -> None:
    rng = np.random.default_rng(9)
    differences = {
        f"c{c}.q{i}": float(rng.choice([-1, 0, 0, 1])) for c in range(30) for i in range(5)
    }
    cluster_of = {q: q.split(".")[0] for q in differences}
    strata = [[f"c{c}" for c in range(30)]]
    subsets = [stratified_draw(strata, [12], rng) for _ in range(40)]
    tally = gate_on_subsets(differences, cluster_of, subsets, delta=0.1, seed=4)
    assert tally == gate_on_subsets(differences, cluster_of, subsets, delta=0.1, seed=4)
    assert tally.passed + tally.failed + tally.inconclusive == tally.n_subsets == 40
    assert tally.below <= tally.failed + tally.passed  # below 0 is a Fail or a noted Pass
    counts = Counter(len(set(s)) for s in subsets)
    assert min(counts) < 12  # some subsets hold a cluster twice, and still run
