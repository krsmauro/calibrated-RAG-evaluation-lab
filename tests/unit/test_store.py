"""The SQLite run store (plan step 3.5): idempotent, append-only, read back unchanged."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from ragcalibrate.harness.run import QueryResult
from ragcalibrate.harness.store import SCHEMA_VERSION, Run, RunStore, StoreError


def make_run(run_id: str = "r1", **changes: object) -> Run:
    values: dict[str, object] = {
        "id": run_id,
        "created_at": "2026-11-04T10:00:00Z",
        "git_sha": "fef341d" + "0" * 33,
        "dirty": True,
        "config_hash": "c" * 64,
        "evalset_hash": "e" * 64,
        "corpus": "cuad",
        "split": "dev",
        "strategy": "rerank",
        "chunker_id": "c1v1:x",
        "manifest_json": '{"k": 10, "rerank_depth": 10}',
    }
    return Run.model_validate(values | changes)


def make_result(query_id: str = "q1", **changes: object) -> QueryResult:
    values: dict[str, object] = {
        "query_id": query_id,
        "document_id": "doc-a",
        "category": "Governing Law",
        # A cross-encoder logit, a score with every digit used, and the score of a tie.
        "retrieved": [(7, 0, 50, -1.2345678901234567), (8, 110, 200, 0.1 + 0.2), (9, 0, 9, 0.0)],
        "metrics": {"hit@1": 0.0, "recall@5": 2 / 3, "mrr@10": 0.5, "abstain": None},
    }
    return QueryResult.model_validate(values | changes)


def raw(path: Path) -> closing[sqlite3.Connection]:
    """A plain connection to the file, outside the store's code."""
    return closing(sqlite3.connect(path, autocommit=True))


def count(path: Path, table: str) -> int:
    with raw(path) as conn:
        # Table names come from the tests themselves, not from input.
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "runs.sqlite"


def test_a_new_store_has_the_current_schema_version(path: Path) -> None:
    RunStore.open(path).close()
    with raw(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_writing_the_same_run_and_query_twice_leaves_one_copy(path: Path) -> None:
    with RunStore.open(path) as store:
        for _ in range(2):
            store.add_run(make_run())
            store.add_query("r1", make_result())
    with RunStore.open(path) as store:  # and again after reopening the file
        store.add_run(make_run())
        store.add_query("r1", make_result())
    assert count(path, "runs") == 1
    assert count(path, "run_queries") == 1
    assert count(path, "retrievals") == 3
    assert count(path, "query_metrics") == 4


def test_reopening_the_file_reads_back_identical_data(path: Path) -> None:
    runs = [make_run("r1"), make_run("r2", dirty=False, strategy="fts")]
    results = [
        make_result("q2"),
        make_result("q1", document_id="doc-b"),
        # Postgres FTS can return nothing for a query: stored, with an empty ranking.
        make_result("q3", retrieved=[], metrics={"recall@5": 0.0}),
    ]
    with RunStore.open(path) as store:
        for run in runs:
            store.add_run(run)
        for result in results:
            store.add_query("r1", result)
        store.add_query("r2", results[0])

    with RunStore.open(path) as store:
        assert [store.run("r1"), store.run("r2")] == runs
        read = store.queries("r1")
        assert read == sorted(results, key=lambda r: r.query_id)
        # Bit for bit, not just equal, and in the order the metrics were written.
        assert [r.model_dump_json() for r in read] == [
            r.model_dump_json() for r in sorted(results, key=lambda r: r.query_id)
        ]
        assert store.queries("r2") == [results[0]]
        assert store.query_ids("r1") == {"q1", "q2", "q3"}
        assert store.query_ids("r2") == {"q2"}


def test_different_values_under_a_stored_key_are_refused_and_the_first_kept(path: Path) -> None:
    first = make_result()
    with RunStore.open(path) as store:
        store.add_run(make_run())
        store.add_query("r1", first)
        with pytest.raises(StoreError, match="already stored with different values"):
            store.add_run(make_run(config_hash="d" * 64))
        changed_score = [(7, 0, 50, -1.2345678901234567), (8, 110, 200, 0.3), (9, 0, 9, 0.0)]
        with pytest.raises(StoreError, match="already stored with different results"):
            store.add_query("r1", make_result(retrieved=changed_score))
        with pytest.raises(StoreError, match="already stored with different results"):
            store.add_query("r1", make_result(metrics={"hit@1": 1.0}))
        assert store.run("r1") == make_run()
        assert store.queries("r1") == [first]


def test_a_schema_version_mismatch_fails_loudly(path: Path) -> None:
    RunStore.open(path).close()
    with raw(path) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(StoreError, match=f"schema version {SCHEMA_VERSION + 1}; this code reads"):
        RunStore.open(path)


def test_a_sqlite_file_that_is_not_a_run_store_is_refused(path: Path) -> None:
    with raw(path) as conn:
        conn.execute("CREATE TABLE notes (text TEXT)")
    with pytest.raises(StoreError, match="not a run store"):
        RunStore.open(path)
    with raw(path) as conn:  # and left as it was
        assert conn.execute("SELECT name FROM sqlite_schema").fetchall() == [("notes",)]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE runs SET dirty = 0",
        "DELETE FROM runs",
        "UPDATE run_queries SET category = 'x'",
        "DELETE FROM run_queries",
        "UPDATE retrievals SET score = 1.0",
        "DELETE FROM retrievals",
        "UPDATE query_metrics SET value = 1.0",
        "DELETE FROM query_metrics",
    ],
)
def test_stored_rows_cannot_be_changed_or_deleted(path: Path, statement: str) -> None:
    with RunStore.open(path) as store:
        store.add_run(make_run())
        store.add_query("r1", make_result())
    with raw(path) as conn, pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(statement)


