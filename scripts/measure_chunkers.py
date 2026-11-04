"""Compare chunkers C1 and C2 on CUAD (plan step 3.4; the full comparison is step 3.9).

  structure        Chunk sizes for C1 and C2, how often C2 falls back to C1 (a section longer
                   than the window), and how many dev gold spans lie wholly inside one chunk.
                   Reads the CUAD zip and the tokenizer; no database or service.
  budget RUN...    Character precision and recall at a fixed retrieved budget (docs/eval-spec.md
                   §3.4) for runs in the run store (`ragcalibrate run`), each paired per query
                   with the first. recall@k rewards bigger chunks, so chunkers are compared
                   this way.

The budget is counted in whitespace-separated words, a stand-in: the spec wants one fixed,
provider-neutral tokenizer, chosen in step 4.9 (ADR 0004). Words are the same for every chunker
and strategy, which is what a comparison needs. Runs keep their top 10 chunks, so a budget the
top 10 do not fill is reported as such.

Dev only: gold spans are used only to score.
Usage: uv run python scripts/measure_chunkers.py structure
       uv run python scripts/measure_chunkers.py budget [--store runs/runs.sqlite] RUN_A RUN_B
"""

import argparse
import re
import statistics
from bisect import bisect_left
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

from tokenizers import Tokenizer

from ragcalibrate.corpora import evalsets
from ragcalibrate.corpora.cuad import load_cuad
from ragcalibrate.harness.cli import DEFAULT_STORE
from ragcalibrate.harness.metrics.retrieval import (
    Interval,
    RankedChunk,
    char_precision_recall_at_budget,
)
from ragcalibrate.harness.run import summarize
from ragcalibrate.harness.store import RunStore
from ragcalibrate.ingest.chunkers import chunk_c1, chunk_c2, heading_starts
from ragcalibrate.ingest.embedding import DEFAULT_MODEL_DIR, load_tokenizer

CUAD_ZIP = Path("data/raw/cuad/data.zip")
EVALSETS = Path("evalsets")
SIZE, OVERLAP = 256, 32  # as loaded by scripts/ingest.py
BUDGETS = (256, 512, 1024)  # words; eval-spec §8 lists 2048 too, beyond what a top 10 holds
WORD = re.compile(r"\S+")


def word_ends(text: str) -> list[int]:
    return [m.end() for m in WORD.finditer(text)]


def n_tokens(tok: Tokenizer, text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False).ids)


def structure() -> None:
    data = load_cuad(CUAD_ZIP)
    tok = load_tokenizer(DEFAULT_MODEL_DIR)
    spans_of: dict[str, list[Interval]] = defaultdict(list)
    for g in data.split("dev")[1]:
        spans_of[g.document_id] += [Interval(s.start, s.end) for s in g.spans]
    n_spans = sum(map(len, spans_of.values()))
    print(f"{len(data.documents)} contracts; window {SIZE} tokens, overlap {OVERLAP}")
    for name, chunk in (("C1", chunk_c1), ("C2", chunk_c2)):
        sizes: list[int] = []
        whole = 0
        for doc in data.documents:
            chunks = chunk(doc.text, tok, SIZE, OVERLAP)
            sizes += [n_tokens(tok, c.text) for c in chunks]
            whole += sum(
                any(c.start_char <= s.start and s.end <= c.end_char for c in chunks)
                for s in spans_of[doc.id]
            )
        q = statistics.quantiles(sizes, n=20)
        print(
            f"{name}: {len(sizes):,} chunks, tokens per chunk mean {statistics.fmean(sizes):.0f},"
            f" median {statistics.median(sizes):.0f}, p5 {q[0]:.0f}, p95 {q[-1]:.0f};"
            f" dev gold spans wholly inside one chunk {whole:,} of {n_spans:,}"
            f" ({whole / n_spans:.1%})"
        )
    no_heading = with_fallback = long_tokens = all_tokens = 0
    headings: list[int] = []
    for doc in data.documents:
        token_starts = [a for a, _ in tok.encode(doc.text, add_special_tokens=False).offsets]
        cuts = heading_starts(doc.text)
        long = 0
        for a, b in pairwise([0, *cuts, len(doc.text)]):
            n = bisect_left(token_starts, b) - bisect_left(token_starts, a)
            long += n if n > SIZE else 0
        headings.append(len(cuts))
        no_heading += not cuts
        with_fallback += long > 0
        long_tokens += long
        all_tokens += len(token_starts)
    print(
        f"C2 headings per contract: median {statistics.median(headings):.0f};"
        f" contracts with none (C2 equals C1): {no_heading}"
    )
    print(
        f"C2 fallback: {with_fallback} of {len(data.documents)} contracts have a section over"
        f" {SIZE} tokens; those sections hold {long_tokens / all_tokens:.1%} of all tokens"
    )


