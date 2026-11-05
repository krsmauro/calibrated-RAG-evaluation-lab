"""`ragcalibrate compare` (plan step 4.4): runs read from a store, a report out, one-line errors."""

from pathlib import Path

import pytest

from ragcalibrate.harness import cli
from ragcalibrate.harness.run import QueryResult
from ragcalibrate.harness.store import Run, RunStore

DOCUMENTS = 40


def add(store: RunStore, run_id: str, recall: float, *, evalset_hash: str = "e" * 64) -> None:
    store.add_run(
        Run(
            id=run_id,
            created_at="2026-11-05T00:00:00Z",
            git_sha="a" * 40,
            dirty=False,
            config_hash="c" * 64,
            evalset_hash=evalset_hash,
            corpus="cuad",
            split="dev",
            strategy="fts",
            chunker_id="c1",
            manifest_json="{}",
        )
    )
    for i in range(DOCUMENTS):
        store.add_query(
            run_id,
            QueryResult(
                query_id=f"q{i:02}",
                document_id=f"d{i:02}",
                category="c",
                retrieved=[],
                metrics={"recall@5": recall, "mrr@10": None},
            ),
        )


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    path = tmp_path / "runs.sqlite"
    with RunStore.open(path) as store:
        add(store, "base", 0.75)
        add(store, "cand", 0.6875)
        add(store, "other-evalset", 0.75, evalset_hash="f" * 64)
    return path


def test_compare_prints_markdown_and_writes_html(
    store_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "report.html"
    argv = ["compare", "base", "cand", "--store", str(store_path), "--html", str(page)]
    assert cli.main(argv) == 0
    out, err = capsys.readouterr()
    row = "| recall@5 (primary) | 0.7500 | 0.6875 | -0.0625 | [-0.0625, -0.0625] | fail | 40 | 40 |"
    assert row in out.splitlines()
    assert "mrr@10" not in out  # undefined in every query: no row, rather than a mean of nothing
    assert err == f"ragcalibrate: wrote {page}\n"
    assert "<td>fail</td>" in page.read_text()


def test_an_unknown_run_is_one_line(store_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["compare", "base", "nope", "--store", str(store_path)]) == 1
    assert capsys.readouterr() == ("", "ragcalibrate: no run 'nope' in the store\n")


def test_a_missing_store_is_not_created(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "none.sqlite"
    assert cli.main(["compare", "a", "b", "--store", str(missing)]) == 1
    assert capsys.readouterr().err == f"ragcalibrate: no run store at {missing}\n"
    assert not missing.exists()


def test_another_eval_set_needs_force(store_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["compare", "base", "other-evalset", "--store", str(store_path)]
    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1 and "--force" in err
    assert cli.main([*argv, "--force"]) == 0


def test_an_html_path_that_cannot_be_written_is_one_line(
    store_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "no-such-folder" / "report.html"
    argv = ["compare", "base", "cand", "--store", str(store_path), "--html", str(page)]
    assert cli.main(argv) == 1
    out, err = capsys.readouterr()
    assert "| recall@5 (primary) |" in out  # the Markdown report was printed before
    assert err == f"ragcalibrate: cannot write {page} (No such file or directory)\n"
