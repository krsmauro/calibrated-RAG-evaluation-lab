"""Relevance-rule sensitivity (docs/eval-spec.md §2; ADR 0004): do stored runs rank the same
under R2 as under R1?

R1, the primary rule, calls a chunk relevant if it overlaps a gold span by one character. R2 asks
for an overlap of at least half the shorter of the span and the chunk. This rescores the stored
rankings of each run under both rules and prints, per rule, each run's recall@5, hit@5 and MRR@10,
each later run's paired difference from the first with its 95% document-clustered interval, and
the order of the runs. The R1 values must equal the ones the runner stored, which also checks
that the gold spans read here are the ones the runs were scored with. The gate uses R1 only.

Dev only: gold spans are used only to score.
Usage: uv run python scripts/measure_relevance.py [--store runs/runs.sqlite] BASELINE RUN...
"""

import argparse
import statistics
from pathlib import Path

from ragcalibrate.corpora import evalsets
from ragcalibrate.harness.cli import DEFAULT_STORE
from ragcalibrate.harness.metrics.retrieval import (
    Interval,
    RankedChunk,
    hit_at_k,
    mrr_at_k,
    recall_at_k,
)
from ragcalibrate.harness.run import QueryResult
from ragcalibrate.harness.store import RunStore
from ragcalibrate.stats.bootstrap import paired_cluster_bootstrap

EVALSETS = Path("evalsets")
RULES = {"R1": 0.0, "R2": 0.5}  # min_overlap_frac in harness.metrics.retrieval
METRICS = ("recall@5", "hit@5", "mrr@10")
SEED = 20261104  # as in `ragcalibrate compare`


def rescore(q: QueryResult, spans: list[Interval], frac: float) -> dict[str, float]:
    ranked = [RankedChunk(str(c), s, e) for c, s, e, _ in q.retrieved]
    values = {
        "recall@5": recall_at_k(ranked, spans, 5, frac),
        "hit@5": hit_at_k(ranked, spans, 5, frac),
        "mrr@10": mrr_at_k(ranked, spans, 10, frac),
    }
    clean = {m: v for m, v in values.items() if v is not None}
    if len(clean) != len(values):
        raise SystemExit(f"{q.query_id} has no gold span; runs score answerable queries only")
    return clean


def main() -> None:
    parser = argparse.ArgumentParser(description="Rescore stored runs under R1 and R2.")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("runs", nargs="+", metavar="RUN_ID")
    args = parser.parse_args()

    evalsets.verify(EVALSETS)
    gold = {
        g.query_id: [Interval(s.start, s.end) for s in g.spans]
        for g in evalsets.read_gold(EVALSETS, "dev")
    }
    with RunStore.open(args.store) as store:
        rows = [store.run(run_id) for run_id in args.runs]
        runs = [store.queries(run_id) for run_id in args.runs]
    base_ids = [q.query_id for q in runs[0]]
    for row, queries in zip(rows, runs, strict=True):
        if row.split != "dev" or [q.query_id for q in queries] != base_ids:
            raise SystemExit(f"{row.id}: not the same dev queries as {rows[0].id}")
    cluster_of = {q.query_id: q.document_id for q in runs[0]}

    # scores[rule][run][metric] = per-query values in base_ids order
    scores: dict[str, list[dict[str, list[float]]]] = {}
    for rule, frac in RULES.items():
        scores[rule] = []
        for row, queries in zip(rows, runs, strict=True):
            per_query = [rescore(q, gold[q.query_id], frac) for q in queries]
            if rule == "R1":
                for q, values in zip(queries, per_query, strict=True):
                    if any(q.metrics[m] != v for m, v in values.items()):
                        raise SystemExit(f"{row.id} {q.query_id}: R1 differs from the stored value")
            scores[rule].append({m: [v[m] for v in per_query] for m in METRICS})

    for i, row in enumerate(rows):
        print(f"[{i}] {row.id}: {row.strategy} {row.chunker_id}")
    print(
        f"{len(base_ids)} queries, {len(set(cluster_of.values()))} documents; R1 values equal the"
        f" stored ones; paired with [0]: mean delta [95% interval, seed {SEED}]"
    )
    for metric in METRICS:
        orders: dict[str, list[int]] = {}
        for rule in RULES:
            means = [statistics.fmean(run[metric]) for run in scores[rule]]
            orders[rule] = sorted(range(len(rows)), key=lambda j: -means[j])
            cells: list[str] = []
            for i, run in enumerate(scores[rule]):
                cell = f"[{i}] {means[i]:.4f}"
                if i > 0:
                    ci = paired_cluster_bootstrap(
                        dict(zip(base_ids, run[metric], strict=True)),
                        dict(zip(base_ids, scores[rule][0][metric], strict=True)),
                        cluster_of,
                        seed=SEED,
                    )
                    cell += f" {ci.mean:+.4f} [{ci.lo:+.4f}, {ci.hi:+.4f}]"
                cells.append(cell)
            order = " > ".join(f"[{j}]" for j in orders[rule])
            print(f"  {metric:<9} {rule}: {'; '.join(cells)}; order {order}")
        verdict = "the same as" if orders["R1"] == orders["R2"] else "DIFFERENT from"
        print(f"  {metric:<9} order under R2 is {verdict} the order under R1")


if __name__ == "__main__":
    main()