def budget(store_path: Path, run_ids: list[str]) -> None:
    evalsets.verify(EVALSETS)
    text_of = {d.id: d.text for d in load_cuad(CUAD_ZIP).documents}
    gold = {g.query_id: g for g in evalsets.read_gold(EVALSETS, "dev")}
    with RunStore.open(store_path) as store:
        rows = [store.run(run_id) for run_id in run_ids]
        runs = [store.queries(run_id) for run_id in run_ids]
    base_ids = [q.query_id for q in runs[0]]
    for i, (row, queries) in enumerate(zip(rows, runs, strict=True)):
        if [q.query_id for q in queries] != base_ids:
            raise SystemExit(f"{row.id}: not the same queries as {rows[0].id}")
        summary = summarize(queries)
        print(
            f"[{i}] {row.id}: {row.split} {row.strategy} {row.chunker_id};"
            f" recall@5 {summary['recall@5'].mean:.3f}, MRR@10 {summary['mrr@10'].mean:.3f}"
        )
    print(f"{len(base_ids)} queries; budget in words; paired with [0]: mean delta, better, worse")
    for b in BUDGETS:
        scores: list[list[tuple[float, float]]] = []
        short: list[int] = []
        for queries in runs:
            scored: list[tuple[float, float]] = []
            unfilled = 0
            for q in queries:
                text = text_of[q.document_id]
                ranked = [RankedChunk(str(c), s, e) for c, s, e, _ in q.retrieved]
                spans = [Interval(s.start, s.end) for s in gold[q.query_id].spans]
                result = char_precision_recall_at_budget(ranked, spans, text, b, word_ends)
                if result is None:
                    raise SystemExit(f"{q.query_id} has no gold span; runs score answerable only")
                scored.append(result)
                unfilled += sum(len(word_ends(text[s:e])) for _, s, e, _ in q.retrieved) < b
            scores.append(scored)
            short.append(unfilled)
        for i, (run_scores, unfilled) in enumerate(zip(scores, short, strict=True)):
            p = statistics.fmean(s[0] for s in run_scores)
            r = statistics.fmean(s[1] for s in run_scores)
            deltas = [s[1] - t[1] for s, t in zip(run_scores, scores[0], strict=True)]
            better, worse = sum(d > 0 for d in deltas), sum(d < 0 for d in deltas)
            paired = "" if i == 0 else f"; recall {statistics.fmean(deltas):+.4f} {better} {worse}"
            print(
                f"  B={b:<5} [{i}] char precision {p:.4f}, char recall {r:.4f}"
                f" (top 10 under budget: {unfilled}){paired}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare chunkers C1 and C2 on CUAD.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("structure")
    budget_parser = commands.add_parser("budget")
    budget_parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    budget_parser.add_argument("runs", nargs="+", metavar="RUN_ID")
    args = parser.parse_args()
    if args.command == "structure":
        structure()
    else:
        budget(args.store, args.runs)


if __name__ == "__main__":
    main()
