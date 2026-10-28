"""The local embedder. Skipped until `make models` has been run."""

from pathlib import Path

import numpy as np
import pytest

from ragcalibrate.ingest.embedding import DIMENSION, Embedder

MODEL_DIR = Path(__file__).parents[2] / "data" / "models" / "bge-small-en-v1.5"

pytestmark = pytest.mark.skipif(
    not (MODEL_DIR / "onnx" / "model.onnx").exists(), reason="run `make models` first"
)

QUESTION = (
    'Highlight the parts (if any) of this contract related to "Governing Law" that should be '
    "reviewed by a lawyer. Details: Which state/country's law governs the interpretation of the "
    "contract?"
)


@pytest.fixture(scope="module")
def embedder() -> Embedder:
    return Embedder(MODEL_DIR, batch_size=4)


def test_matches_the_reference_implementation(embedder: Embedder) -> None:
    # First six values from sentence-transformers 6.2.0 (torch 2.14.1) on the same pinned model,
    # recorded in ADR 0011. The ONNX path must agree to well under 1e-5.
    reference = [-0.045818, 0.027819, 0.030915, -0.0757, 0.04747, -0.035005]
    np.testing.assert_allclose(embedder.embed([QUESTION])[0, :6], reference, atol=1e-5)


def test_unit_length_float32_vectors(embedder: Embedder) -> None:
    vectors = embedder.embed(["one", "two words", "a somewhat longer third text"])
    assert vectors.shape == (3, DIMENSION)
    assert vectors.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-6)


def test_empty_input_gives_an_empty_matrix(embedder: Embedder) -> None:
    assert embedder.embed([]).shape == (0, DIMENSION)


def test_same_text_twice_gives_the_same_vector(embedder: Embedder) -> None:
    texts = ["The Licensee shall indemnify the Licensor."] * 2 + ["x" * 3000]
    first, second = embedder.embed(texts), embedder.embed(texts)
    assert np.array_equal(first, second)
    assert np.array_equal(first[0], first[1])


def test_batching_does_not_change_vectors_beyond_float_noise(embedder: Embedder) -> None:
    # Padding a short text to a long neighbour's length changes the arithmetic slightly, not the
    # result: measured at most 1e-7 on 50 CUAD chunks (ADR 0011).
    texts = ["short", "a much longer text " * 30, "middle length text here", "x", "y z"]
    batched = embedder.embed(texts)
    alone = np.concatenate([embedder.embed([t]) for t in texts])
    np.testing.assert_allclose(batched, alone, atol=1e-5)


def test_a_relevant_clause_is_closer_than_an_unrelated_one(embedder: Embedder) -> None:
    q, relevant, unrelated = embedder.embed(
        [
            QUESTION,
            "This Agreement shall be governed by the laws of the State of New York.",
            "The Licensee shall pay a royalty of five percent of net sales each quarter.",
        ]
    )
    assert q @ relevant > q @ unrelated
