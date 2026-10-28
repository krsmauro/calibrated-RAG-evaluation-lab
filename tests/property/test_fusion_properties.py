"""Reciprocal Rank Fusion invariants (plan step 3.2, Design §9): ties, order, duplicates, gaps."""

from hypothesis import given
from hypothesis import strategies as st

from ragcalibrate.contract import RetrievedChunk
from ragcalibrate.service.fusion import rrf

rrf_ks = st.integers(0, 100)
ks = st.integers(1, 15)


@st.composite
def rankings(draw: st.DrawFn, max_lists: int = 4) -> list[list[RetrievedChunk]]:
    """Rankings over one pool of chunks: unique within a ranking, shared across rankings.

    Few distinct start positions, so equal fused scores and equal positions both occur.
    """
    n = draw(st.integers(0, 12))
    pool = [
        RetrievedChunk(chunk_id=i, start_char=s, end_char=s + 5, text="x", score=0.0)
        for i, s in enumerate(draw(st.lists(st.integers(0, 4), min_size=n, max_size=n)))
    ]
    ranking = (
        st.lists(st.sampled_from(pool), unique_by=lambda c: c.chunk_id) if pool else st.just([])
    )
    return draw(st.lists(ranking, max_size=max_lists))


def ids(result: list[RetrievedChunk]) -> list[int]:
    return [c.chunk_id for c in result]


@given(lists=rankings(), rrf_k=rrf_ks, k=ks)
def test_best_first_ties_by_position_unique_and_at_most_k(
    lists: list[list[RetrievedChunk]], rrf_k: int, k: int
) -> None:
    result = rrf(lists, rrf_k=rrf_k, k=k)
    order = [(-c.score, c.start_char, c.chunk_id) for c in result]
    assert order == sorted(order)
    assert len(set(ids(result))) == len(result)
    assert len(result) == min(k, len({c.chunk_id for r in lists for c in r}))


@given(data=st.data(), lists=rankings(), rrf_k=rrf_ks, k=ks)
def test_the_order_of_the_rankings_does_not_matter(
    data: st.DataObject, lists: list[list[RetrievedChunk]], rrf_k: int, k: int
) -> None:
    shuffled = data.draw(st.permutations(lists))
    assert rrf(shuffled, rrf_k=rrf_k, k=k) == rrf(lists, rrf_k=rrf_k, k=k)


@given(lists=rankings(max_lists=1), rrf_k=rrf_ks, k=ks)
def test_one_ranking_alone_or_fused_with_itself_keeps_its_order(
    lists: list[list[RetrievedChunk]], rrf_k: int, k: int
) -> None:
    ranking = lists[0] if lists else []
    expected = ids(ranking)[:k]
    assert ids(rrf([ranking], rrf_k=rrf_k, k=k)) == expected
    assert ids(rrf([ranking, []], rrf_k=rrf_k, k=k)) == expected  # an empty side
    assert ids(rrf([ranking, ranking], rrf_k=rrf_k, k=k)) == expected  # every chunk in both


@given(lists=rankings(), rrf_k=rrf_ks)
def test_repeating_a_chunk_later_in_its_ranking_changes_nothing(
    lists: list[list[RetrievedChunk]], rrf_k: int
) -> None:
    repeated = [r + r[:1] for r in lists]
    assert rrf(repeated, rrf_k=rrf_k, k=100) == rrf(lists, rrf_k=rrf_k, k=100)


@given(lists=rankings(), rrf_k=rrf_ks, position=st.integers(0, 4))
def test_a_new_chunk_at_the_end_of_a_ranking_does_not_reorder_the_others(
    lists: list[list[RetrievedChunk]], rrf_k: int, position: int
) -> None:
    if not lists:
        lists = [[]]
    new = RetrievedChunk(
        chunk_id=999, start_char=position, end_char=position + 5, text="x", score=0.0
    )
    before = rrf(lists, rrf_k=rrf_k, k=100)
    after = rrf([*lists[:-1], [*lists[-1], new]], rrf_k=rrf_k, k=100)
    assert [c for c in after if c.chunk_id != new.chunk_id] == before
