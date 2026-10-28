"""Retrieval metrics (docs/eval-spec.md section 3): pure functions over spans and ranked chunks.

All offsets are half-open character offsets into the same raw document text. A metric that is
undefined because the query has no gold span returns None: the caller excludes the query from the
average; it is never scored as zero or one (spec 3.1).
"""

from collections.abc import Callable, Sequence
from typing import NamedTuple


class Interval(NamedTuple):
    start: int
    end: int


class RankedChunk(NamedTuple):
    id: str
    start: int
    end: int

    @property
    def interval(self) -> Interval:
        return Interval(self.start, self.end)


# Character offset just after each token of a text. Which tokenizer is used is decided in step 4.9;
# the metric only needs to know where the tokens end.
TokenEnds = Callable[[str], list[int]]


def overlap(a: Interval, b: Interval) -> int:
    return max(0, min(a.end, b.end) - max(a.start, b.start))


def merge_spans(spans: Sequence[Interval]) -> list[Interval]:
    """Merge gold spans that overlap each other, so no character or span is counted twice."""
    merged: list[Interval] = []
    for span in sorted(spans):
        if merged and span.start < merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, span.end))
        else:
            merged.append(span)
    return merged


def dedupe(chunks: Sequence[RankedChunk]) -> list[RankedChunk]:
    """Keep the first occurrence of each chunk id, so a repeat does not shift later ranks."""
    seen: set[str] = set()
    kept: list[RankedChunk] = []
    for chunk in chunks:
        if chunk.id not in seen:
            seen.add(chunk.id)
            kept.append(chunk)
    return kept


def _relevant(chunk: RankedChunk, span: Interval, min_overlap_frac: float) -> bool:
    """R1 (default): one character of overlap. R2: overlap of at least `frac` of the shorter of
    the span and the chunk, so a span longer than any chunk stays reachable (spec section 2)."""
    shared = overlap(chunk.interval, span)
    if shared == 0:
        return False
    shorter = min(span.end - span.start, chunk.end - chunk.start)
    return shared >= min_overlap_frac * shorter


def hit_at_k(
    ranked: Sequence[RankedChunk], gold: Sequence[Interval], k: int, min_overlap_frac: float = 0.0
) -> float | None:
    if not gold:
        return None
    spans = merge_spans(gold)
    top = dedupe(ranked)[:k]
    return float(any(_relevant(c, s, min_overlap_frac) for c in top for s in spans))


def recall_at_k(
    ranked: Sequence[RankedChunk], gold: Sequence[Interval], k: int, min_overlap_frac: float = 0.0
) -> float | None:
    if not gold:
        return None
    spans = merge_spans(gold)
    top = dedupe(ranked)[:k]
    hit = sum(any(_relevant(c, s, min_overlap_frac) for c in top) for s in spans)
    return hit / len(spans)


def mrr_at_k(
    ranked: Sequence[RankedChunk], gold: Sequence[Interval], k: int, min_overlap_frac: float = 0.0
) -> float | None:
    if not gold:
        return None
    spans = merge_spans(gold)
    for rank, chunk in enumerate(dedupe(ranked)[:k], start=1):
        if any(_relevant(chunk, s, min_overlap_frac) for s in spans):
            return 1 / rank
    return 0.0


def char_precision_recall_at_budget(
    ranked: Sequence[RankedChunk],
    gold: Sequence[Interval],
    doc_text: str,
    budget_tokens: int,
    token_ends: TokenEnds,
) -> tuple[float, float] | None:
    """Character precision and recall within the first `budget_tokens` tokens of the ranked list.

    Chunks are read in order; the chunk that crosses the budget is cut at a token boundary. A
    character covered by two overlapping chunks counts once. Returns None when there is no gold.
    Empty retrieval scores (0, 0): returning nothing is a failure, not an undefined case.
    """
    if not gold:
        return None
    retrieved: list[Interval] = []
    used = 0
    for chunk in dedupe(ranked):
        if used >= budget_tokens:
            break
        ends = token_ends(doc_text[chunk.start : chunk.end])
        take = min(len(ends), budget_tokens - used)
        used += take
        if take:
            retrieved.append(Interval(chunk.start, chunk.start + ends[take - 1]))
    covered = merge_spans(retrieved)
    gold_chars = sum(s.end - s.start for s in merge_spans(gold))
    ret_chars = sum(s.end - s.start for s in covered)
    shared = sum(overlap(r, g) for r in covered for g in merge_spans(gold))
    if ret_chars == 0:
        return 0.0, 0.0
    return shared / ret_chars, shared / gold_chars
