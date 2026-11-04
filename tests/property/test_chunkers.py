"""Chunkers C1 and C2 with the real bge tokenizer. Skipped until `make models` has been run.

The general properties (offsets, coverage, window, overlap, determinism) run against both
chunkers; then each chunker's own guarantees and worked examples.
"""

from bisect import bisect_left
from collections import Counter
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from tokenizers import Tokenizer

from ragcalibrate.ingest.chunkers import Chunk, c1_id, c2_id, chunk_c1, chunk_c2, heading_starts
from ragcalibrate.ingest.embedding import load_tokenizer

MODEL_DIR = Path(__file__).parents[2] / "data" / "models" / "bge-small-en-v1.5"

pytestmark = pytest.mark.skipif(
    not (MODEL_DIR / "tokenizer.json").exists(), reason="run `make models` first"
)

# Contract-like pieces plus the awkward cases: accents, CJK (the normalizer splits each character
# into its own word), a ligature, a character that lowercases to two code points, long words,
# a Hangul syllable (the normalizer turns it into three tokens with the same offsets). The
# numbering and punctuation pieces make C2 headings: ". 1. The", "\n (a) shall", "  2.1 Section".
PIECES = [
    "The", "Licensee", "shall", "indemnify", "Section", "2.1(a)", "ARTICLE IV.", "naïve",
    "über-cool", "日本語", "e-mail", "$1,000,000", "\n\n", "\t", "  ", "—", "x" * 30, "İstanbul",
    "ﬁnal", "Non-Compete", "탬", ".", ";", "1.", "2.1", "(a)", "(iv)", "Section 3.", "\n",
]  # fmt: skip
# Text made of headed sections, so C2's packing and its fallback to C1 run on most examples.
HEADINGS = ["1.", "2.1", "8.1.4", "Section 3.", "ARTICLE IV", "(a)", "(iv)", "A."]
BEFORE = [". ", "; ", ": ", "\n", "\n\n", "   "]
sectioned = st.lists(
    st.tuples(
        st.sampled_from(BEFORE), st.sampled_from(HEADINGS), st.lists(st.sampled_from(PIECES))
    ),
    min_size=1,
    max_size=8,
).map(lambda parts: "".join(f"{b}{h} The {' '.join(body)}" for b, h, body in parts))
texts = st.one_of(
    st.lists(st.sampled_from(PIECES), max_size=80).map(" ".join),
    st.text(st.characters(exclude_categories=["Cs"]), max_size=200),
    sectioned,
)
windows = st.integers(1, 24).flatmap(
    lambda size: st.tuples(st.just(size), st.integers(0, size - 1))
)
Chunker = Callable[[str, Tokenizer, int, int], list[Chunk]]
both = pytest.mark.parametrize("chunk", [chunk_c1, chunk_c2], ids=["c1", "c2"])


@pytest.fixture(scope="module")
def tok() -> Tokenizer:
    return load_tokenizer(MODEL_DIR)


def n_tokens(tok: Tokenizer, text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False).ids)


@both
@given(text=texts, window=windows)
def test_chunks_are_exact_ordered_slices(
    tok: Tokenizer, chunk: Chunker, text: str, window: tuple[int, int]
) -> None:
    chunks = chunk(text, tok, *window)
    for c in chunks:
        assert 0 <= c.start_char < c.end_char <= len(text)
        assert text[c.start_char : c.end_char] == c.text
    assert all(a.start_char < b.start_char for a, b in pairwise(chunks))
    assert all(a.end_char < b.end_char for a, b in pairwise(chunks))


@both
@given(text=texts, window=windows)
def test_every_token_is_inside_a_chunk(
    tok: Tokenizer, chunk: Chunker, text: str, window: tuple[int, int]
) -> None:
    chunks = chunk(text, tok, *window)
    for start, end in tok.encode(text, add_special_tokens=False).offsets:
        assert any(c.start_char <= start and end <= c.end_char for c in chunks)


@both
@given(text=texts, window=windows)
def test_no_chunk_exceeds_its_window(
    tok: Tokenizer, chunk: Chunker, text: str, window: tuple[int, int]
) -> None:
    size, _ = window
    # A single word longer than the window is split, and its pieces may re-tokenize differently.
    word_lengths = Counter(tok.encode(text, add_special_tokens=False).word_ids)
    assume(max(word_lengths.values(), default=0) <= size)
    for c in chunk(text, tok, *window):
        assert n_tokens(tok, c.text) <= size