def test_a_failed_write_stores_nothing_of_that_query(path: Path) -> None:
    too_big = 2**63  # does not fit SQLite's INTEGER: fails after the query's first rows went in
    with RunStore.open(path) as store:
        store.add_run(make_run())
        with pytest.raises(OverflowError):
            store.add_query("r1", make_result(retrieved=[(1, 0, 5, 0.5), (too_big, 0, 5, 0.4)]))
        assert store.queries("r1") == []
        store.add_query("r1", make_result())  # the key is free: nothing half-written holds it
        assert store.queries("r1") == [make_result()]


@pytest.mark.parametrize(
    "changes",
    [
        {"metrics": {"recall@5": float("nan")}},  # would read back as NULL, "not defined"
        {"metrics": {"recall@5": float("inf")}},
        {"retrieved": [(1, 0, 5, float("nan"))]},
        {"retrieved": [(1, 0, 5, float("-inf"))]},
    ],
)
def test_values_that_are_not_finite_are_refused(path: Path, changes: dict[str, object]) -> None:
    with RunStore.open(path) as store:
        store.add_run(make_run())
        with pytest.raises(StoreError, match="not finite"):
            store.add_query("r1", make_result("q1", **changes))
        assert store.queries("r1") == []


def test_run_ids_lists_every_stored_run(path: Path) -> None:
    with RunStore.open(path) as store:
        assert store.run_ids() == set()
        store.add_run(make_run("r1"))
        store.add_run(make_run("r2"))
        store.add_query("r1", make_result())
        assert store.run_ids() == {"r1", "r2"}


def test_a_query_needs_a_stored_run(path: Path) -> None:
    with RunStore.open(path) as store:
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            store.add_query("r1", make_result())
        with pytest.raises(StoreError, match="no run 'r1'"):
            store.run("r1")
        with pytest.raises(StoreError, match="no run 'r1'"):
            store.queries("r1")
        with pytest.raises(StoreError, match="no run 'r1'"):
            store.query_ids("r1")


def test_a_closed_store_is_one_file(path: Path) -> None:
    # A CI artifact is the .sqlite file alone: nothing may be left in a WAL file beside it.
    with RunStore.open(path) as store:
        store.add_run(make_run())
        store.add_query("r1", make_result())
        assert path.with_name(path.name + "-wal").exists()
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]
