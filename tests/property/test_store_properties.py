"""Run store round trip (plan step 3.5): any results written come back unchanged after reopening."""

import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from ragcalibrate.harness.run import QueryResult
from ragcalibrate.harness.store import Run, RunStore

INT64 = st.integers(min_value=-(2**63), max_value=2**63 - 1)
FINITE = st.floats(allow_nan=False, allow_infinity=False)

results = st.builds(
    QueryResult,
    query_id=st.text(min_size=1),
    document_id=st.text(),
    category=st.text(),
    retrieved=st.lists(st.tuples(INT64, INT64, INT64, FINITE), max_size=12),
    metrics=st.dictionaries(st.text(), st.none() | FINITE, max_size=6),
)

RUN = Run(
    id="r",
    created_at="2026-11-04T10:00:00Z",
    git_sha="0" * 40,
    dirty=False,
    config_hash="c",
    evalset_hash="e",
    corpus="cuad",
    split="dev",
    strategy="dense",
    chunker_id="c1",
    manifest_json="{}",
)


@given(st.lists(results, max_size=8, unique_by=lambda r: r.query_id))
def test_results_read_back_after_reopening_equal_what_was_written(
    written: list[QueryResult],
) -> None:
    # A fresh directory per example: Hypothesis reruns the body, and pytest's tmp_path is shared.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "runs.sqlite"
        with RunStore.open(path) as store:
            store.add_run(RUN)
            for result in written:
                store.add_query(RUN.id, result)
        with RunStore.open(path) as store:
            read = store.queries(RUN.id)
            assert store.run(RUN.id) == RUN
    # Sorted by Python's string order, which is code point order, as SQLite's BINARY collation.
    assert read == sorted(written, key=lambda r: r.query_id)
    for got, want in zip(read, sorted(written, key=lambda r: r.query_id), strict=True):
        assert list(got.metrics) == list(want.metrics)  # same order, not only equal
