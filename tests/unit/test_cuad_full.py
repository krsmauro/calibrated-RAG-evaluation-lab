"""Whole-dataset checks. Skipped when `make data` has not been run (CI does not download CUAD)."""

from pathlib import Path

import pytest

from ragcalibrate.corpora.cuad import load_cuad

ZIP = Path(__file__).parents[2] / "data" / "raw" / "cuad" / "data.zip"

pytestmark = pytest.mark.skipif(not ZIP.exists(), reason="run `make data` first")


def test_full_cuad_matches_the_measured_facts() -> None:
    # Numbers are from finding F-008; load_cuad itself raises on any label/text mismatch.
    data = load_cuad(ZIP)
    assert len(data.documents) == 510
    assert len(data.queries) == 20_910
    assert sum(len(g.spans) for g in data.gold) == 13_823
    for split, docs, queries, answerable in (
        ("dev", 408, 16_728, 5_458),
        ("test", 102, 4_182, 1_244),
    ):
        q, g = data.split(split)  # type: ignore[arg-type]
        assert len({x.document_id for x in q}) == docs
        assert len(q) == queries
        assert sum(x.answerable for x in g) == answerable
