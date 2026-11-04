"""Coverage of the paired cluster bootstrap's 95% interval by number of contracts (plan step 4.2).

For each setting, draws synthetic comparisons with a known true difference (see
`ragcalibrate.stats.coverage`), builds the interval for each, and prints how often it holds the
truth, with a 95% Wilson interval for that share, and how often the interval lies wholly below
the truth: with a true difference of 0, that is a false Fail, nominally 2.5%. The query-level
rows resample single queries, the shortcut the gate must not take.

"discrete" is the draw shaped like CUAD's recall@5 differences; its strength is set so the
intraclass correlation is near dev's (0.02 to 0.05 between S1, S2 and S3; this script prints it).

Usage: uv run python scripts/measure_coverage.py [--simulations 2000] [--resamples 2000]
"""

import argparse
import math
import time

import numpy as np

from ragcalibrate.stats.coverage import CHANGE_RATE, Kind, coverage

CLUSTERS = (10, 20, 30, 40, 60, 100, 200)
QUERY_LEVEL_UP_TO = 100  # each query its own cluster: slow beyond this, and the point is made
SETTINGS: list[tuple[str, Kind, float]] = [
    ("discrete, dev-like ICC", "discrete", 1.0),
    ("discrete, strong ICC", "discrete", 3.0),
    ("gaussian, ICC 0.05", "gaussian", 0.05),
    ("gaussian, ICC 0.20", "gaussian", 0.20),
]
SEED = 42


def discrete_icc(strength: float) -> float:
    """ICC of the discrete draw: between-cluster variance of the mean over total variance."""
    u = np.random.default_rng(0).normal(0, strength, 1_000_000)
    cluster_means = CHANGE_RATE * (2 / (1 + np.exp(-u)) - 1)
    return float(cluster_means.var()) / CHANGE_RATE  # a difference is +-1 at rate CHANGE_RATE


def wilson(k: int, n: int) -> tuple[float, float]:
    p, z = k / n, 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap coverage by number of clusters.")
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--resamples", type=int, default=2000)
    args = parser.parse_args()
    print(f"{args.simulations} simulations per row, {args.resamples} resamples each, seed {SEED}")
    print(f"{'setting':32} {'method':8} {'K':>4} {'coverage':>8} {'95% CI':>15} {'below':>6}")
    for name, kind, strength in SETTINGS:
        label = name + (f" ({discrete_icc(strength):.3f})" if kind == "discrete" else "")
        for k in CLUSTERS:
            for query_level in (False, True):
                if query_level and k > QUERY_LEVEL_UP_TO:
                    continue
                started = time.perf_counter()
                result = coverage(
                    kind,
                    k,
                    strength=strength,
                    delta=0.0,
                    query_level=query_level,
                    n_simulations=args.simulations,
                    n_resamples=args.resamples,
                    seed=SEED,
                )
                lo, hi = wilson(result.covered, result.n_simulations)
                print(
                    f"{label:32} {'query' if query_level else 'cluster':8} {k:4}"
                    f" {result.rate:8.3f}  [{lo:.3f}, {hi:.3f}]"
                    f" {result.too_low / result.n_simulations:6.3f}"
                    f"  ({time.perf_counter() - started:.0f} s)",
                    flush=True,
                )


if __name__ == "__main__":
    main()
