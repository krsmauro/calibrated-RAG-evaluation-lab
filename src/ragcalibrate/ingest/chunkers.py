"""Versioned chunkers over the raw document text.

A chunk is a half-open character span [start_char, end_char) of the document exactly as the
dataset shipped it, and its text is that slice, so chunks and gold spans share one coordinate
system (skill EVAL-CRITICAL-2). The chunker id names the algorithm version, the tokenizer and
every parameter: change any of them and the id changes, so old and new chunks never mix.
"""

import re
from bisect import bisect_left
from itertools import pairwise
from typing import NamedTuple

from tokenizers import Tokenizer

C1_VERSION = 1
C2_VERSION = 1

# Where C2 may cut: the start of a section or clause heading (Design §7). CUAD's text was
# extracted from filings, and in many contracts the only line breaks are page artifacts, with
# headings inline ("...as follows: 1. Grant of Rights. Section 1.1. License Grant. Subject
# to..."). So a heading may start a line, follow a sentence end, or follow a run of spaces (a
# layout gap), and is one of: Article or Section with a number ("ARTICLE IV", "Section 1.1."), a
# number with a dot or a dotted number ("2. Term", "8.1.4 Breach"), each followed by a capital;
# or a clause number in parentheses ("(a)", "(iv)", "(12)"). A letter or Roman numeral with a dot
# ("A. Purpose", "IV. Term") counts only at a line start, since after a sentence end it is
# usually an initial (". A. Smith"). Left out on purpose: a reference inside a sentence ("under
# Section 2.1"), a number before a lowercase word ("10 days"), "(a)" inside a sentence ("if (a)
# it..."), and three-digit parentheses (a phone area code). Every rule needs whitespace before
# the heading, so no token crosses a cut. A missed heading costs little: its section joins the
# one before, and a section longer than the window falls back to C1.
_LINE_START = r"\n[ \t]*"
# A sentence end may close a quote, straight or curly (\u201d, \u2019), or a bracket.
_ANY_START = _LINE_START + r"|[.:;][\"'\u201d\u2019)\]]?[ \t]+|[ \t]{2,}"
_ANYWHERE = (
    r"(?:ARTICLE|Article|SECTION|Section)[ \t]+(?:\d{1,3}(?:\.\d{1,3})*|[IVXLC]{1,6})\.?\s+[A-Z]"
    r"|(?:\d{1,3}(?:\.\d{1,3})+\.?|\d{1,3}\.)[ \t]+[A-Z]"
    r"|\((?:[a-z]{1,4}|\d{1,2}|[A-Z])\)[ \t]+\S"
)
_LINE_ONLY = r"(?:[A-Z]|[IVXL]{1,5})\.[ \t]+[A-Z]"
# Matches the whitespace or punctuation before a heading; the heading itself is a lookahead, so
# the match ends where the heading starts.
_HEADING = re.compile(rf"(?:{_ANY_START})(?={_ANYWHERE})|(?:{_LINE_START})(?={_LINE_ONLY})")


class Chunk(NamedTuple):
    start_char: int
    end_char: int
    text: str


def c1_id(tokenizer_id: str, size: int, overlap: int) -> str:
    return f"c1v{C1_VERSION}:{tokenizer_id}:size={size}:overlap={overlap}"


