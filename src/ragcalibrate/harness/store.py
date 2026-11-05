"""The SQLite run store (plan step 3.5; Design §5.8 and §6; ADR 0003): what the harness measured.

One file holds any number of runs, so it can be uploaded as a CI artifact, diffed and queried
with any SQLite client, without a running database. Postgres holds the corpus, which belongs to
the system under test; this file belongs to the measuring instrument, and the two never mix.

- Append-only: triggers reject UPDATE and DELETE on every table, so a stored result is corrected
  only by a new run (skill EVAL-HIGH-3).
- Idempotent: a run is keyed on its id, a query's results on (run id, query id). Writing the same
  thing twice leaves one copy; writing something different under a stored key is an error, never
  a silent overwrite or a silent skip.
- One query, one transaction: its row, its ranking and its metrics are stored together or not at
  all, so a run killed midway leaves only whole queries.
- Rows are read back through Pydantic, since the file may come from other code. The schema version
  is `PRAGMA user_version`; a file with any other version is refused when opened.

Answers and judgments (Design §6) get their tables in Phases 5 and 6, with a version bump, once
the /answer response and the judge's verdicts have a shape.
"""

import math
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from ragcalibrate.harness.run import QueryResult

SCHEMA_VERSION = 1

# STRICT tables reject a value of the wrong type instead of storing it as whatever it looks like.
_SCHEMA = (
    """
    CREATE TABLE runs (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,  -- ISO 8601, UTC
        git_sha TEXT NOT NULL,
        dirty INTEGER NOT NULL CHECK (dirty IN (0, 1)),
        config_hash TEXT NOT NULL,
        evalset_hash TEXT NOT NULL,
        corpus TEXT NOT NULL,
        split TEXT NOT NULL,
        strategy TEXT NOT NULL,
        chunker_id TEXT NOT NULL,
        manifest_json TEXT NOT NULL  -- the whole manifest; the columns above repeat what a
                                     -- comparison filters on
    ) STRICT
    """,
    # Not in Design §6: one row per stored query. It marks the query as stored (a query can have
    # no retrieved chunks), and keeps its document, the paired bootstrap's cluster, in the file.
    """
    CREATE TABLE run_queries (
        run_id TEXT NOT NULL REFERENCES runs (id),
        query_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        category TEXT NOT NULL,
        PRIMARY KEY (run_id, query_id)
    ) STRICT
    """,
    """
    CREATE TABLE retrievals (
        run_id TEXT NOT NULL,
        query_id TEXT NOT NULL,
        rank INTEGER NOT NULL CHECK (rank >= 1),  -- 1 is the best
        chunk_id INTEGER NOT NULL,
        start_char INTEGER NOT NULL,
        end_char INTEGER NOT NULL,
        score REAL NOT NULL,
        PRIMARY KEY (run_id, query_id, rank),
        FOREIGN KEY (run_id, query_id) REFERENCES run_queries (run_id, query_id)
    ) STRICT
    """,
    # Long format, so a paired comparison is a join on query_id. NULL: the metric is not defined
    # for this query (no gold span, spec 3.1), which is not the same as 0.
    """
    CREATE TABLE query_metrics (
        run_id TEXT NOT NULL,
        query_id TEXT NOT NULL,
        metric TEXT NOT NULL,
        value REAL,
        PRIMARY KEY (run_id, query_id, metric),
        FOREIGN KEY (run_id, query_id) REFERENCES run_queries (run_id, query_id)
    ) STRICT
    """,
    *(
        f"""
        CREATE TRIGGER {table}_no_{op.lower()} BEFORE {op} ON {table}
        BEGIN SELECT RAISE(ABORT, 'the run store is append-only'); END
        """
        for table in ("runs", "run_queries", "retrievals", "query_metrics")
        for op in ("UPDATE", "DELETE")
    ),
    "PRAGMA user_version = 1",  # SCHEMA_VERSION; a test checks that the two agree
)


class StoreError(Exception):
    """The store cannot do what was asked: wrong file, wrong version, or a conflicting write."""


