"""`ragcalibrate run` (plan step 3.7): readable failures, a stored run, and resuming one."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from ragcalibrate.contract import RetrievedChunk, RetrieveRequest, RetrieveResponse
from ragcalibrate.corpora.schema import Gold, GoldSpan, Query, Split
from ragcalibrate.harness import cli
from ragcalibrate.harness.adapter import HttpSut, SutError, SutNotReady
from ragcalibrate.harness.store import RunStore

REPO = Path(__file__).resolve().parents[2]
S3 = str(REPO / "configs" / "s3-hybrid.yaml")
QUERIES = [Query(id=f"q{i}", document_id=f"d{i % 2}", text=f"question {i}") for i in range(10)]
GOLD = [
    Gold(
        query_id=q.id,
        document_id=q.document_id,
        category="c",
        spans=(GoldSpan(start=0, end=5, text="....."),),
    )
    for q in QUERIES
]


def answer(request: RetrieveRequest) -> RetrieveResponse:
    chunks = [
        RetrievedChunk(chunk_id=i, start_char=10 * i, end_char=10 * i + 10, text="x" * 10, score=-i)
        for i in range(request.k)
    ]
    return RetrieveResponse(
        strategy=request.strategy,
        chunker_id=request.chunker_id,
        embedder_id=request.embedder_id,
        reranker_id=None,
        chunks=chunks,
    )


def test_run_stops_with_one_line_when_the_service_is_not_ready(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    async def down(self: HttpSut) -> None:
        raise SutNotReady("cannot reach http://127.0.0.1:8000/ (ConnectError)")

    monkeypatch.setattr(HttpSut, "check_ready", down)
    # The check runs first, so this needs neither a service nor the eval-set files.
    assert cli.main(["run", S3, "--store", str(tmp_path / "runs.sqlite")]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("ragcalibrate: cannot reach http://127.0.0.1:8000/ (ConnectError)")
    assert "make serve" in err
    assert len(err.splitlines()) == 1
    assert not (tmp_path / "runs.sqlite").exists()  # nothing written for a run that never began


def test_a_bad_config_gets_one_readable_line_per_problem(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    config = tmp_path / "bad.yaml"
    config.write_text("corpus: cuad\nsplit: test\nstrategy: hybrid\nchunker_id: c1\nk: 5\n")
    assert cli.main(["run", str(config)]) == 2
    assert capsys.readouterr().err.splitlines() == [
        f"ragcalibrate: {config}: split: Input should be 'dev'",
        f"ragcalibrate: {config}: k: Extra inputs are not permitted",
    ]
    assert cli.main(["run", str(tmp_path / "missing.yaml")]) == 2
    assert "cannot read it (No such file or directory)" in capsys.readouterr().err
    config.write_text("corpus: [cuad\n")
    assert cli.main(["run", str(config)]) == 2
    assert "not valid YAML" in capsys.readouterr().err


def test_a_concurrency_below_one_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["run", S3, "--concurrency", "0"])
    assert stopped.value.code == 2
    assert "--concurrency must be at least 1" in capsys.readouterr().err


def test_a_stopped_run_is_resumed_only_with_its_own_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    async def ready(self: HttpSut) -> None:
        pass

    calls = {"n": 0, "fail_on": 7}

    async def retrieve(self: HttpSut, request: RetrieveRequest) -> RetrieveResponse:
        calls["n"] += 1
        if calls["n"] == calls["fail_on"]:
            raise SutError(400, "bad_request", "planted")
        return answer(request)

    def read_gold(directory: Path, split: Split) -> list[Gold]:
        return GOLD

    def read_queries(directory: Path, split: Split) -> list[Query]:
        return QUERIES

    monkeypatch.setattr(HttpSut, "check_ready", ready)
    monkeypatch.setattr(HttpSut, "retrieve", retrieve)
    monkeypatch.setattr(cli.evalsets, "verify", lambda _: SimpleNamespace(evalset_hash="e" * 64))
    monkeypatch.setattr(cli.evalsets, "read_gold", read_gold)
    monkeypatch.setattr(cli.evalsets, "read_queries", read_queries)
    monkeypatch.setattr(cli, "REPO", REPO)
    store = str(tmp_path / "runs.sqlite")

    assert cli.main(["run", S3, "--store", store, "--concurrency", "1"]) == 1
    err = capsys.readouterr().err
    found = re.search(r"--resume (\S+)`", err)
    assert found
    run_id = found.group(1)
    assert "ragcalibrate: RunFailed" not in err
    assert err.splitlines()[-1] == "ragcalibrate: SutError: 400 bad_request: planted"

    s4 = str(REPO / "configs" / "s4-rerank.yaml")
    assert cli.main(["run", s4, "--store", store, "--resume", run_id]) == 1
    refused = capsys.readouterr().err
    assert f"cannot resume run {run_id}, changed since it started: config;" in refused

    calls["fail_on"] = 0
    assert cli.main(["run", S3, "--store", store, "--resume", run_id]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"run {run_id} ({S3}), stored in {store}\n")
    assert f"{len(QUERIES)} answerable queries, 2 documents" in out
    with RunStore.open(Path(store)) as opened:
        assert len(opened.queries(run_id)) == len(QUERIES)
        assert opened.run(run_id).strategy == "hybrid"
