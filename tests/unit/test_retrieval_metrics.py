"""Known-answer tests for the retrieval metrics. Every expected value is worked out by hand.

Spans and chunks are half-open [start, end). The shared fixture:
    gold spans   S1 = [10, 20)   S2 = [50, 60)
    c1 = [0, 10)    touches S1's start but overlaps nothing (half-open)
    c2 = [15, 30)   overlaps S1 by 5 characters
    c3 = [55, 70)   overlaps S2 by 5 characters
    c4 = [18, 52)   overlaps S1 by 2 ([18,20)) and S2 by 2 ([50,52))
"""

import re

import pytest

from ragcalibrate.harness.metrics.retrieval import (
    Interval,
    RankedChunk,
    char_precision_recall_at_budget,
    dedupe,
    hit_at_k,
    merge_spans,
    mrr_at_k,
    overlap,
    recall_at_k,
)

S1, S2 = Interval(10, 20), Interval(50, 60)
GOLD = [S1, S2]
C1, C2 = RankedChunk("c1", 0, 10), RankedChunk("c2", 15, 30)
C3, C4 = RankedChunk("c3", 55, 70), RankedChunk("c4", 18, 52)


def test_overlap_is_half_open() -> None:
    assert overlap(Interval(0, 10), Interval(10, 20)) == 0  # adjacent, not overlapping
    assert overlap(Interval(15, 30), Interval(10, 20)) == 5
    assert overlap(Interval(0, 100), Interval(10, 20)) == 10  # containment
    assert overlap(Interval(30, 40), Interval(10, 20)) == 0  # disjoint, no negative values


def test_merge_spans_merges_overlaps_only() -> None:
    assert merge_spans([Interval(15, 30), Interval(10, 20)]) == [Interval(10, 30)]
    assert merge_spans([Interval(10, 20), Interval(20, 30)]) == [Interval(10, 20), Interval(20, 30)]
    assert merge_spans([Interval(0, 100), Interval(10, 20)]) == [Interval(0, 100)]
    assert merge_spans([]) == []


def test_dedupe_keeps_first_occurrence_and_its_rank() -> None:
    assert dedupe([C1, C2, C2, C3]) == [C1, C2, C3]


@pytest.mark.parametrize(
    ("k", "hit", "recall", "mrr"),
    [
        (1, 0.0, 0.0, 0.0),  # c1 overlaps nothing
        (2, 1.0, 0.5, 0.5),  # c2 at rank 2 hits S1 only
        (3, 1.0, 1.0, 0.5),  # c3 adds S2
        (10, 1.0, 1.0, 0.5),  # k beyond the list: use what was returned, never pad
    ],
)
def test_r1_metrics_on_the_shared_fixture(k: int, hit: float, recall: float, mrr: float) -> None:
    ranked = [C1, C2, C3]
    assert hit_at_k(ranked, GOLD, k) == hit
    assert recall_at_k(ranked, GOLD, k) == recall
    assert mrr_at_k(ranked, GOLD, k) == mrr


def test_one_chunk_covering_two_spans_counts_both() -> None:
    assert recall_at_k([C4], GOLD, 1) == 1.0
    assert mrr_at_k([C1, C4], GOLD, 5) == 0.5


def test_duplicate_chunk_does_not_push_later_results_down() -> None:
    # Without dedupe c3 would sit at rank 4 and recall@3 would be 0.5.
    assert recall_at_k([C1, C2, C2, C3], GOLD, 3) == 1.0
    assert mrr_at_k([C1, C1, C3], [S2], 2) == 0.5


def test_gold_span_split_across_two_chunks_counts_once() -> None:
    left, right = RankedChunk("l", 5, 14), RankedChunk("r", 14, 25)
    assert recall_at_k([left, right], [S1], 2) == 1.0
    assert recall_at_k([right], [S1], 1) == 1.0  # either half is enough under R1


def test_overlapping_gold_spans_are_merged_before_counting() -> None:
    gold = [Interval(10, 20), Interval(15, 30)]  # one clause labeled twice
    chunk = RankedChunk("x", 25, 29)  # touches only the second label
    assert recall_at_k([chunk], gold, 1) == 1.0  # unmerged this would be 0.5


def test_no_gold_spans_is_undefined_not_zero() -> None:
    assert hit_at_k([C2], [], 5) is None
    assert recall_at_k([C2], [], 5) is None
    assert mrr_at_k([C2], [], 5) is None


def test_empty_result_list_scores_zero() -> None:
    assert hit_at_k([], GOLD, 5) == 0.0
    assert recall_at_k([], GOLD, 5) == 0.0
    assert mrr_at_k([], GOLD, 5) == 0.0


def test_r2_uses_half_of_the_shorter_of_span_and_chunk() -> None:
    # S1 has length 10; c2 overlaps it by 5 and needs 0.5 * min(10, 15) = 5: relevant.
    assert recall_at_k([C2], [S1], 1, min_overlap_frac=0.5) == 1.0
    # c4 overlaps S1 by only 2 (needs 0.5 * min(10, 34) = 5): relevant under R1, not under R2.
    assert recall_at_k([C4], [S1], 1) == 1.0
    assert recall_at_k([C4], [S1], 1, min_overlap_frac=0.5) == 0.0
    # A long span stays reachable: 100 of 1000 characters is half of the shorter (the chunk).
    assert (
        recall_at_k([RankedChunk("a", 0, 100)], [Interval(0, 1000)], 1, min_overlap_frac=0.5) == 1.0
    )


def _word_ends(text: str) -> list[int]:
    return [m.end() for m in re.finditer(r"\S+", text)]


# Words of 4 letters separated by single spaces: word i occupies [5i, 5i + 4).
DOC = "aaaa bbbb cccc dddd eeee ffff gggg hhhh"
CHAR_GOLD = [Interval(10, 14), Interval(30, 34)]  # "cccc" and "gggg": 8 gold characters
W1, W2 = RankedChunk("w1", 0, 14), RankedChunk("w2", 10, 24)  # "aaaa bbbb cccc", "cccc dddd eeee"


def test_char_metrics_cut_the_crossing_chunk_at_a_token_boundary() -> None:
    # B=4: w1 gives 3 tokens, [0,14); w2 gets 1 token left, cut after "cccc": [10,14).
    # Ret = [0,14), 14 characters; Ret and Gold share [10,14), 4 characters.
    result = char_precision_recall_at_budget([W1, W2], CHAR_GOLD, DOC, 4, _word_ends)
    assert result == (4 / 14, 4 / 8)


def test_char_metrics_count_a_doubly_covered_character_once() -> None:
    # B=6: Ret = [0,14) union [10,24) = [0,24), 24 characters (not 28); shared with Gold: 4.
    result = char_precision_recall_at_budget([W1, W2], CHAR_GOLD, DOC, 6, _word_ends)
    assert result == (4 / 24, 4 / 8)


def test_char_metrics_edge_cases() -> None:
    assert char_precision_recall_at_budget([], CHAR_GOLD, DOC, 4, _word_ends) == (0.0, 0.0)
    assert char_precision_recall_at_budget([W1], [], DOC, 4, _word_ends) is None
    # Duplicate chunk ids are dropped before the budget is spent.
    assert char_precision_recall_at_budget([W1, W1], CHAR_GOLD, DOC, 6, _word_ends) == (
        4 / 14,
        4 / 8,
    )
