"""The run manifest (plan step 3.6): the config hash, the config's rules, and the git state."""

import hashlib
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from ragcalibrate.harness.manifest import (
    Manifest,
    RunConfig,
    build_manifest,
    config_hash,
    git_state,
    run_row,
)

REPO = Path(__file__).resolve().parents[2]

# Every field set, so a change to any one of them can be tried.
RERANK: dict[str, object] = {
    "corpus": "cuad",
    "split": "dev",
    "strategy": "rerank",
    "chunker_id": "c1v1:bge-small-en-v1.5@5c38ec7c405e:size=256:overlap=32",
    "embedder_id": "bge-small-en-v1.5@5c38ec7c405e",
    "reranker_id": "ms-marco-MiniLM-L6-v2@233902d25c44",
    "rrf_k": 10,
    "fusion_depth": 100,
    "rerank_depth": 10,
}


def test_changing_any_one_config_value_changes_the_hash() -> None:
    base = config_hash(RunConfig.model_validate(RERANK))
    changed = {
        "chunker_id": "c2v1:bge-small-en-v1.5@5c38ec7c405e:size=256:overlap=32",
        "embedder_id": "text-embedding-3-small",
        "reranker_id": "bge-reranker-base@x",
        "rrf_k": 60,
        "fusion_depth": 50,
        "rerank_depth": 20,
    }
    hashes = {base}
    for field, value in changed.items():
        hashes.add(config_hash(RunConfig.model_validate(RERANK | {field: value})))
    hybrid = {k: v for k, v in RERANK.items() if k not in ("reranker_id", "rerank_depth")}
    hashes.add(config_hash(RunConfig.model_validate(hybrid | {"strategy": "hybrid"})))
    assert len(hashes) == len(changed) + 2  # all different from the base and from each other


def test_the_hash_depends_on_the_values_only_and_is_pinned() -> None:
    reordered = dict(reversed(RERANK.items()))
    assert config_hash(RunConfig.model_validate(reordered)) == config_hash(
        RunConfig.model_validate(RERANK)
    )
    # Pinned: a change here changes the identity of every stored experiment, so it must be made
    # on purpose (and resuming a run started before it is refused).
    canonical = (
        '{"chunker_id":"c1v1:bge-small-en-v1.5@5c38ec7c405e:size=256:overlap=32","corpus":"cuad",'
        '"embedder_id":"bge-small-en-v1.5@5c38ec7c405e","fusion_depth":100,"rerank_depth":10,'
        '"reranker_id":"ms-marco-MiniLM-L6-v2@233902d25c44","rrf_k":10,"split":"dev",'
        '"strategy":"rerank"}'
    )
    assert config_hash(RunConfig.model_validate(RERANK)) == (
        hashlib.sha256(canonical.encode()).hexdigest()
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"split": "test"}, "Input should be 'dev'"),
        ({"surprise": 1}, "Extra inputs are not permitted"),
        ({"rrf_k": "10"}, "Input should be a valid integer"),  # strict: no "10" for 10
        ({"embedder_id": None}, "embedder_id is required for dense, hybrid and rerank"),
        ({"reranker_id": None}, "reranker_id is required for rerank"),
        ({"strategy": "hybrid"}, "reranker_id is required for rerank, and only there"),
        ({"rrf_k": None}, "rerank needs rrf_k and fusion_depth"),  # the contract's rule
        ({"rerank_depth": 5}, "rerank_depth must be at least k"),  # k is 10
    ],
)
def test_a_config_must_state_what_its_strategy_uses(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        RunConfig.model_validate(RERANK | changes)


def test_fts_takes_no_model() -> None:
    fts = {"corpus": "cuad", "split": "dev", "strategy": "fts", "chunker_id": "c1"}
    RunConfig.model_validate(fts)
    with pytest.raises(ValidationError, match="embedder_id is required for dense"):
        RunConfig.model_validate(fts | {"embedder_id": "bge"})
    with pytest.raises(ValidationError, match="rrf_k and fusion_depth apply to"):
        RunConfig.model_validate(fts | {"rrf_k": 10})


def clone(tmp_path: Path) -> Path:
    # A clean checkout of this repository's commit, without changing it: --sparse checks out the
    # top-level files only, and git counts the rest as not checked out, not as deleted.
    target = tmp_path / "clone"
    subprocess.run(  # noqa: S603
        ["git", "clone", "--quiet", "--sparse", str(REPO), str(target)],  # noqa: S607
        check=True,
    )
    return target


def test_a_clean_tree_is_not_dirty_and_any_change_makes_it_dirty(tmp_path: Path) -> None:
    repo = clone(tmp_path)
    head = subprocess.run(  # noqa: S603
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert git_state(repo) == (head, False)

    (repo / "runs").mkdir()
    (repo / "runs" / "runs.sqlite").write_text("ignored")  # gitignored: the run store
    assert git_state(repo) == (head, False)

    (repo / "new.py").write_text("x = 1\n")  # untracked
    assert git_state(repo) == (head, True)
    (repo / "new.py").unlink()
    assert git_state(repo) == (head, False)

    with (repo / "Makefile").open("a") as makefile:  # tracked and changed
        makefile.write("\n")
    assert git_state(repo) == (head, True)


def test_the_manifest_round_trips_through_the_store_row(tmp_path: Path) -> None:
    repo = clone(tmp_path)
    config = RunConfig.model_validate(RERANK)
    manifest = build_manifest(
        config,
        created_at="2026-11-04T10:00:00Z",
        evalset_hash="e" * 64,
        base_url="http://127.0.0.1:8000",
        n_queries=5458,
        n_documents=408,
        repo=repo,
    )
    assert manifest.config_hash == config_hash(config)
    assert manifest.uv_lock_sha256 == hashlib.sha256((repo / "uv.lock").read_bytes()).hexdigest()
    assert manifest.k == 10
    assert not manifest.git_dirty
    row = run_row("r1", manifest)
    assert (row.strategy, row.chunker_id, row.config_hash) == (
        "rerank",
        config.chunker_id,
        manifest.config_hash,
    )
    assert Manifest.model_validate_json(row.manifest_json) == manifest