def chunk_c1(text: str, tokenizer: Tokenizer, size: int, overlap: int) -> list[Chunk]:
    """C1: windows of at most `size` tokens, consecutive windows sharing up to `overlap` tokens.

    Tokens are the embedding model's own, so a chunk never exceeds its context. Window edges are
    moved to the start of a word: a chunk then re-tokenizes to exactly its window's tokens (the
    BERT normalizer and pre-tokenizer work word by word), and no chunk begins or ends mid-word.
    The one exception is a single word longer than `size` tokens, which is split, but never
    inside a character.
    Edges move toward less text: the end moves back, the next start moves forward, so a chunk
    is never longer than `size` tokens and the overlap is never more than `overlap` tokens.
    """
    if size < 1 or not 0 <= overlap < size:
        raise ValueError(f"need size >= 1 and 0 <= overlap < size, got {size=} {overlap=}")
    encoding = tokenizer.encode(text, add_special_tokens=False)
    offsets, word_ids = encoding.offsets, encoding.word_ids
    n = len(offsets)

    def word_start(i: int) -> bool:
        return i == 0 or i == n or word_ids[i] != word_ids[i - 1]

    def char_boundary(i: int) -> bool:
        # The normalizer can turn one character into several tokens with the same offsets (a
        # Hangul syllable becomes three jamo), so not every token boundary is a place to cut.
        return i == 0 or i == n or offsets[i][0] >= offsets[i - 1][1]

    chunks: list[Chunk] = []
    start = prev_end = 0
    while start < n:
        end = min(start + size, n)
        cut = end
        while cut > start + 1 and not word_start(cut):
            cut -= 1
        if not word_start(cut):
            # One word fills the window: split it at the last character boundary. If one
            # character alone makes more than `size` tokens, keep it whole in this chunk.
            cut = end
            while cut > start + 1 and not char_boundary(cut):
                cut -= 1
            while not char_boundary(cut):
                cut += 1
        end = cut
        if end <= prev_end:
            # Moving the end back left nothing new after the overlap; drop the overlap instead
            # of emitting a chunk that lies inside the previous one.
            start = prev_end
            continue
        first, last = offsets[start][0], offsets[end - 1][1]
        chunks.append(Chunk(first, last, text[first:last]))
        if end == n:
            break
        prev_end = end
        nxt = max(end - overlap, start + 1)
        while nxt < end and not word_start(nxt):
            nxt += 1
        start = nxt
    return chunks


def c2_id(tokenizer_id: str, size: int, overlap: int) -> str:
    return f"c2v{C2_VERSION}:{tokenizer_id}:size={size}:overlap={overlap}"


def heading_starts(text: str) -> list[int]:
    """Offsets where a section or clause heading starts, ascending; never 0."""
    return [m.end() for m in _HEADING.finditer(text)]


def chunk_c2(text: str, tokenizer: Tokenizer, size: int, overlap: int) -> list[Chunk]:
    """C2: chunks that end where a heading starts, with C1 inside sections longer than `size`.

    The text is cut before every heading into sections. Consecutive sections are packed into one
    chunk while it holds at most `size` tokens, so a section that fits the window is never split,
    and chunks are far larger than one per section would make them: chunk size moves retrieval
    metrics on its own (Design §5.2), so C2's should differ from C1's as little as the structure
    allows. They are still smaller than C1's, which a comparison has to allow for (finding
    F-013). A section longer than `size` tokens is chunked by C1 on its own, with C1's overlap;
    packed chunks do not overlap. A text without headings gets exactly C1's chunks.
    """
    if size < 1 or not 0 <= overlap < size:
        raise ValueError(f"need size >= 1 and 0 <= overlap < size, got {size=} {overlap=}")
    offsets = tokenizer.encode(text, add_special_tokens=False).offsets
    token_starts = [start for start, _ in offsets]
    chunks: list[Chunk] = []

    def emit(first: int, end: int) -> None:
        if end > first:
            start_char, end_char = offsets[first][0], offsets[end - 1][1]
            chunks.append(Chunk(start_char, end_char, text[start_char:end_char]))

    first = 0  # tokens from `first` up to the current section are packed, not yet emitted
    for a, b in pairwise([0, *heading_starts(text), len(text)]):
        i, j = bisect_left(token_starts, a), bisect_left(token_starts, b)  # its tokens: [i, j)
        if j - first <= size:
            continue
        emit(first, i)
        if j - i <= size:
            first = i
        else:
            # Cutting at a heading, a word start, leaves the section's tokens unchanged, so C1
            # over the section alone splits it as it would inside the whole text.
            chunks.extend(
                Chunk(a + c.start_char, a + c.end_char, c.text)
                for c in chunk_c1(text[a:b], tokenizer, size, overlap)
            )
            first = j
    emit(first, len(offsets))
    return chunks
