"""Scoring and averaging in the minimal run (plan step 2.10), with hand-computed values."""

from ragcalibrate.contract import RetrievedChunk, RetrieveResponse
from ragcalibrate.corpora.schema import Gold, GoldSpan
from ragcalibrate.harness.run import Mean, QueryResult, by_category, score, summarize


def chunk(chunk_id: int, start: int, end: int, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id, start_char=start, end_char=end, text="x" * (end - start), score=score
    )


def test_score_one_query_by_hand() -> None:
    # Two gold spans. Rank 1 misses both, rank 2 overlaps span A, rank 3 overlaps span B.
    gold = Gold(
        query_id="q",
        document_id="d",
        category="Governing Law",
        spans=(
            GoldSpan(start=100, end=120, text="a" * 20),
            GoldSpan(start=300, end=310, text="b" * 10),
        ),
    )
    response = RetrieveResponse(
        strategy="dense",
        chunker_id="c",
        embedder_id="e",
        reranker_id=None,
        chunks=[chunk(7, 0, 50, 0.9), chunk(8, 110, 200, 0.8), chunk(9, 305, 400, 0.7)],
    )
    result = score(response, gold)
    assert result.metrics == {
        "hit@1": 0.0, "recall@1": 0.0,
        "hit@3": 1.0, "recall@3": 1.0,
        "hit@5": 1.0, "recall@5": 1.0,
        "hit@10": 1.0, "recall@10": 1.0,
        "mrr@10": 0.5,
    }  # fmt: skip
    assert result.retrieved[1] == (8, 110, 200, 0.8)


def result(category: str, recall: float | None) -> QueryResult:
    return QueryResult(
        query_id=f"{category}{recall}",
        document_id="d",
        category=category,
        retrieved=[],
        metrics={"recall@5": recall},
    )


def test_means_exclude_undefined_values_and_split_by_category() -> None:
    results = [result("A", 1.0), result("A", 0.0), result("B", 0.5), result("B", None)]
    # Overall: (1 + 0 + 0.5) / 3; the None (no gold span) is excluded, not counted as zero.
    assert summarize(results) == {"recall@5": Mean(mean=0.5, n=3)}
    assert by_category(results) == {
        "A": {"recall@5": Mean(mean=0.5, n=2)},
        "B": {"recall@5": Mean(mean=0.5, n=1)},
    }
