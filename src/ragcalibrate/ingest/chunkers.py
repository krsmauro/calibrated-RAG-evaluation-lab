"""Versioned chunkers over the raw document text.

A chunk is a half-open character span [start_char, end_char) of the document exactly as the
dataset shipped it, and its text is that slice, so chunks and gold spans share one coordinate
system (skill EVAL-CRITICAL-2). The chunker id names the algorithm version, the tokenizer and
every parameter: change any of them and the id changes, so old and new chunks never mix.
"""

from typing import NamedTuple

from tokenizers import Tokenizer

C1_VERSION = 1


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
