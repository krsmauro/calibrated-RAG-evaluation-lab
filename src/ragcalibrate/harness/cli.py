"""The `ragcalibrate` command line.

`ragcalibrate run` (plan step 2.10, minimal): sends the dev split's answerable queries to a
running service (`make serve`), scores them, prints the summary and writes a JSON result with
per-query metrics and the facts needed to regenerate it. Phase 3 replaces the JSON file with the
SQLite run store and the flags with a versioned experiment YAML.
"""

import argparse
import asyncio
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel

from ragcalibrate.contract import Strategy
from ragcalibrate.corpora import evalsets
from ragcalibrate.corpora.schema import Split
from ragcalibrate.harness.adapter import TIMEOUT, HttpSut
from ragcalibrate.harness.run import (
    K_VALUES,
    MRR_K,
    Mean,
    QueryResult,
    by_category,
    retrieve_all,
    score,
    summarize,
)
from ragcalibrate.logs import configure_logging

EVALSETS = Path("evalsets")
# The chunker `make ingest` loads (scripts/ingest.py). An experiment parameter, not a service
# internal: the harness names it, the service looks it up. Experiment YAML replaces this (3.7).
DEFAULT_CHUNKER = "c1v1:bge-small-en-v1.5@5c38ec7c405e:size=256:overlap=32"
CORPUS = "cuad"
STRATEGY: Strategy = "dense"  # the only one until plan phase 3


class Manifest(BaseModel):
    created_at: str
    git_sha: str
    git_dirty: bool
    evalset_hash: str
    corpus: str
    split: str
    strategy: str
    chunker_id: str
    embedder_id: str | None
    k: int
    base_url: str
    n_queries: int
    n_documents: int


class RunResult(BaseModel):
    manifest: Manifest
    summary: dict[str, Mean]
    by_category: dict[str, dict[str, Mean]]
    queries: list[QueryResult]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ragcalibrate")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="score retrieval on the dev split's answerable queries")
    # Only dev: the test split is run once per frozen configuration (plan step 4.8), not ad hoc.
    run.add_argument("--split", choices=["dev"], default="dev")
    run.add_argument("--chunker-id", default=DEFAULT_CHUNKER)
    run.add_argument("--base-url", default="http://127.0.0.1:8000")
    run.add_argument("--concurrency", type=int, default=8)
    run.add_argument("--out", type=Path, help="JSON result path (default: runs/<time>.json)")
    args = parser.parse_args(argv)

    configure_logging()
    result = asyncio.run(_run(args.split, args.chunker_id, args.base_url, args.concurrency))
    out: Path = args.out or Path("runs") / f"{result.manifest.created_at.replace(':', '')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=1) + "\n", encoding="utf-8")
    _report(result, out)
    return 0


async def _run(split: Split, chunker_id: str, base_url: str, concurrency: int) -> RunResult:
    manifest = evalsets.verify(EVALSETS)  # the files on disk are the hashed ones
    gold = [g for g in evalsets.read_gold(EVALSETS, split) if g.answerable]
    wanted = {g.query_id for g in gold}
    queries = [q for q in evalsets.read_queries(EVALSETS, split) if q.id in wanted]
    gold_of = {g.query_id: g for g in gold}
    k = max(*K_VALUES, MRR_K)
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT) as client:
        responses = await retrieve_all(
            HttpSut(client),
            queries,
            corpus=CORPUS,
            strategy=STRATEGY,
            chunker_id=chunker_id,
            k=k,
            concurrency=concurrency,
        )
    embedders = {r.embedder_id for r in responses}
    if len(embedders) != 1:
        raise RuntimeError(f"the service used more than one embedder in one run: {embedders}")
    results = [score(r, gold_of[q.id]) for q, r in zip(queries, responses, strict=True)]
    sha, dirty = _git_state()
    return RunResult(
        manifest=Manifest(
            created_at=created_at,
            git_sha=sha,
            git_dirty=dirty,
            evalset_hash=manifest.evalset_hash,
            corpus=CORPUS,
            split=split,
            strategy=STRATEGY,
            chunker_id=chunker_id,
            embedder_id=embedders.pop(),
            k=k,
            base_url=base_url,
            n_queries=len(results),
            n_documents=len({r.document_id for r in results}),
        ),
        summary=summarize(results),
        by_category=by_category(results),
        queries=results,
    )


def _git_state() -> tuple[str, bool]:
    # Fixed arguments, no user input; git from PATH is how every contributor runs it.
    def git(*args: str) -> str:
        done = subprocess.run(["git", *args], capture_output=True, text=True, check=True)  # noqa: S603, S607
        return done.stdout.strip()

    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def _report(result: RunResult, out: Path) -> None:
    m = result.manifest
    lines = [
        f"{m.split} {m.strategy} {m.chunker_id} {m.embedder_id}",
        f"{m.n_queries} answerable queries, {m.n_documents} documents; "
        f"git {m.git_sha[:12]}{' (dirty)' if m.git_dirty else ''}; evalset {m.evalset_hash[:12]}",
        "",
        *(f"{name:10} {mean.mean:.4f}  (n={mean.n})" for name, mean in result.summary.items()),
        "",
        f"{'category':40} {'n':>4} {'recall@5':>8} {'mrr@10':>7}",
        *(
            f"{category[:40]:40} {ms['recall@5'].n:4} {ms['recall@5'].mean:8.3f}"
            f" {ms['mrr@10'].mean:7.3f}"
            for category, ms in result.by_category.items()
        ),
        "",
        f"wrote {out}",
    ]
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
