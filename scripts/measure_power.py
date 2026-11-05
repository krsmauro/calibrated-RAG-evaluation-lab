"""The gate on random subsets of dev contracts: false alarms, power and the minimum detectable
effect, from stored runs only (plan step 4.6; finding F-014).

All of dev is the population. Each table draws N subsets of a given number of contracts,
stratified by length like the CI subset, applies the gate to each exactly as `compare` does
(paired cluster bootstrap, 10,000 resamples, then the rule with delta 0.02 on recall@5), and
counts the outcomes. See `ragcalibrate.stats.subsampling` for why contracts are drawn with
replacement; the false-alarm table also shows draws without replacement (the CI subset's own
draw, seeds 0 to N-1), the design's literal version, to show what that changes.

  1. False alarms. Two runs' per-query differences, shifted by their mean on all of dev, so the
     true difference is exactly 0 while each query's noise is real. Nominal: 2.5% of intervals
     wholly below 0 (a false Fail) and 2.5% wholly above. S4 against S1 is the pair whose dev
     difference is already about 0; the others show other kinds of churn.
  2. Power. A regression of known size on top of a null: recall@5 set to 0 on random queries
     until the dev mean falls by the drop (`seed_regression`). Two noise levels: none (S3 with
     the drop against S3: only the dropped queries differ) and a strategy swap (S4 with the drop
     against S1, shifted as in 1). The minimum detectable effect (MDE) is the drop the gate Fails
     with 80% probability, read off the curve by linear interpolation.
  3. Real regressions: S1, S4 and S2 against S3, unshifted, as stored.

Needs the run store and the CUAD zip (`make data`); no database or service.
Usage: uv run python scripts/measure_power.py [--subsets 1000] [--resamples 10000]
"""

import argparse
import math
import statistics
import time
from collections.abc import Mapping
from pathlib import Path

import numpy as np

from ragcalibrate.corpora import evalsets
from ragcalibrate.corpora.cuad import load_cuad
from ragcalibrate.harness.cli import DEFAULT_STORE
from ragcalibrate.harness.store import RunStore
from ragcalibrate.report.compare import DELTA, PRIMARY
from ragcalibrate.stats.bootstrap import N_RESAMPLES
from ragcalibrate.stats.subsampling import Tally, gate_on_subsets, seed_regression, stratified_draw

CUAD_ZIP = Path("data/raw/cuad/data.zip")
# The S1 to S4 dev runs in docs/results.md (chunker C1 at 256, clean commit 4bad31f).
RUNS = {
    "S1": "20261104T194802Z-31d733",
    "S2": "20261104T194807Z-69af36",
    "S3": "20261104T194821Z-4eb392",
    "S4": "20261104T194846Z-bce2cd",
}
SIZES = (40, 60, 100, 150, 200, 300, 408)
NULLS = (("S4", "S1"), ("S1", "S3"), ("S4", "S3"), ("S2", "S3"))  # candidate, baseline
QUERY_LEVEL_UP_TO = 100  # contracts; resampling single queries is slow beyond, and the point made
DROPS = (0.0, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.06)
REAL = (("S1", "S3"), ("S4", "S3"), ("S2", "S3"))
POWER = 0.8
SEED = 20261105


def wilson(k: int, n: int) -> tuple[float, float]:
    """95% Wilson interval of a share k/n (as in scripts/measure_coverage.py)."""
    p, z = k / n, 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def share(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k / n:.3f} [{max(lo, 0.0):.3f}, {min(hi, 1.0):.3f}]"


def shifted(candidate: Mapping[str, float], baseline: Mapping[str, float]) -> dict[str, float]:
    """Per-query differences minus their mean: the same noise with a true difference of 0."""
    raw = {q: candidate[q] - baseline[q] for q in baseline}
    mean = math.fsum(raw.values()) / len(raw)
    return {q: d - mean for q, d in raw.items()}


def mde(fails: list[float]) -> str:
    """The drop at which the share of Fails first reaches POWER, linearly interpolated."""
    for i in range(1, len(DROPS)):
        if fails[i] >= POWER > fails[i - 1]:
            x0, x1, y0, y1 = DROPS[i - 1], DROPS[i], fails[i - 1], fails[i]
            return f"{x0 + (POWER - y0) * (x1 - x0) / (y1 - y0):.3f}"
    return f"> {DROPS[-1]}" if fails[-1] < POWER else "check the grid"


