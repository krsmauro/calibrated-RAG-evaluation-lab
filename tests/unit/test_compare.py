"""Comparing two runs (plan step 4.4), against hand-computed answers.

The values are binary fractions (0.75, 0.6875, ...), so every sum and mean below is exact in
floating point. When every document has the same mean difference, every bootstrap resample has
that mean too, so the interval is that single value and the gate's outcome follows by hand.
"""

from collections.abc import Mapping, Sequence

import pytest

from ragcalibrate.report.compare import (
    MIN_DOCUMENTS,
    PRIMARY,
    SEED,
    NotComparable,
    StoredRun,
    compare,
    render_html,
    render_markdown,
)
from ragcalibrate.stats.gate import Outcome


def stored(
    values: Mapping[str, float | None] | Sequence[Mapping[str, float | None]],
    *,
    run_id: str = "base",
    documents: int = MIN_DOCUMENTS,
    strategy: str = "fts",
    chunker_id: str = "c1",
    evalset_hash: str = "e" * 64,
    split: str = "dev",
) -> StoredRun:
    """A run with two queries per document; `values` is every query's metrics, or a list
    giving each query's in turn."""
    queries = [f"q{i:03}" for i in range(2 * documents)]
    per_query = [values] * len(queries) if isinstance(values, Mapping) else list(values)
    return StoredRun(
        id=run_id,
        split=split,
        strategy=strategy,
        chunker_id=chunker_id,
        git_sha="a" * 40,
        dirty=False,
        evalset_hash=evalset_hash,
        config_hash="c" * 64,
        metrics=dict(zip(queries, per_query, strict=True)),
        document_of={q: f"d{i // 2:03}" for i, q in enumerate(queries)},
    )


def test_a_regression_past_delta_fails() -> None:
    result = compare(stored({PRIMARY: 0.75}), stored({PRIMARY: 0.6875}, run_id="cand"))
    [row] = result.rows
    assert (row.baseline, row.candidate, row.difference) == (0.75, 0.6875, -0.0625)
    assert row.interval is not None
    assert (row.interval.lo, row.interval.hi) == (-0.0625, -0.0625)
    assert (row.interval.seed, row.interval.n_clusters) == (SEED, MIN_DOCUMENTS)
    assert (row.outcome, row.note) == (Outcome.FAIL, "")
    assert (row.n_queries, row.n_documents) == (2 * MIN_DOCUMENTS, MIN_DOCUMENTS)


def test_a_regression_smaller_than_delta_passes_with_a_note() -> None:
    # -1/64 = -0.015625 is above -delta (-0.02), and the whole interval is below zero.
    [row] = compare(stored({PRIMARY: 0.75}), stored({PRIMARY: 0.734375})).rows
    assert (row.outcome, row.note) == (Outcome.PASS, "small regression detected")


def test_identical_runs_pass() -> None:
    [row] = compare(stored({PRIMARY: 0.5}), stored({PRIMARY: 0.5})).rows
    assert row.interval is not None
    assert (row.difference, row.interval.lo, row.interval.hi) == (0.0, 0.0, 0.0)
    assert (row.outcome, row.note) == (Outcome.PASS, "")


def test_means_are_over_the_paired_queries() -> None:
    # Per document: baseline 1 and 0, candidate 1 and 1, so the difference is 0.5 everywhere.
    base = stored([{PRIMARY: 1.0}, {PRIMARY: 0.0}] * MIN_DOCUMENTS)
    cand = stored({PRIMARY: 1.0})
    [row] = compare(base, cand).rows
    assert (row.baseline, row.candidate, row.difference) == (0.5, 1.0, 0.5)
    assert row.interval is not None
    assert (row.interval.lo, row.interval.hi) == (0.5, 0.5)
    assert row.outcome is Outcome.PASS


def test_below_the_minimum_of_documents_it_is_inconclusive_without_an_interval() -> None:
    few = MIN_DOCUMENTS - 1
    base, cand = stored({PRIMARY: 0.75}, documents=few), stored({PRIMARY: 0.5}, documents=few)
    [row] = compare(base, cand).rows
    assert row.interval is None
    assert row.difference == -0.25  # still shown
    assert row.outcome is Outcome.INCONCLUSIVE
    assert row.note == f"{few} documents, fewer than {MIN_DOCUMENTS} (F-003)"
    assert row.n_documents == few


def test_a_chunker_change_gets_no_outcome() -> None:
    base, cand = stored({PRIMARY: 0.75}), stored({PRIMARY: 0.5}, chunker_id="c2")
    [row] = compare(base, cand).rows
    assert row.interval is not None  # the interval is still worth seeing
    assert row.outcome is None
    assert "chunkers differ" in row.note and "D8" in row.note


