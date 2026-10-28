"""Reciprocal Rank Fusion for S3 (Design §7): a pure function over ranked lists, no I/O."""

import math
from collections.abc import Sequence

from ragcalibrate.contract import RetrievedChunk


def rrf(
    rankings: Sequence[Sequence[RetrievedChunk]], *, rrf_k: int, k: int
) -> list[RetrievedChunk]:
    """Fuse rankings with Reciprocal Rank Fusion (Cormack, Clarke and Buettcher, SIGIR 2009).

    A chunk scores the sum, over the rankings that contain it, of 1 / (rrf_k + rank), with rank
    counted from 1. Only positions count, never the input scores, so cosine similarity and
    ts_rank need no normalization. Returns the k best, best first, each with its fused score. A
    chunk listed twice in one ranking counts once, at its first position. Equal scores are
    ordered by position in the document, then by chunk id, as the SQL strategies order them, so
    the result never depends on the order of the rankings.
    """
    parts: dict[int, list[float]] = {}
    chunks: dict[int, RetrievedChunk] = {}
    for ranking in rankings:
        seen: set[int] = set()
        for rank, chunk in enumerate(ranking, start=1):
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            chunks.setdefault(chunk.chunk_id, chunk)
            parts.setdefault(chunk.chunk_id, []).append(1 / (rrf_k + rank))
    # fsum rounds the exact sum once, so a score depends only on the ranks, never on the order of
    # the rankings: ranks (1, 3) and (3, 1) tie exactly and the tiebreak below decides. Plain sum
    # gives the same with two rankings, but can differ in the last bit with three or more.
    scored = [(math.fsum(p), chunks[chunk_id]) for chunk_id, p in parts.items()]
    scored.sort(key=lambda item: (-item[0], item[1].start_char, item[1].chunk_id))
    return [
        RetrievedChunk(
            chunk_id=c.chunk_id, start_char=c.start_char, end_char=c.end_char, text=c.text, score=s
        )
        for s, c in scored[:k]
    ]
