"""Tune S3 (Reciprocal Rank Fusion of S1 and S2) on CUAD dev: smoothing constant and depth (3.2).

Asks the running service (`make serve`) once for each answerable dev query's top 100 chunks by
S1 (fts) and by S2 (dense), then fuses prefixes of those lists offline with the service's own
`rrf` and scores the top 10 with the harness's own scoring. A prefix of a top-100 list is
exactly what the service returns at a smaller k (both SQL queries end in a total order), so
this equals what `/retrieve` with strategy "hybrid" returns for the same parameters; the
chosen setting is checked through the service afterwards (`ragcalibrate run --strategy hybrid`).

Dev only: the choice must not see the test split. Gold spans are used only to score.
Usage: uv run python scripts/measure_rrf.py   (needs `make serve`)
"""

import asyncio
import statistics
from pathlib import Path

import httpx

from ragcalibrate.contract import MAX_K, RetrieveResponse
from ragcalibrate.corpora import evalsets
from ragcalibrate.harness.adapter import TIMEOUT, HttpSut
from ragcalibrate.harness.run import QueryResult, retrieve_all, score, summarize
from ragcalibrate.ingest.chunkers import c1_id
from ragcalibrate.ingest.embedding import EMBEDDER_ID
from ragcalibrate.service.fusion import rrf

CORPUS, K = "cuad", 10
CHUNKER = c1_id(EMBEDDER_ID, 256, 32)
EVALSETS = Path("evalsets")
BASE_URL = "http://127.0.0.1:8000"
RRF_KS = (1, 10, 30, 60, 100, 300)
DEPTHS = (10, 20, 30, 50, 100)


def top(response: RetrieveResponse, n: int) -> RetrieveResponse:
    return response.model_copy(update={"chunks": response.chunks[:n]})


def fuse(lex: RetrieveResponse, sem: RetrieveResponse, depth: int, rrf_k: int) -> RetrieveResponse:
    """What the service's hybrid strategy returns for these parameters."""
    chunks = rrf([lex.chunks[:depth], sem.chunks[:depth]], rrf_k=rrf_k, k=K)
    return sem.model_copy(update={"strategy": "hybrid", "chunks": chunks})


def row(name: str, results: list[QueryResult], baseline: list[QueryResult]) -> str:
    means = summarize(results)
    # Paired with S1 on recall@5: queries where this is better, worse.
    pairs = [
        (r.metrics["recall@5"] or 0.0) - (b.metrics["recall@5"] or 0.0)
        for r, b in zip(results, baseline, strict=True)
    ]
    wins, losses = sum(d > 0 for d in pairs), sum(d < 0 for d in pairs)
    return (
        f"{name:22} {means['recall@5'].mean:6.3f} {means['hit@5'].mean:6.3f}"
        f" {means['recall@10'].mean:6.3f} {means['mrr@10'].mean:6.3f}"
        f" {statistics.fmean(pairs):+7.3f} {wins:5} {losses:5}"
    )


async def main() -> None:
    evalsets.verify(EVALSETS)
    gold = {g.query_id: g for g in evalsets.read_gold(EVALSETS, "dev") if g.answerable}
    queries = [q for q in evalsets.read_queries(EVALSETS, "dev") if q.id in gold]
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sut = HttpSut(client)
        options = {"corpus": CORPUS, "chunker_id": CHUNKER, "k": MAX_K, "concurrency": 8}
        lexical = await retrieve_all(sut, queries, strategy="fts", **options)
        semantic = await retrieve_all(sut, queries, strategy="dense", **options)
    golds = [gold[q.id] for q in queries]
    s1 = [score(top(r, K), g) for r, g in zip(lexical, golds, strict=True)]
    s2 = [score(top(r, K), g) for r, g in zip(semantic, golds, strict=True)]
    for depth in DEPTHS:
        short = sum(len(r.chunks) < depth for r in lexical)
        empty = sum(not r.chunks for r in lexical)
        print(f"depth {depth}: S1 returns fewer than {depth} for {short}, none for {empty}")
    n_docs = len({q.document_id for q in queries})
    print(f"\n{len(queries)} answerable dev queries, {n_docs} documents, top {K} scored")
    print("delta, better, worse: recall@5 paired per query against S1\n")
    header = f"{'':22} {'R@5':>6} {'Hit@5':>6} {'R@10':>6} {'MRR':>6}"
    print(header + f" {'delta':>7} {'better':>5} {'worse':>5}")
    print(row("S1 fts", s1, s1))
    print(row("S2 dense", s2, s1))
    for depth in DEPTHS:
        for rrf_k in RRF_KS:
            fused = [
                score(fuse(lex, sem, depth, rrf_k), g)
                for lex, sem, g in zip(lexical, semantic, golds, strict=True)
            ]
            print(row(f"S3 depth {depth} k {rrf_k}", fused, s1))


if __name__ == "__main__":
    asyncio.run(main())