def test_only_the_primary_metric_gates_and_it_comes_first() -> None:
    values = {"hit@1": 0.0, PRIMARY: 0.5, "mrr@10": 0.25}
    rows = compare(stored(values), stored({"hit@1": 1.0, PRIMARY: 0.5, "mrr@10": 0.0})).rows
    assert [r.metric for r in rows] == [PRIMARY, "hit@1", "mrr@10"]
    assert [r.outcome for r in rows] == [Outcome.PASS, None, None]
    assert rows[1].note == rows[2].note == "secondary, does not gate"
    assert [r.difference for r in rows] == [0.0, 1.0, -0.25]


def test_undefined_values_are_left_out_and_counted() -> None:
    per_query: list[Mapping[str, float | None]] = [{PRIMARY: 1.0, "mrr@10": 0.5}] * (
        2 * MIN_DOCUMENTS
    )
    per_query[0] = {PRIMARY: 1.0, "mrr@10": None}  # undefined in the baseline only
    rows = compare(stored(per_query), stored({PRIMARY: 1.0, "mrr@10": 0.25})).rows
    assert (rows[1].metric, rows[1].n_queries, rows[1].n_documents) == (
        "mrr@10",
        2 * MIN_DOCUMENTS - 1,
        MIN_DOCUMENTS,
    )
    assert (rows[1].baseline, rows[1].candidate) == (0.5, 0.25)


def test_different_eval_sets_or_splits_are_refused_unless_forced() -> None:
    base = stored({PRIMARY: 0.5})
    other = stored({PRIMARY: 0.5}, run_id="cand", evalset_hash="f" * 64, split="test")
    with pytest.raises(NotComparable, match=r"differ in eval set .*; split dev and test.*--force"):
        compare(base, other)
    assert compare(base, other, force=True).rows[0].outcome is Outcome.PASS


def test_runs_with_different_queries_are_refused_with_counts() -> None:
    base = stored({PRIMARY: 0.5})
    shorter = stored({PRIMARY: 0.5}, documents=MIN_DOCUMENTS - 1)
    with pytest.raises(NotComparable, match="2 only in the baseline, 0 only in the candidate"):
        compare(base, shorter)


def test_a_query_in_another_document_is_refused() -> None:
    base = stored({PRIMARY: 0.5})
    moved = base._replace(document_of={**base.document_of, "q000": "elsewhere"})
    with pytest.raises(NotComparable, match="1 queries belong to other documents"):
        compare(base, moved)


def test_the_primary_metric_must_be_in_both_runs() -> None:
    with pytest.raises(NotComparable, match="recall@5 is not defined in both runs"):
        compare(stored({"hit@1": 1.0}), stored({"hit@1": 1.0}))


def test_markdown_shows_every_number_with_its_n() -> None:
    base = stored({PRIMARY: 0.75, "mrr@10": 0.5})
    cand = stored({PRIMARY: 0.6875, "mrr@10": 0.5}, run_id="cand", strategy="dense")
    lines = render_markdown([compare(base, cand)]).splitlines()
    assert "| baseline | base | dev | fts | c1 | aaaaaaa | eeeeeeeeeeee | cccccccccccc |" in lines
    assert "## Candidate 1: dense (cand) against fts (base)" in lines
    header = "| metric | baseline | candidate | delta | 95% CI | outcome | queries | documents |"
    assert header in lines
    assert (
        "| recall@5 (primary) | 0.7500 | 0.6875 | -0.0625 | [-0.0625, -0.0625] | fail | 80 | 40 |"
        in lines
    )
    assert (
        "| mrr@10 | 0.5000 | 0.5000 | +0.0000 | [+0.0000, +0.0000] | secondary, does not gate"
        " | 80 | 40 |" in lines
    )
    assert f"seed {SEED}" in lines[2]


def test_markdown_says_when_no_interval_was_computed() -> None:
    few = MIN_DOCUMENTS - 1
    text = render_markdown(
        [compare(stored({PRIMARY: 0.5}, documents=few), stored({PRIMARY: 0.5}, documents=few))]
    )
    assert "| not computed | inconclusive, 39 documents, fewer than 40 (F-003) | 78 | 39 |" in text


def test_html_has_the_same_tables_and_escapes_text() -> None:
    base = stored({PRIMARY: 0.5})
    cands = [stored({PRIMARY: 0.5}, run_id=f"c{i}", strategy="<b>x</b>") for i in (1, 2)]
    page = render_html([compare(base, c) for c in cands])
    assert page.startswith("<!DOCTYPE html>")
    assert page.count("<table>") == 3  # the runs, then one per candidate
    assert "&lt;b&gt;x&lt;/b&gt;" in page and "<b>x</b>" not in page
    assert "<td>recall@5 (primary)</td><td>0.5000</td>" in page
