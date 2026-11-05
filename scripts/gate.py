"""Gate the working tree against the merge base, locally (plan step 4.7a; Design §8.5; D9).

Runs one experiment config on all of dev twice. The baseline runs at the merge base of BASE
(default main) and HEAD, in a temporary git worktree, with that commit's own service and
harness. The candidate is the working tree as it is, uncommitted changes included. Both runs
go into the run store and are compared as `ragcalibrate compare` does; the Markdown report it
prints is what the PR comment will carry (step 4.7b).

Exit code: 0 for a Pass, and for no verdict (Inconclusive, or no outcome because the chunkers
differ, D8), which is neutral; 1 for a Fail; 2 when the gate could not run. `--outcome FILE`
writes the verdict as one word, pass, fail, inconclusive or none, so the GitHub Action (step
4.7b) can tell a Pass from a neutral result; when the gate cannot run, the file is not written.

Each side gets its own service, started here on its own port from its own tree, so a `make
serve` left running from before a change never answers for either side. Both services read the
one Postgres index, and the gate does not ingest: a change to chunking has to change the chunker
id and be loaded first (`make ingest`), or both sides read the same chunks.

Needs `make up`, `make models`, `make ingest` and `make evalsets`. The services' and runs' output
goes to runs/gate-*.log.
Usage: uv run python scripts/gate.py [CONFIG] [--base REF] [--store PATH] [--outcome FILE]
       (or `make gate`)
"""

# Every subprocess here is git or uv from PATH, as every contributor runs them, with arguments
# from this command line (a config path, a git ref): nothing from outside the user's own shell.
# ruff: noqa: S603, S607

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from ragcalibrate.harness.cli import DEFAULT_STORE, stored_run
from ragcalibrate.harness.store import RunStore, StoreError
from ragcalibrate.report.compare import NotComparable, compare, render_markdown
from ragcalibrate.stats.gate import Outcome

ROOT = Path.cwd()  # the repository root, as for `ragcalibrate`
PORTS = {"base": 8101, "candidate": 8102}
READY_TIMEOUT = 300  # seconds: a fresh worktree's first `uv run` installs its environment
LOGS = Path("runs")  # gitignored, like the run store
# Each tree runs in its own environment: `uv run` from this script would otherwise see this
# environment's VIRTUAL_ENV and warn that it does not match the tree's own.
ENV = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}


class GateError(Exception):
    """The gate could not run to a verdict."""


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


@contextmanager
def base_tree(sha: str, path: Path) -> Iterator[Path]:
    """A worktree at `sha` that can run: links to the models, the CUAD zip and .env, and its
    own eval-set files (gitignored, so a worktree has none), built from the pinned zip."""
    git("worktree", "add", "--detach", str(path), sha)
    try:
        # A real data/ directory, so the `data/` ignore rule matches it: a link named data
        # would be untracked, and the base run would be recorded as made on a dirty tree.
        (path / "data").mkdir()
        for name in ("raw", "models"):
            (path / "data" / name).symlink_to(ROOT / "data" / name)
        (path / ".env").symlink_to(ROOT / ".env")
        build = ["uv", "run", "python", "scripts/build_evalsets.py"]
        done = subprocess.run(build, cwd=path, env=ENV, capture_output=True, text=True)
        if done.returncode != 0:
            raise GateError(f"cannot build the eval sets at {sha[:12]}: {done.stdout}{done.stderr}")
        yield path
    finally:
        git("worktree", "remove", "--force", str(path))


@contextmanager
def service(tree: Path, side: str) -> Iterator[str]:
    """The service of `tree` on its own port, until the block ends."""
    port = PORTS[side]
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            # Something already answering there would be taken for this tree's service.
            raise GateError(f"port {port} is in use; stop what listens there")
    url = f"http://127.0.0.1:{port}"
    log = ROOT / LOGS / f"gate-{side}.log"
    log.parent.mkdir(exist_ok=True)
    command = ["uv", "run", "uvicorn", "ragcalibrate.service.app:create_app", "--factory"]
    command += ["--host", "127.0.0.1", "--port", str(port)]
    with log.open("w") as out:
        process = subprocess.Popen(command, cwd=tree, env=ENV, stdout=out, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + READY_TIMEOUT
            while not _ready(url):
                if process.poll() is not None:
                    raise GateError(f"the {side} service exited ({process.returncode}); see {log}")
                if time.monotonic() > deadline:
                    raise GateError(f"the {side} service is not ready after {READY_TIMEOUT} s")
                time.sleep(1)
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def _ready(url: str) -> bool:
    try:
        return httpx.get(f"{url}/readyz", timeout=2).status_code == 200
    except httpx.TransportError:
        return False


def run(tree: Path, config: Path, url: str, store: Path, side: str) -> str:
    """Run `config` with `tree`'s harness against `url`; the id of the run it stored."""
    with RunStore.open(store) as s:
        before = s.run_ids()
    command = ["uv", "run", "ragcalibrate", "run", str(config), "--base-url", url]
    command += ["--store", str(store)]
    log = ROOT / LOGS / f"gate-{side}-run.log"
    print(f"gate: {side} run of {config} in {tree}, log {log}", file=sys.stderr, flush=True)
    with log.open("w") as out:
        done = subprocess.run(
            command, cwd=tree, env=ENV, stdout=out, stderr=subprocess.STDOUT, check=False
        )
    if done.returncode != 0:
        raise GateError(f"the {side} run failed (exit {done.returncode}); see {log}")
    with RunStore.open(store) as s:
        new = s.run_ids() - before
    if len(new) != 1:
        raise GateError(f"expected one new run in {store} after the {side} run, found {len(new)}")
    return new.pop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate the working tree against the merge base.")
    parser.add_argument("config", type=Path, nargs="?", default=Path("configs/s3-hybrid.yaml"))
    parser.add_argument("--base", default="main", help="branch or commit to gate against")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--outcome", type=Path, help="write the verdict here as one word")
    args = parser.parse_args()
    store = args.store.resolve()  # the base run writes here from another directory
    if args.outcome is not None:
        args.outcome.unlink(missing_ok=True)  # no verdict from an earlier gate survives this one
    try:
        if not args.config.is_file():
            raise GateError(f"no config {args.config}")
        sha = git("merge-base", args.base, "HEAD")
        print(f"gate: baseline at {sha[:12]} (merge base of {args.base} and HEAD)", file=sys.stderr)
        with (
            tempfile.TemporaryDirectory(prefix="ragcalibrate-gate-") as tmp,
            base_tree(sha, Path(tmp) / "base") as tree,
        ):
            if not (tree / args.config).is_file():
                raise GateError(f"{args.config} does not exist at {sha[:12]}: no baseline")
            with service(tree, "base") as url:
                baseline = run(tree, args.config, url, store, "base")
        with service(ROOT, "candidate") as url:
            candidate = run(ROOT, args.config, url, store, "candidate")
        with RunStore.open(store) as s:
            comparison = compare(stored_run(s, baseline), stored_run(s, candidate))
    except (GateError, NotComparable, StoreError) as exc:
        print(f"gate: cannot decide: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(render_markdown([comparison]))
    primary = comparison.rows[0]  # the primary metric comes first
    verdict = primary.outcome.value if primary.outcome is not None else "no outcome"
    print(f"gate: {verdict}{f' ({primary.note})' if primary.note else ''}", file=sys.stderr)
    if args.outcome is not None:
        args.outcome.write_text(f"{primary.outcome.value if primary.outcome else 'none'}\n")
    return 1 if primary.outcome is Outcome.FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