@both
@given(text=texts, size=st.integers(1, 24))
def test_zero_overlap_chunks_do_not_overlap(
    tok: Tokenizer, chunk: Chunker, text: str, size: int
) -> None:
    chunks = chunk(text, tok, size, 0)
    assert all(a.end_char <= b.start_char for a, b in pairwise(chunks))


@both
@given(text=texts, window=windows)
def test_deterministic(tok: Tokenizer, chunk: Chunker, text: str, window: tuple[int, int]) -> None:
    assert chunk(text, tok, *window) == chunk(text, tok, *window)


@both
def test_empty_and_whitespace_text_give_no_chunks(tok: Tokenizer, chunk: Chunker) -> None:
    assert chunk("", tok, 5, 2) == []
    assert chunk(" \n\t ", tok, 5, 2) == []


@both
@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (4, 4), (4, -1)])
def test_bad_parameters_are_rejected(
    tok: Tokenizer, chunk: Chunker, size: int, overlap: int
) -> None:
    with pytest.raises(ValueError, match="overlap < size"):
        chunk("text", tok, size, overlap)


# C1


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


def test_id_names_every_parameter() -> None:
    assert c1_id("bge@abc", 256, 32) == "c1v1:bge@abc:size=256:overlap=32"


# C2


@given(text=texts, window=windows)
def test_c2_never_splits_a_section_that_fits(
    tok: Tokenizer, text: str, window: tuple[int, int]
) -> None:
    size, _ = window
    offsets = tok.encode(text, add_special_tokens=False).offsets
    token_starts = [start for start, _ in offsets]
    chunks = chunk_c2(text, tok, *window)
    for a, b in pairwise([0, *heading_starts(text), len(text)]):
        i, j = bisect_left(token_starts, a), bisect_left(token_starts, b)
        if 0 < j - i <= size:
            first, last = offsets[i][0], offsets[j - 1][1]
            assert any(c.start_char <= first and last <= c.end_char for c in chunks)


@given(text=texts, window=windows)
def test_c2_without_headings_is_c1(tok: Tokenizer, text: str, window: tuple[int, int]) -> None:
    assume(not heading_starts(text))
    assert chunk_c2(text, tok, *window) == chunk_c1(text, tok, *window)


def test_c2_known_answer(tok: Tokenizer) -> None:
    # Worked by hand from the tokens. Headings start at -1.- (offset 10), -2.- (29), -3.- (51),
    # so the sections and their token counts are: -Recitals.- 3 (recital ##s .), -1. Term. One
    # year.- 7, -2. Fees. Ten dollars.- 7, -3. Law. Texas law applies here.- 9.
    text = "Recitals. 1. Term. One year. 2. Fees. Ten dollars. 3. Law. Texas law applies here."
    # Window 12: the first two sections pack (10 tokens); the third would make 17, so it starts
    # a chunk; the fourth would make 16 with it, so it is a chunk of its own (9).
    assert chunk_c2(text, tok, 12, 2) == [
        Chunk(0, 28, "Recitals. 1. Term. One year."),
        Chunk(29, 50, "2. Fees. Ten dollars."),
        Chunk(51, 82, "3. Law. Texas law applies here."),
    ]
    # C1 with the same window cuts inside the second section: tokens 0-11 end on -2.-.
    assert chunk_c1(text, tok, 12, 2)[0] == Chunk(0, 31, "Recitals. 1. Term. One year. 2.")
    # Window 10: the first two sections fill it exactly, and still pack.
    assert chunk_c2(text, tok, 10, 2)[0] == Chunk(0, 28, "Recitals. 1. Term. One year.")
    # Window 8: no two sections fit together. The fourth (9 tokens) falls back to C1: tokens
    # 0-7 end before the final -.- (a word of its own); the next window starts 2 tokens back,
    # at -applies-, and takes the rest.
    assert chunk_c2(text, tok, 8, 2) == [
        Chunk(0, 9, "Recitals."),
        Chunk(10, 28, "1. Term. One year."),
        Chunk(29, 50, "2. Fees. Ten dollars."),
        Chunk(51, 81, "3. Law. Texas law applies here"),
        Chunk(69, 82, "applies here."),
    ]


def test_c2_id_names_every_parameter() -> None:
    assert c2_id("bge@abc", 256, 32) == "c2v1:bge@abc:size=256:overlap=32"
