"""Check that runs of one experiment gave the same results (plan step 3.8).

Compares each run with the first, query by query: the ranking (chunk ids and offsets, in order),
the scores, and the metrics. Runs must share a config hash, since two experiments are expected to
differ. If only scores differ, the largest gap is printed: that is the tolerance a comparison of
scores would need (the step asks to compare ranks then, and write the gap up as a finding).

Exit code 0 if every run equals the first, 1 if any differs, 2 if the runs are not comparable.
Usage: uv run python scripts/check_determinism.py [--store runs/runs.sqlite] RUN_A RUN_B [RUN...]
"""

import argparse
import sys
from pathlib import Path

from ragcalibrate.harness.cli import DEFAULT_STORE
from ragcalibrate.harness.store import RunStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that repeated runs are identical.")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("runs", nargs="+", metavar="RUN_ID")
    args = parser.parse_args()
    if len(args.runs) < 2:
        parser.error("give at least two runs")
    with RunStore.open(args.store) as store:
        rows = [store.run(run_id) for run_id in args.runs]
        results = [store.queries(run_id) for run_id in args.runs]
    if len({row.config_hash for row in rows}) != 1:
        print("not one experiment: the runs have different config hashes")
        return 2
    base_row, base = rows[0], results[0]
    identical = True
    for row, other in zip(rows[1:], results[1:], strict=True):
        if [q.query_id for q in other] != [q.query_id for q in base]:
            print(f"{row.id}: not the same queries as {base_row.id}")
            identical = False
            continue
        ranking = scores = metrics = 0
        gap = 0.0
        for a, b in zip(base, other, strict=True):
            if [c[:3] for c in a.retrieved] != [c[:3] for c in b.retrieved]:
                ranking += 1
            elif a.retrieved != b.retrieved:
                scores += 1
                pairs = zip(a.retrieved, b.retrieved, strict=True)
                gap = max(gap, *(abs(x[3] - y[3]) for x, y in pairs))
            metrics += a.metrics != b.metrics
        n_rows = sum(len(q.retrieved) for q in other)
        same = ranking == scores == metrics == 0
        identical &= same
        print(
            f"{row.id} vs {base_row.id} ({row.strategy}, {row.chunker_id[:4]}):"
            f" {len(other)} queries, {n_rows} retrieved rows;"
            f" {'identical' if same else 'DIFFERENT'}: rankings differ {ranking},"
            f" scores alone differ {scores} (largest gap {gap:.3g}), metrics differ {metrics}"
        )
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