def main() -> None:
    parser = argparse.ArgumentParser(description="False alarms and power of the gate on subsets.")
    parser.add_argument("--subsets", type=int, default=1000)
    parser.add_argument("--resamples", type=int, default=N_RESAMPLES)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    args = parser.parse_args()
    n = args.subsets

    with RunStore.open(args.store) as store:
        stored = {name: store.queries(run_id) for name, run_id in RUNS.items()}
    values = {name: {r.query_id: r.metrics[PRIMARY] for r in rs} for name, rs in stored.items()}
    document_of = {r.query_id: r.document_id for r in stored["S3"]}
    for name, rs in stored.items():
        if {r.query_id: r.document_id for r in rs} != document_of:
            raise SystemExit(f"{name} holds other queries than S3: not one paired population")
    data = load_cuad(CUAD_ZIP)
    strata = evalsets.length_strata(data)
    if {d for s in strata for d in s} != set(document_of.values()):
        raise SystemExit("the runs' documents are not the dev documents")
    if any(v is None for vs in values.values() for v in vs.values()):
        raise SystemExit(f"{PRIMARY} is undefined for some query: answerable queries only")
    population = {
        name: {q: float(v) for q, v in vs.items() if v is not None} for name, vs in values.items()
    }

    def gate(differences: Mapping[str, float], subsets: list[list[str]], **kw: bool) -> Tally:
        return gate_on_subsets(
            differences,
            document_of,
            subsets,
            delta=DELTA,
            seed=SEED,
            n_resamples=args.resamples,
            **kw,
        )

    with_replacement = {
        size: [
            stratified_draw(strata, evalsets.stratum_quotas(size), rng)
            for rng in [np.random.default_rng([SEED, size])]
            for _ in range(n)
        ]
        for size in SIZES
    }
    # The CI subset's own draw, seeds 0 to n-1. All of dev is the same draw every time: skipped.
    without_replacement = {
        size: [
            list(evalsets.ci_subset(data, evalset_hash="-", size=size, seed=i).documents)
            for i in range(n)
        ]
        for size in SIZES
        if size < len(set(document_of.values()))
    }
    per_document = statistics.mean(
        sum(1 for d in document_of.values() if d == doc) for doc in set(document_of.values())
    )
    print(
        f"{len(document_of)} answerable dev queries, {len(set(document_of.values()))} contracts"
        f" ({per_document:.1f} queries each); {n} subsets per row, {args.resamples} resamples,"
        f" delta {DELTA}, seed {SEED}; shares with 95% Wilson intervals"
    )

    started = time.perf_counter()
    print("\n## 1. False alarms: true difference 0 (differences shifted by their dev mean)\n")
    print(
        "| pair | dev mean before shift | queries that differ | draw | contracts"
        " | false Fail (wholly below 0) | wholly above 0 | pass | inconclusive |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for cand, base in NULLS:
        raw = [population[cand][q] - population[base][q] for q in document_of]
        differences = shifted(population[cand], population[base])
        churn = np.mean(np.array(raw) != 0)
        head = f"{cand} - {base} | {math.fsum(raw) / len(raw):+.4f} | {churn:.3f}"
        draws: list[tuple[str, dict[int, list[list[str]]], bool]] = [
            ("cluster, with replacement", with_replacement, False),
            ("cluster, without replacement", without_replacement, False),
        ]
        if (cand, base) == NULLS[0]:
            draws.append(("query-level, with replacement", with_replacement, True))
        for label, subsets_by_size, query_level in draws:
            for size, subsets in subsets_by_size.items():
                if query_level and size > QUERY_LEVEL_UP_TO:
                    continue
                t = gate(differences, subsets, query_level=query_level)
                print(
                    f"| {head} | {label} | {size} | {share(t.failed, n)} | {share(t.above, n)}"
                    f" | {t.passed / n:.3f} | {t.inconclusive / n:.3f} |",
                    flush=True,
                )
    print(f"\n({time.perf_counter() - started:.0f} s)")

    started = time.perf_counter()
    print("\n## 2. Power: a regression of known size (recall@5 set to 0 on random queries)\n")
    noises = {
        "none (S3 with the drop against S3)": ("S3", "S3"),
        "strategy swap (S4 with the drop against S1, shifted)": ("S4", "S1"),
    }
    for noise, (cand, base) in noises.items():
        rows: dict[int, list[Tally]] = {size: [] for size in SIZES}
        realized: list[float] = []
        for k, drop in enumerate(DROPS):
            dropped = seed_regression(population[cand], drop, np.random.default_rng([SEED, k]))
            differences = shifted(population[cand], population[base])
            differences = {q: d + dropped[q] - population[cand][q] for q, d in differences.items()}
            realized.append(0.0 - math.fsum(differences.values()) / len(differences))
            for size in SIZES:
                rows[size].append(gate(differences, with_replacement[size]))
        print(
            f"\nNoise: {noise}. Share of subsets that Fail by the drop on all of dev; and pass /"
            f" inconclusive / fail at drop 0 and {DELTA}:\n"
        )
        print(
            "| contracts | "
            + " | ".join(f"drop {r:.4f}" for r in realized)
            + f" | MDE ({POWER:.0%} Fail) | at 0: P / I / F | at {DELTA}: P / I / F |"
        )
        print("| --- " * (len(DROPS) + 4) + "|")
        for size, tallies in rows.items():
            fails = [t.failed / n for t in tallies]
            at = {d: tallies[DROPS.index(d)] for d in (0.0, DELTA)}
            pif = {
                d: f"{t.passed / n:.2f} / {t.inconclusive / n:.2f} / {t.failed / n:.2f}"
                for d, t in at.items()
            }
            print(
                f"| {size} | "
                + " | ".join(f"{f:.3f}" for f in fails)
                + f" | {mde(fails)} | {pif[0.0]} | {pif[DELTA]} |",
                flush=True,
            )
    print(f"\n({time.perf_counter() - started:.0f} s)")

    started = time.perf_counter()
    print("\n## 3. Real regressions against S3, as stored\n")
    print("| candidate | dev delta | contracts | pass | inconclusive | fail |")
    print("| --- | --- | --- | --- | --- | --- |")
    for cand, base in REAL:
        differences = {q: population[cand][q] - population[base][q] for q in document_of}
        mean = math.fsum(differences.values()) / len(differences)
        for size in SIZES:
            t = gate(differences, with_replacement[size])
            print(
                f"| {cand} | {mean:+.4f} | {size} | {t.passed / n:.3f} | {t.inconclusive / n:.3f}"
                f" | {t.failed / n:.3f} |",
                flush=True,
            )
    print(f"\n({time.perf_counter() - started:.0f} s)")


if __name__ == "__main__":
    main()
