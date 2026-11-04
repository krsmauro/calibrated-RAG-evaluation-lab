"""The paired, document-clustered bootstrap (plan step 4.1; Design §8.5; skill STAT-CRITICAL-1).

Compares two runs on the same queries. Each query gives one paired difference, candidate minus
baseline, and belongs to a cluster: its document, since queries about one contract share its
chunking and formatting and are not independent. A resample draws as many clusters as there
are, with replacement, keeps every query of each drawn cluster, and takes the mean difference
over those queries. The interval is the percentiles of 10,000 such means (numpy's default
linear interpolation, which is part of the definition).

A query-level bootstrap, which understates the variance when clusters are correlated, is this
same function with every query its own cluster; it exists to show that difference (plan steps
4.2 and 4.6), never to gate.

Pure: no I/O, no clock, and a seeded generator, so the same inputs and seed give the same
interval, whatever order the inputs come in.
"""

import math
from collections import defaultdict
from collections.abc import Mapping
from typing import NamedTuple

import numpy as np

N_RESAMPLES = 10_000
CONFIDENCE = 0.95


class Interval(NamedTuple):
    """The observed mean paired difference over queries, its interval, and how it was made."""

    mean: float
    lo: float
    hi: float
    n_queries: int
    n_clusters: int
    n_resamples: int
    confidence: float
    seed: int


def paired_cluster_bootstrap(
    candidate: Mapping[str, float],
    baseline: Mapping[str, float],
    cluster_of: Mapping[str, str],
    *,
    seed: int,
    n_resamples: int = N_RESAMPLES,
    confidence: float = CONFIDENCE,
) -> Interval:
    """Percentile interval of mean(candidate - baseline), resampling clusters of queries.

    `candidate` and `baseline` map query id to the query's value of one metric, and must hold
    the same queries: a comparison of different query sets is not paired, so it raises rather
    than dropping the queries that do not match. `cluster_of` maps each query id to its cluster.
    """
    if candidate.keys() != baseline.keys():
        only = sorted(candidate.keys() ^ baseline.keys())
        raise ValueError(f"not paired: {len(only)} queries are in one run only, such as {only[0]}")
    if missing := sorted(candidate.keys() - cluster_of.keys()):
        raise ValueError(f"{len(missing)} queries have no cluster, such as {missing[0]}")
    values = [*candidate.values(), *baseline.values()]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("every value must be a finite number; exclude undefined metrics first")
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be between 0 and 1, not {confidence}")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be at least 1, not {n_resamples}")

    differences: defaultdict[str, list[float]] = defaultdict(list)
    for query_id in candidate:
        differences[cluster_of[query_id]].append(candidate[query_id] - baseline[query_id])
    if len(differences) < 2:
        # Every resample would be that one cluster: an interval of width zero that means nothing.
        raise ValueError(f"a cluster bootstrap needs at least two clusters, not {len(differences)}")
    # Clusters in a fixed order, so the seed draws the same clusters however the input was built.
    clusters = sorted(differences)
    sums = np.array([math.fsum(differences[c]) for c in clusters])
    sizes = np.array([len(differences[c]) for c in clusters])

    rng = np.random.default_rng(seed)
    drawn = rng.integers(0, len(clusters), size=(n_resamples, len(clusters)))
    means = sums[drawn].sum(axis=1) / sizes[drawn].sum(axis=1)
    tail = (1 - confidence) / 2 * 100
    lo, hi = np.percentile(means, [tail, 100 - tail])
    return Interval(
        mean=math.fsum(d for ds in differences.values() for d in ds) / len(candidate),
        lo=float(lo),
        hi=float(hi),
        n_queries=len(candidate),
        n_clusters=len(clusters),
        n_resamples=n_resamples,
        confidence=confidence,
        seed=seed,
    )
