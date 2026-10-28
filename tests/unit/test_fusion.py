"""Reciprocal Rank Fusion (plan step 3.2) against hand-computed fixtures."""

import pytest

from ragcalibrate.contract import RetrievedChunk
from ragcalibrate.service.fusion import rrf


def chunk(chunk_id: int, start: int, score: float = 0.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id, start_char=start, end_char=start + 10, text="x" * 10, score=score
    )


A, B, C, D = chunk(1, 0, 9.0), chunk(2, 100, 8.0), chunk(3, 200, 7.0), chunk(4, 300, 0.5)


def fused(result: list[RetrievedChunk]) -> list[tuple[int, float]]:
    return [(c.chunk_id, c.score) for c in result]


def test_two_rankings_by_hand() -> None:
    # rrf_k = 60. A is 1st and 3rd, B 2nd and 1st, C only 3rd, D only 2nd:
    # B = 1/61 + 1/62 = 123/3782 > A = 1/61 + 1/63 = 124/3843 > D = 1/62 > C = 1/63.
    result = rrf([[A, B, C], [B, D, A]], rrf_k=60, k=10)
    assert [c.chunk_id for c in result] == [2, 1, 4, 3]
    assert [c.score for c in result] == pytest.approx([123 / 3782, 124 / 3843, 1 / 62, 1 / 63])
    # Offsets and text come through unchanged; the input scores are not used.
    assert (result[0].start_char, result[0].end_char, result[0].text) == (100, 110, "x" * 10)


def test_only_the_k_best_are_returned() -> None:
    assert [c.chunk_id for c in rrf([[A, B, C], [B, D, A]], rrf_k=60, k=2)] == [2, 1]


def test_equal_scores_are_ordered_by_position_in_the_document() -> None:
    # rrf_k = 0: A = 1/1 + 1/2 and B = 1/2 + 1/1 tie at 1.5. B starts earlier, so B comes first,
    # although A is first in the first ranking.
    late_a = chunk(1, 500)
    assert fused(rrf([[late_a, B], [B, late_a]], rrf_k=0, k=10)) == [(2, 1.5), (1, 1.5)]


def test_an_empty_side_leaves_the_other_ranking_as_it_is() -> None:
    # S1 returns nothing when no chunk shares a word with the query.
    assert fused(rrf([[], [B, A]], rrf_k=60, k=10)) == [(2, 1 / 61), (1, 1 / 62)]
    assert rrf([[], []], rrf_k=60, k=10) == []
    assert rrf([], rrf_k=60, k=10) == []


def test_a_chunk_listed_twice_in_one_ranking_counts_once_at_its_first_position() -> None:
    assert fused(rrf([[A, B, A]], rrf_k=60, k=10)) == [(1, 1 / 61), (2, 1 / 62)]
