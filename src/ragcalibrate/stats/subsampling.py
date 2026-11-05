"""The gate on random subsets of contracts: false alarms, power, minimum detectable effect (plan
step 4.6; Design §8.5; skill STAT-CRITICAL-4).

All of dev is the population. A subset is drawn as the CI subset is (docs/eval-spec.md §7: a
quota from each length stratum), and the gate is applied to it as `compare` applies it: the
paired cluster bootstrap on the subset's per-query differences, then `decide`. Counting the
outcomes over many subsets gives the gate's false-alarm rate (a true difference of 0) and its
power (a regression of known size, made with `seed_regression`).

Subsets are drawn with replacement within each stratum, a model of a population of contracts
much larger than dev: drawn without replacement, 200 of 408 contracts overlap so much that they
vary less than 200 new contracts would, and the gate would look more powerful and quieter than
it is. A contract drawn twice counts as two clusters, as two similar contracts would.

Pure and seeded: the same inputs give the same counts.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import NamedTuple

import numpy as np

from ragcalibrate.stats.bootstrap import N_RESAMPLES, paired_cluster_bootstrap
from ragcalibrate.stats.gate import Outcome, decide


class Tally(NamedTuple):
    n_subsets: int
    passed: int
    failed: int
    inconclusive: int
    below: int  # interval wholly below 0 (a Fail, or a Pass with "small regression detected")
    above: int  # interval wholly above 0


def stratified_draw(
    strata: Sequence[Sequence[str]], quotas: Sequence[int], rng: np.random.Generator
) -> list[str]:
    """`quotas[i]` clusters from `strata[i]`, with replacement, stratum by stratum."""
    if len(quotas) != len(strata) or min(quotas) < 0:
        raise ValueError(f"need one quota of at least 0 per stratum, got {list(quotas)}")
    return [
        s[int(j)] for s, k in zip(strata, quotas, strict=True) for j in rng.integers(0, len(s), k)
    ]


def seed_regression(
    values: Mapping[str, float], drop: float, rng: np.random.Generator
) -> dict[str, float]:
    """A copy of `values` (one metric per query, at least 0) in which queries, taken in a random
    order, are set to 0 until the mean has fallen by `drop`: for recall@k, "the relevant chunks
    fell out of the top k" on a random share of queries. The fall overshoots `drop` by less than
    one query's value over the number of queries, so the regression's size is known."""
    if drop < 0:
        raise ValueError(f"drop is the size of a regression, at least 0, not {drop}")
    if min(values.values()) < 0:
        raise ValueError("values must not be negative: a query's loss is its value")
    target = drop * len(values)
    if target > sum(values.values()):
        raise ValueError(f"cannot fall by {drop}, more than the mean")
    dropped = dict(values)
    order = sorted(values)  # a fixed order, so the seed picks the same queries every time
    lost = 0.0
    for i in rng.permutation(len(order)):
        if lost >= target:
            break
        lost += dropped[order[i]]
        dropped[order[i]] = 0.0
    return dropped


def gate_on_subsets(
    differences: Mapping[str, float],
    cluster_of: Mapping[str, str],
    subsets: Sequence[Sequence[str]],
    *,
    delta: float,
    seed: int,
    n_resamples: int = N_RESAMPLES,
    query_level: bool = False,
) -> Tally:
    """The gate's outcome on each subset of clusters, counted.

    `differences` maps each query to its paired difference, candidate minus baseline;
    `cluster_of` gives its cluster. Subset i is bootstrapped with seed `seed + i`, so two calls
    on the same subsets use the same resamples (common random numbers: a power curve over
    several regression sizes moves only because the differences do). `query_level` resamples
    single queries, the shortcut the gate must not take, to show what it would do.
    """
    queries_of: defaultdict[str, list[str]] = defaultdict(list)
    for query in differences:
        queries_of[cluster_of[query]].append(query)
    counts = {outcome: 0 for outcome in Outcome}
    below = above = 0
    for i, subset in enumerate(subsets):
        # Each draw is its own cluster, so a contract drawn twice is two clusters.
        candidate = {
            f"{j}/{q}": differences[q] for j, c in enumerate(subset) for q in queries_of[c]
        }
        clusters = {key: key if query_level else key.split("/")[0] for key in candidate}
        interval = paired_cluster_bootstrap(
            candidate,
            dict.fromkeys(candidate, 0.0),
            clusters,
            seed=seed + i,
            n_resamples=n_resamples,
        )
        counts[decide(interval.lo, interval.hi, delta).outcome] += 1
        below += interval.hi < 0
        above += interval.lo > 0
    return Tally(
        n_subsets=len(subsets),
        passed=counts[Outcome.PASS],
        failed=counts[Outcome.FAIL],
        inconclusive=counts[Outcome.INCONCLUSIVE],
        below=below,
        above=above,
    )