class Run(BaseModel):
    """One row of `runs`. `manifest_json` is stored as given; the code that builds the manifest
    parses it back."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    created_at: str
    git_sha: str
    dirty: bool
    config_hash: str
    evalset_hash: str
    corpus: str
    split: str
    strategy: str
    chunker_id: str
    manifest_json: str


class RunStore:
    """An open store. Close it (or use `with`): the file is complete, with no WAL file beside
    it, only once the last connection is closed.

    Not safe for concurrent use: any thread may call it, but one at a time (the runner holds a
    lock around each call and makes it from a worker thread, off the event loop)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, path: Path) -> Self:
        """Open the store at `path`, creating it if the file is missing or empty."""
        # autocommit=True: no implicit transactions; every write is in an explicit one below.
        # check_same_thread=False: calls come from asyncio.to_thread's workers, serialized.
        conn = sqlite3.connect(path, autocommit=True, check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            # WAL: a reader (a comparison) does not block the run that is writing (DB-HIGH-4).
            conn.execute("PRAGMA journal_mode = WAL")
            store = cls(conn)
            store._prepare(path)
        except BaseException:
            conn.close()
            raise
        return store

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def add_run(self, run: Run) -> None:
        """Store `run`. The same run again is a no-op; a different one under its id is an error."""
        with self._transaction():
            stored = self._run(run.id)
            if stored is None:
                self._conn.execute(
                    "INSERT INTO runs (id, created_at, git_sha, dirty, config_hash, evalset_hash,"
                    " corpus, split, strategy, chunker_id, manifest_json) VALUES (:id,"
                    " :created_at, :git_sha, :dirty, :config_hash, :evalset_hash, :corpus, :split,"
                    " :strategy, :chunker_id, :manifest_json)",
                    run.model_dump(),
                )
            elif stored != run:
                raise StoreError(f"run {run.id!r} is already stored with different values")

    def add_query(self, run_id: str, result: QueryResult) -> None:
        """Store one query's results for a stored run, in one transaction. The same results again
        are a no-op; different results for a stored query are an error."""
        values = [score for *_, score in result.retrieved]
        values += [v for v in result.metrics.values() if v is not None]
        if not all(math.isfinite(v) for v in values):
            # SQLite stores NaN as NULL, which would read back as "not defined": refuse it here.
            raise StoreError(f"query {result.query_id!r} has a score or metric that is not finite")
        key = (run_id, result.query_id)
        with self._transaction():
            stored = self._query(*key)
            if stored is not None:
                if stored != result:
                    raise StoreError(
                        f"query {result.query_id!r} of run {run_id!r} is already stored with"
                        " different results"
                    )
                return
            self._conn.execute(
                "INSERT INTO run_queries (run_id, query_id, document_id, category)"
                " VALUES (?, ?, ?, ?)",
                (*key, result.document_id, result.category),
            )
            self._conn.executemany(
                "INSERT INTO retrievals (run_id, query_id, rank, chunk_id, start_char, end_char,"
                " score) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(*key, rank, *chunk) for rank, chunk in enumerate(result.retrieved, start=1)],
            )
            self._conn.executemany(
                "INSERT INTO query_metrics (run_id, query_id, metric, value) VALUES (?, ?, ?, ?)",
                [(*key, name, value) for name, value in result.metrics.items()],
            )

    def run(self, run_id: str) -> Run:
        run = self._run(run_id)
        if run is None:
            raise StoreError(f"no run {run_id!r} in the store")
        return run

    def run_ids(self) -> set[str]:
        """The ids of every stored run."""
        return {str(row["id"]) for row in self._conn.execute("SELECT id FROM runs")}

    def query_ids(self, run_id: str) -> set[str]:
        """The ids of the run's stored queries: what a resumed run skips."""
        self.run(run_id)  # an unknown run is an error, not an empty run
        rows = self._conn.execute("SELECT query_id FROM run_queries WHERE run_id = ?", (run_id,))
        return {str(row["query_id"]) for row in rows}

    def queries(self, run_id: str) -> list[QueryResult]:
        """The run's stored queries, sorted by query id."""
        self.run(run_id)  # an unknown run is an error, not an empty run
        heads = self._conn.execute(
            "SELECT query_id, document_id, category FROM run_queries WHERE run_id = ?"
            " ORDER BY query_id",
            (run_id,),
        ).fetchall()
        return [self._read(run_id, head) for head in heads]

    def _prepare(self, path: Path) -> None:
        with self._transaction():
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                return
            if version == 0:
                if self._conn.execute("SELECT count(*) FROM sqlite_schema").fetchone()[0]:
                    raise StoreError(f"{path} is a SQLite file but not a run store")
                for statement in _SCHEMA:
                    self._conn.execute(statement)
                return
            # No silent migration of a file that holds past results (database rules,
            # DB-CRITICAL-1): a forward step is written when a version is added.
            raise StoreError(
                f"{path} is run-store schema version {version}; this code reads version"
                f" {SCHEMA_VERSION} only. Open it with the code that wrote it, or use a new store."
            )

    @contextmanager
    def _transaction(self) -> Generator[None]:
        # IMMEDIATE takes the write lock at once, so a check made before an insert holds until
        # the commit, even with another process writing the same file.
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def _run(self, run_id: str) -> Run | None:
        row = self._conn.execute(
            "SELECT id, created_at, git_sha, dirty, config_hash, evalset_hash, corpus, split,"
            " strategy, chunker_id, manifest_json FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        return None if row is None else Run.model_validate(dict(row))

    def _query(self, run_id: str, query_id: str) -> QueryResult | None:
        head = self._conn.execute(
            "SELECT query_id, document_id, category FROM run_queries"
            " WHERE run_id = ? AND query_id = ?",
            (run_id, query_id),
        ).fetchone()
        return None if head is None else self._read(run_id, head)

    def _read(self, run_id: str, head: sqlite3.Row) -> QueryResult:
        """A stored query's results, from its `run_queries` row."""
        key = (run_id, head["query_id"])
        retrieved = self._conn.execute(
            "SELECT chunk_id, start_char, end_char, score FROM retrievals"
            " WHERE run_id = ? AND query_id = ? ORDER BY rank",
            key,
        )
        # rowid order is the order the metrics were written in, so reports list them the same way.
        metrics = self._conn.execute(
            "SELECT metric, value FROM query_metrics WHERE run_id = ? AND query_id = ?"
            " ORDER BY rowid",
            key,
        )
        return QueryResult.model_validate(
            {
                "query_id": head["query_id"],
                "document_id": head["document_id"],
                "category": head["category"],
                "retrieved": [tuple(row) for row in retrieved],
                "metrics": {row["metric"]: row["value"] for row in metrics},
            }
        )
