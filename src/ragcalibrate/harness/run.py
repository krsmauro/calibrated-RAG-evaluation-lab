"""Minimal retrieval run (plan step 2.10): send each query, score the results, summarize.

Phase 3 replaces this with the full runner (experiment YAML, SQLite run store, resumable runs,
one retry layer). Until then a failed request fails the whole run: a run with gaps is not a
result.
"""

import asyncio
import statistics
from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel

from ragcalibrate.contract import RetrieveRequest, RetrieveResponse, Strategy
from ragcalibrate.corpora.schema import Gold, Query
from ragcalibrate.harness.adapter import HttpSut
from ragcalibrate.harness.metrics.retrieval import (
    Interval,
    RankedChunk,
    hit_at_k,
    mrr_at_k,
    recall_at_k,
)

# docs/eval-spec.md section 8: every k is reported, so saturation shows instead of hiding.
K_VALUES = (1, 3, 5, 10)
MRR_K = 10


class Mean(BaseModel):
    mean: float
    n: int


class QueryResult(BaseModel):
    query_id: str
    document_id: str
    category: str
    retrieved: list[tuple[int, int, int, float]]  # (chunk_id, start_char, end_char, score)
    metrics: dict[str, float | None]


async def retrieve_all(
    sut: HttpSut,
    queries: Sequence[Query],
    *,
    corpus: str,
    strategy: Strategy,
    chunker_id: str,
    k: int,
    concurrency: int,
) -> list[RetrieveResponse]:
    """One response per query, in the order of `queries`; at most `concurrency` in flight."""
    limit = asyncio.Semaphore(concurrency)

    async def one(query: Query) -> RetrieveResponse:
        request = RetrieveRequest(
            query=query.text,
            corpus=corpus,
            doc_id=query.document_id,
            strategy=strategy,
            chunker_id=chunker_id,
            k=k,
        )
        async with limit:
            return await sut.retrieve(request)

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(one(q)) for q in queries]
    return [t.result() for t in tasks]


def score(response: RetrieveResponse, gold: Gold) -> QueryResult:
    ranked = [RankedChunk(str(c.chunk_id), c.start_char, c.end_char) for c in response.chunks]
    spans = [Interval(s.start, s.end) for s in gold.spans]
    metrics: dict[str, float | None] = {}
    for k in K_VALUES:
        metrics[f"hit@{k}"] = hit_at_k(ranked, spans, k)
        metrics[f"recall@{k}"] = recall_at_k(ranked, spans, k)
    metrics[f"mrr@{MRR_K}"] = mrr_at_k(ranked, spans, MRR_K)
    return QueryResult(
        query_id=gold.query_id,
        document_id=gold.document_id,
        category=gold.category,
        retrieved=[(c.chunk_id, c.start_char, c.end_char, c.score) for c in response.chunks],
        metrics=metrics,
    )


def summarize(results: Sequence[QueryResult]) -> dict[str, Mean]:
    """Mean of each metric over the queries where it is defined (None is excluded, spec 3.1)."""
    values: defaultdict[str, list[float]] = defaultdict(list)
    for result in results:
        for name, value in result.metrics.items():
            if value is not None:
                values[name].append(value)
    return {name: Mean(mean=statistics.fmean(v), n=len(v)) for name, v in values.items()}


def by_category(results: Sequence[QueryResult]) -> dict[str, dict[str, Mean]]:
    groups: defaultdict[str, list[QueryResult]] = defaultdict(list)
    for result in results:
        groups[result.category].append(result)
    return {category: summarize(group) for category, group in sorted(groups.items())}
