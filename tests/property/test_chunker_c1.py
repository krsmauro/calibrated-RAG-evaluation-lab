"""Chunker C1 with the real bge tokenizer. Skipped until `make models` has been run."""

from collections import Counter
from itertools import pairwise
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from tokenizers import Tokenizer

from ragcalibrate.ingest.chunkers import Chunk, c1_id, chunk_c1
from ragcalibrate.ingest.embedding import load_tokenizer

MODEL_DIR = Path(__file__).parents[2] / "data" / "models" / "bge-small-en-v1.5"

pytestmark = pytest.mark.skipif(
    not (MODEL_DIR / "tokenizer.json").exists(), reason="run `make models` first"
)

# Contract-like pieces plus the awkward cases: accents, CJK (the normalizer splits each character
# into its own word), a ligature, a character that lowercases to two code points, long words,
# a Hangul syllable (the normalizer turns it into three tokens with the same offsets).
PIECES = [
    "The", "Licensee", "shall", "indemnify", "Section", "2.1(a)", "ARTICLE IV.", "naïve",
    "über-cool", "日本語", "e-mail", "$1,000,000", "\n\n", "\t", "  ", "—", "x" * 30, "İstanbul",
    "ﬁnal", "Non-Compete", "탬",
]  # fmt: skip
texts = st.one_of(
    st.lists(st.sampled_from(PIECES), max_size=80).map(" ".join),
    st.text(st.characters(exclude_categories=["Cs"]), max_size=200),
)
windows = st.integers(1, 24).flatmap(
    lambda size: st.tuples(st.just(size), st.integers(0, size - 1))
)


@pytest.fixture(scope="module")
def tok() -> Tokenizer:
    return load_tokenizer(MODEL_DIR)


def n_tokens(tok: Tokenizer, text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False).ids)


@given(text=texts, window=windows)
def test_chunks_are_exact_ordered_slices(
    tok: Tokenizer, text: str, window: tuple[int, int]
) -> None:
    chunks = chunk_c1(text, tok, *window)
    for c in chunks:
        assert 0 <= c.start_char < c.end_char <= len(text)
        assert text[c.start_char : c.end_char] == c.text
    assert all(a.start_char < b.start_char for a, b in pairwise(chunks))
    assert all(a.end_char < b.end_char for a, b in pairwise(chunks))


@given(text=texts, window=windows)
def test_every_token_is_inside_a_chunk(tok: Tokenizer, text: str, window: tuple[int, int]) -> None:
    chunks = chunk_c1(text, tok, *window)
    for start, end in tok.encode(text, add_special_tokens=False).offsets:
        assert any(c.start_char <= start and end <= c.end_char for c in chunks)


@given(text=texts, window=windows)
def test_no_chunk_exceeds_its_window(tok: Tokenizer, text: str, window: tuple[int, int]) -> None:
    size, _ = window
    # A single word longer than the window is split, and its pieces may re-tokenize differently.
    word_lengths = Counter(tok.encode(text, add_special_tokens=False).word_ids)
    assume(max(word_lengths.values(), default=0) <= size)
    for c in chunk_c1(text, tok, *window):
        assert n_tokens(tok, c.text) <= size


@given(text=texts, size=st.integers(1, 24))
def test_zero_overlap_chunks_do_not_overlap(tok: Tokenizer, text: str, size: int) -> None:
    chunks = chunk_c1(text, tok, size, 0)
    assert all(a.end_char <= b.start_char for a, b in pairwise(chunks))


@given(text=texts, window=windows)
def test_deterministic(tok: Tokenizer, text: str, window: tuple[int, int]) -> None:
    assert chunk_c1(text, tok, *window) == chunk_c1(text, tok, *window)


def test_known_answer(tok: Tokenizer) -> None:
    # Worked by hand from the tokens: the(0) license ##e(1) shall(2) ind ##em ##ni ##fy(3)
    # the(4) li ##cens ##or(5) .(6), word ids in brackets. size 5, overlap 2.
    # Window 1: tokens 0-4 would end inside -indemnify-, so it ends after -shall- (4 tokens).
    # Window 2 starts 2 tokens back at -##e-, moves forward to -shall-: tokens 3-7.
    # Window 3 would start at -##ni-, moves forward past -indemnify-: no overlap, tokens 8-12.
    text = "The Licensee shall indemnify   the Licensor."
    assert chunk_c1(text, tok, 5, 2) == [
        Chunk(0, 18, "The Licensee shall"),
        Chunk(13, 28, "shall indemnify"),
        Chunk(31, 44, "the Licensor."),
    ]


def test_word_longer_than_the_window_is_split(tok: Tokenizer) -> None:
    text = "b " + "x" * 60
    chunks = chunk_c1(text, tok, 4, 1)
    assert chunks[0] == Chunk(0, 1, "b")
    assert "".join(c.text for c in chunks[1:]) == "x" * 60  # no gaps, no overlap inside a word


def test_a_word_is_never_split_inside_a_character(tok: Tokenizer) -> None:
    # Found by Hypothesis on 2026-10-28. Tokens of -x탬y-: x ##ᄐ ##ᅢ ##ᆷ ##y, one word, the
    # middle three all at offsets (1, 2). Window 2 can only cut where tokens stop sharing a
    # character; the syllable stays whole although its 3 tokens exceed the window.
    assert chunk_c1("x탬y", tok, 2, 0) == [Chunk(0, 1, "x"), Chunk(1, 2, "탬"), Chunk(2, 3, "y")]
    assert chunk_c1("탬", tok, 1, 0) == [Chunk(0, 1, "탬")]


def test_empty_and_whitespace_text_give_no_chunks(tok: Tokenizer) -> None:
    assert chunk_c1("", tok, 5, 2) == []
    assert chunk_c1(" \n\t ", tok, 5, 2) == []


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (4, 4), (4, -1)])
def test_bad_parameters_are_rejected(tok: Tokenizer, size: int, overlap: int) -> None:
    with pytest.raises(ValueError, match="overlap < size"):
        chunk_c1("text", tok, size, overlap)


def test_id_names_every_parameter() -> None:
    assert c1_id("bge@abc", 256, 32) == "c1v1:bge@abc:size=256:overlap=32"
