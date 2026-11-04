"""The `ragcalibrate` command line.

`ragcalibrate run CONFIG` (plan step 3.7) runs the experiment in CONFIG, a YAML file such as
configs/s3-hybrid.yaml, on the dev split's answerable queries against a running service (`make
serve`). Each query's ranking and metrics go into the run store (runs/runs.sqlite, ADR 0003) as
soon as they are scored, and the summary printed at the end is read back from the store. A run
that stops is finished with `--resume RUN_ID`.

Run it from the repository root: the eval sets, `uv.lock` and the git state are read there.
"""

import argparse
import asyncio
import logging
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import ValidationError

from ragcalibrate import logs
from ragcalibrate.corpora import evalsets
from ragcalibrate.corpora.schema import Query
from ragcalibrate.harness.adapter import TIMEOUT, HttpSut, SutNotReady
from ragcalibrate.harness.manifest import (
    ConfigError,
    Manifest,
    RunConfig,
    build_manifest,
    config_hash,
    git_state,
    load_config,
    run_row,
)
from ragcalibrate.harness.run import QueryResult, by_category, summarize
from ragcalibrate.harness.runner import RunFailed, execute
from ragcalibrate.harness.store import RunStore, StoreError

EVALSETS = Path("evalsets")
REPO = Path(".")
DEFAULT_STORE = Path("runs/runs.sqlite")


class CannotResume(Exception):
    """The run asked for cannot be resumed with this config, eval set or code."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ragcalibrate")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run an experiment on the dev split and store it")
    run.add_argument("config", type=Path, help="experiment file, such as configs/s3-hybrid.yaml")
    run.add_argument(
        "--store", type=Path, default=DEFAULT_STORE, help=f"run store (default {DEFAULT_STORE})"
    )
    run.add_argument("--resume", metavar="RUN_ID", help="finish a stopped run: skip what it stored")
    run.add_argument("--base-url", default="http://127.0.0.1:8000")
    run.add_argument("--concurrency", type=int, default=8)
    run.add_argument(
        "--max-cost",
        type=float,
        metavar="USD",
        help="no effect until Phase 5: a retrieval run makes no paid calls",
    )
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")  # 0 would wait forever

    logs.configure_logging()
    # httpx logs every request at INFO: one line per query would bury the report.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        config = load_config(args.config)
        run_id, manifest = asyncio.run(_run(args, config))
    except ConfigError as exc:
        return _fail(str(exc), code=2)
    except SutNotReady as exc:
        hint = "the service must be running (`make serve`, after `make up` and `make ingest`)"
        return _fail(f"{exc}; {hint}, or pass --base-url")
    except (StoreError, CannotResume, RunFailed) as exc:
        return _fail(str(exc))
    except KeyboardInterrupt:
        return _fail("interrupted", code=130)
    with RunStore.open(args.store) as store:
        results = store.queries(run_id)
    _report(run_id, args.config, args.store, manifest, results)
    return 0


async def _run(args: argparse.Namespace, config: RunConfig) -> tuple[str, Manifest]:
    async with httpx.AsyncClient(base_url=args.base_url, timeout=TIMEOUT) as client:
        sut = HttpSut(client)
        await sut.check_ready()  # first: a service that is down fails here, before any work
        evalset = evalsets.verify(EVALSETS)  # the files on disk are the hashed ones
        gold = [g for g in evalsets.read_gold(EVALSETS, config.split) if g.answerable]
        wanted = {g.query_id for g in gold}
        queries = [q for q in evalsets.read_queries(EVALSETS, config.split) if q.id in wanted]
        args.store.parent.mkdir(parents=True, exist_ok=True)
        # Opening, starting and checking a run are short synchronous calls made before any
        # query is in flight, so they hold up nothing; the runner's writes go to a thread.
        with RunStore.open(args.store) as store:
            if args.resume is None:
                run_id, manifest = _start(store, config, evalset.evalset_hash, args, queries)
            else:
                run_id = args.resume
                manifest = _resumable(store, run_id, config, evalset.evalset_hash)
            sys.stderr.write(
                f"ragcalibrate: run {run_id} in {args.store}; if it stops, finish it with"
                f" `ragcalibrate run {args.config} --resume {run_id}`\n"
            )
            logs.run_id.set(run_id)  # every log line of the run carries it
            await execute(
                sut,
                store,
                run_id,
                config,
                queries,
                {g.query_id: g for g in gold},
                concurrency=args.concurrency,
            )
    return run_id, manifest


def _start(
    store: RunStore,
    config: RunConfig,
    evalset_hash: str,
    args: argparse.Namespace,
    queries: Sequence[Query],
) -> tuple[str, Manifest]:
    now = datetime.now(UTC)
    # Sortable by start time; the random part keeps two runs started in one second apart.
    run_id = f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    manifest = build_manifest(
        config,
        created_at=f"{now:%Y-%m-%dT%H:%M:%SZ}",
        evalset_hash=evalset_hash,
        base_url=args.base_url,
        n_queries=len(queries),
        n_documents=len({q.document_id for q in queries}),
        repo=REPO,
    )
    store.add_run(run_row(run_id, manifest))
    return run_id, manifest


def _resumable(store: RunStore, run_id: str, config: RunConfig, evalset_hash: str) -> Manifest:
    """The stored run's manifest, if this config, eval set and code may finish it."""
    try:
        manifest = Manifest.model_validate_json(store.run(run_id).manifest_json)
    except ValidationError as exc:
        raise CannotResume(f"run {run_id} was started by other code: {exc}") from exc
    now = (config_hash(config), evalset_hash, *git_state(REPO))
    then = (manifest.config_hash, manifest.evalset_hash, manifest.git_sha, manifest.git_dirty)
    names = ("config", "eval set", "git commit", "dirty flag")
    changed = [name for name, a, b in zip(names, now, then, strict=True) if a != b]
    # A tree dirty both times passes: the changes themselves are not compared.
    if changed:
        raise CannotResume(
            f"cannot resume run {run_id}, changed since it started: {', '.join(changed)};"
            " start a new run instead"
        )
    return manifest


def _fail(message: str, *, code: int = 1) -> int:
    # A setup problem or a stopped run, not a bug: one line each, no traceback.
    sys.stderr.write("".join(f"ragcalibrate: {line}\n" for line in message.splitlines()))
    return code


def _report(
    run_id: str, config_path: Path, store: Path, manifest: Manifest, results: list[QueryResult]
) -> None:
    c = manifest.config
    summary = summarize(results)
    lines = [
        f"run {run_id} ({config_path}), stored in {store}",
        f"{c.split} {c.strategy} {c.chunker_id}"
        + (f" {c.embedder_id}" if c.embedder_id else "")
        + (f" rrf_k={c.rrf_k} fusion_depth={c.fusion_depth}" if c.rrf_k is not None else "")
        + (f" {c.reranker_id} rerank_depth={c.rerank_depth}" if c.reranker_id else ""),
        f"{len(results)} answerable queries, {manifest.n_documents} documents;"
        f" git {manifest.git_sha[:12]}{' (dirty)' if manifest.git_dirty else ''};"
        f" evalset {manifest.evalset_hash[:12]}",
        "",
        *(f"{name:10} {mean.mean:.4f}  (n={mean.n})" for name, mean in summary.items()),
        "",
        f"{'category':40} {'n':>4} {'recall@5':>8} {'mrr@10':>7}",
        *(
            f"{category[:40]:40} {ms['recall@5'].n:4} {ms['recall@5'].mean:8.3f}"
            f" {ms['mrr@10'].mean:7.3f}"
            for category, ms in by_category(results).items()
        ),
    ]
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
