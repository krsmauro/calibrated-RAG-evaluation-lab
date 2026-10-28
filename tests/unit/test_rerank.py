"""S4 (plan step 3.3): reordering by scores, hand-computed; the cross-encoder, once downloaded.

The model tests skip until `make models` has been run.
"""

from pathlib import Path

import numpy as np
import pytest

from ragcalibrate.contract import RetrievedChunk
from ragcalibrate.service.rerank import Reranker, rerank

MODEL_DIR = Path(__file__).parents[2] / "data" / "models" / "ms-marco-MiniLM-L6-v2"
needs_model = pytest.mark.skipif(
    not (MODEL_DIR / "onnx" / "model.onnx").exists(), reason="run `make models` first"
)

QUESTION = (
    'Highlight the parts (if any) of this contract related to "Governing Law" that should be '
    "reviewed by a lawyer. Details: Which state/country's law governs the interpretation of the "
    "contract?"
)
CLAUSES = [
    "This Agreement shall be governed by the laws of the State of New York.",
    "The Licensee shall pay a royalty of five percent of net sales each quarter.",
    "Either party may terminate this Agreement on ninety days written notice.",
]


def chunk(chunk_id: int, start: int) -> RetrievedChunk:
    # The incoming score is the hybrid's; reranking must replace it, not combine with it.
    return RetrievedChunk(
        chunk_id=chunk_id, start_char=start, end_char=start + 10, text="x" * 10, score=0.01
    )


A, B, C, D = chunk(1, 0), chunk(2, 100), chunk(3, 50), chunk(4, 50)


def test_best_score_first_with_new_scores_and_ties_in_document_order() -> None:
    # B scores highest. A and C tie at 0.5: A starts earlier, so A first. D is cut by k.
    result = rerank([A, B, C, D], [0.5, 2.0, 0.5, -1.0], k=3)
    assert [(c.chunk_id, c.score) for c in result] == [(2, 2.0), (1, 0.5), (3, 0.5)]


def test_a_tie_at_the_same_position_falls_back_to_chunk_id() -> None:
    assert [c.chunk_id for c in rerank([D, C], [1.0, 1.0], k=2)] == [3, 4]


def test_the_order_of_the_candidates_does_not_matter() -> None:
    scores = {1: 0.5, 2: 2.0, 3: 0.5, 4: 0.5}
    for candidates in ([A, B, C, D], [D, C, B, A], [C, A, D, B]):
        result = rerank(candidates, [scores[c.chunk_id] for c in candidates], k=4)
        assert [c.chunk_id for c in result] == [2, 1, 3, 4]


def test_fewer_candidates_than_k_returns_them_all_and_none_returns_none() -> None:
    assert [c.chunk_id for c in rerank([A, B], [0.0, 1.0], k=10)] == [2, 1]
    assert rerank([], [], k=10) == []


def test_one_score_per_candidate() -> None:
    with pytest.raises(ValueError, match="zip"):
        rerank([A, B], [1.0], k=2)


@pytest.fixture(scope="module")
def reranker() -> Reranker:
    return Reranker(MODEL_DIR, batch_size=2)


@needs_model
def test_matches_the_reference_implementation(reranker: Reranker) -> None:
    # sentence-transformers 6.2.0 (torch 2.15.0) CrossEncoder on the same pinned commit, recorded
    # in ADR 0013. The ONNX path differed by at most 1.1e-5 on 197 CUAD pairs.
    reference = [-4.151086, -9.274020, -8.356949]
    np.testing.assert_allclose(reranker.score(QUESTION, CLAUSES), reference, atol=1e-4)


@needs_model
def test_same_input_twice_gives_the_same_scores(reranker: Reranker) -> None:
    texts = [*CLAUSES, "x " * 600]  # the last pair is longer than the context and is cut
    assert reranker.score(QUESTION, texts) == reranker.score(QUESTION, texts)


@needs_model
def test_batching_does_not_change_scores_beyond_float_noise(reranker: Reranker) -> None:
    # Padded next to a longer neighbour, a pair's arithmetic changes slightly: measured at most
    # 2.4e-6 on 197 CUAD pairs (ADR 0013).
    texts = ["short", "a much longer clause " * 30, *CLAUSES]
    alone = [reranker.score(QUESTION, [t])[0] for t in texts]
    np.testing.assert_allclose(reranker.score(QUESTION, texts), alone, atol=1e-4)


@needs_model
def test_no_texts_gives_no_scores(reranker: Reranker) -> None:
    assert reranker.score(QUESTION, []) == []
