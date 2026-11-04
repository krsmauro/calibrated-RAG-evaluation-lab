"""Coverage of the paired cluster bootstrap on synthetic data (plan step 4.2; finding F-003).

Draws many synthetic comparisons with a known true mean difference, builds the bootstrap
interval for each, and counts how often the interval holds the truth: about 95% for a 95%
interval if the bootstrap is right. Queries are grouped in clusters (contracts) whose queries
share an effect, so they are correlated, as on CUAD.

Two ways to draw a paired difference per query, both with 2 to 24 queries per cluster (mean 13,
as CUAD dev's 13.4, range 2 to 32):

- "gaussian": the true delta, plus a cluster effect, plus noise, with variances icc and 1 - icc,
  so `strength` is the intraclass correlation itself.
- "discrete": like a recall@5 difference on CUAD, mostly 0 (dev: 66% to 81% of queries). A query
  changes with probability 1/4, up (+1) with probability sigmoid(u) and down (-1) otherwise,
  where u is its cluster's effect, normal with standard deviation `strength`. The true mean
  difference is 0 by symmetry, which is the case the false-fail rate is about.

Pure and seeded: the same arguments give the same counts.
"""

import math
from typing import Literal, NamedTuple

import numpy as np

from ragcalibrate.stats.bootstrap import paired_cluster_bootstrap

Kind = Literal["gaussian", "discrete"]
CHANGE_RATE = 0.25  # share of queries whose difference is not 0, in the discrete draw


class Coverage(NamedTuple):
    n_clusters: int
    n_simulations: int
    covered: int  # intervals that hold the true difference
    too_low: int  # hi below the truth: with a true difference of 0, a false Fail
    too_high: int  # lo above the truth

    @property
    def rate(self) -> float:
        return self.covered / self.n_simulations


def draw(
    rng: np.random.Generator, kind: Kind, n_clusters: int, strength: float, delta: float
) -> tuple[dict[str, float], dict[str, str], float]:
    """One synthetic comparison: each query's paired difference, its cluster, and the truth."""
    if kind == "discrete" and delta != 0:
        raise ValueError("the discrete draw has a true difference of 0 only")
    differences: dict[str, float] = {}
    cluster_of: dict[str, str] = {}
    for c in range(n_clusters):
        size = int(rng.integers(2, 25))
        if kind == "gaussian":
            shared = rng.normal(0, math.sqrt(strength))
            values = delta + shared + rng.normal(0, math.sqrt(1 - strength), size)
        else:
            up = 1 / (1 + math.exp(-rng.normal(0, strength)))
            changed = rng.random(size) < CHANGE_RATE
            values = np.where(changed, np.where(rng.random(size) < up, 1.0, -1.0), 0.0)
        for i, value in enumerate(values):
            differences[f"{c}:{i}"] = float(value)
            cluster_of[f"{c}:{i}"] = str(c)
    return differences, cluster_of, delta if kind == "gaussian" else 0.0


def coverage(
    kind: Kind,
    n_clusters: int,
    *,
    strength: float,
    delta: float = 0.0,
    query_level: bool = False,
    n_simulations: int,
    n_resamples: int,
    seed: int,
) -> Coverage:
    """How often a 95% interval holds the truth. `query_level` resamples single queries, which
    ignores the clusters: the shortcut whose under-coverage this is meant to show."""
    rng = np.random.default_rng(seed)
    covered = too_low = too_high = 0
    for _ in range(n_simulations):
        differences, cluster_of, truth = draw(rng, kind, n_clusters, strength, delta)
        if query_level:
            cluster_of = {q: q for q in differences}
        zeros = dict.fromkeys(differences, 0.0)
        interval = paired_cluster_bootstrap(
            differences,
            zeros,
            cluster_of,
            seed=int(rng.integers(2**63)),
            n_resamples=n_resamples,
        )
        if interval.hi < truth:
            too_low += 1
        elif interval.lo > truth:
            too_high += 1
        else:
            covered += 1
    return Coverage(n_clusters, n_simulations, covered, too_low, too_high)
