"""The run manifest (plan step 3.6; Design §8.6; skill EVAL-HIGH-2): what a run was, fixed at its
start, so that its numbers can be regenerated.

A manifest holds the experiment's config, whose hash is the experiment's identity; the eval set's
hash; the harness's commit and whether the tree had changes; the hash of the locked dependencies;
and the machine. The config names every model, and the runner refuses a response that reports
another (step 3.7), so the record does not rest on the service's defaults.

Not recorded: RNG seeds, since a retrieval run draws no random numbers (the bootstrap records its
own in Phase 4); and the code the service was started from, which the contract does not report,
so a `make serve` started before a change keeps serving the old code unnoticed.
"""

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from ragcalibrate.contract import RetrieveRequest, Strategy
from ragcalibrate.harness.run import K
from ragcalibrate.harness.store import Run


class RunConfig(BaseModel):
    """One experiment: the settings sent to the system under test, and the eval set to run.

    Every setting the strategy uses must be stated, and nothing else may be, so the hash covers
    all that decides the results and no setting that has no effect.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    corpus: Literal["cuad"]
    # Only dev: the test split is run once per frozen configuration (plan step 4.8), not ad hoc.
    split: Literal["dev"]
    strategy: Strategy
    chunker_id: str
    # The models, as the service names them in its responses. The embedder is sent with each
    # request; the request cannot choose the reranker, so its id is only checked.
    embedder_id: str | None = None
    reranker_id: str | None = None
    rrf_k: int | None = None
    fusion_depth: int | None = None
    rerank_depth: int | None = None

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if (self.strategy == "fts") == (self.embedder_id is not None):
            raise ValueError("embedder_id is required for dense, hybrid and rerank, and only there")
        if (self.strategy == "rerank") != (self.reranker_id is not None):
            raise ValueError("reranker_id is required for rerank, and only there")
        # The contract's own rules for which parameters a strategy takes, so they live in one place.
        self.request(query="config check", doc_id="config check")
        return self

    def request(self, query: str, doc_id: str) -> RetrieveRequest:
        return RetrieveRequest(
            query=query,
            corpus=self.corpus,
            doc_id=doc_id,
            strategy=self.strategy,
            chunker_id=self.chunker_id,
            embedder_id=self.embedder_id,
            k=K,
            rrf_k=self.rrf_k,
            fusion_depth=self.fusion_depth,
            rerank_depth=self.rerank_depth,
        )


class ConfigError(Exception):
    """An experiment file that cannot be read or is not a valid config; one line per problem."""


def load_config(path: Path) -> RunConfig:
    """Read an experiment file (YAML, plan step 3.7). `safe_load` only: a config builds no
    Python objects."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read it ({exc.strerror})") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: not valid YAML ({exc})") from exc
    try:
        return RunConfig.model_validate(data)
    except ValidationError as exc:
        lines = [
            f"{path}: {'.'.join(map(str, e['loc'])) or 'config'}: "
            + e["msg"].removeprefix("Value error, ")
            for e in exc.errors()
        ]
        raise ConfigError("\n".join(lines)) from exc


def config_hash(config: RunConfig) -> str:
    """sha256 of the config as canonical JSON: the same settings give the same hash, however the
    file that held them was written. A test pins one value; changing how this is computed changes
    every experiment's identity."""
    canonical = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class Hardware(BaseModel):
    """The machine the harness ran on (the service ran on the same one in every run so far)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    platform: str
    machine: str
    cpus: int | None
    python: str


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    created_at: str  # when the run started, ISO 8601 UTC
    config: RunConfig
    config_hash: str
    evalset_hash: str
    git_sha: str
    git_dirty: bool
    uv_lock_sha256: str
    hardware: Hardware
    k: int
    base_url: str
    n_queries: int
    n_documents: int


def git_state(repo: Path) -> tuple[str, bool]:
    """The commit checked out in `repo`, and whether the tree differs from it. Untracked files
    count as a difference; ignored ones (the run store in runs/, data/) do not."""

    # Fixed arguments, no user input; git from PATH is how every contributor runs it.
    def git(*args: str) -> str:
        done = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo), *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        return done.stdout.strip()

    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def build_manifest(
    config: RunConfig,
    *,
    created_at: str,
    evalset_hash: str,
    base_url: str,
    n_queries: int,
    n_documents: int,
    repo: Path,
) -> Manifest:
    sha, dirty = git_state(repo)
    return Manifest(
        created_at=created_at,
        config=config,
        config_hash=config_hash(config),
        evalset_hash=evalset_hash,
        git_sha=sha,
        git_dirty=dirty,
        uv_lock_sha256=hashlib.sha256((repo / "uv.lock").read_bytes()).hexdigest(),
        hardware=Hardware(
            platform=platform.platform(),
            machine=platform.machine(),
            cpus=os.cpu_count(),
            python=platform.python_version(),
        ),
        k=K,
        base_url=base_url,
        n_queries=n_queries,
        n_documents=n_documents,
    )


def run_row(run_id: str, manifest: Manifest) -> Run:
    """The store's row for a run: the manifest whole, and the fields a comparison filters on."""
    return Run(
        id=run_id,
        created_at=manifest.created_at,
        git_sha=manifest.git_sha,
        dirty=manifest.git_dirty,
        config_hash=manifest.config_hash,
        evalset_hash=manifest.evalset_hash,
        corpus=manifest.config.corpus,
        split=manifest.config.split,
        strategy=manifest.config.strategy,
        chunker_id=manifest.config.chunker_id,
        manifest_json=manifest.model_dump_json(),
    )
