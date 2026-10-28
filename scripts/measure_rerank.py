"""Tune S4 (cross-encoder rerank of S3's top N) on CUAD dev, and time it (plan step 3.3).

`tune`: asks the running service (`make serve`) once for each answerable dev query's S3 top
max(depths), with S3's parameters from 3.2, then reranks prefixes of that list offline with the
service's own `Reranker` and `rerank` and scores the top 10 with the harness's own scoring. A
prefix of S3's top n is what the service returns at a smaller k (RRF sorts every fused chunk
before cutting), so this is what `/retrieve` with strategy "rerank" returns, up to float noise:
the service scores exactly N pairs, here a prefix's scores come from batches of the longest
list, and the same pair in a different batch moved by at most 2.4e-6 (ADR 0013). The chosen
setting is checked through the service afterwards (`ragcalibrate run --strategy rerank`).

`tune --question details` or `category` (a diagnostic for finding F-012, not a strategy): the
reranker sees only part of CUAD's templated question, the text after "Details:" or the category
name, while S3's candidates still come from the whole question. The service always reranks with
the question as sent; cutting the template is done here, in a measurement script, to see how much
of S4's loss the template explains.

`latency`: sends a seeded sample of dev queries one at a time, S3 and then S4 at one depth, and
reports the latency the client sees per request (one at a time, so no queueing behind other
requests). Design §8.6's latency under load is plan step 8.7, not this.

Dev only: the choice must not see the test split. Gold spans are used only to score.
Usage: uv run python scripts/measure_rerank.py tune [--sample N] [--depths N ...] [--question Q]
       uv run python scripts/measure_rerank.py latency --rerank-depth N [--sample N]
"""

import argparse
import asyncio
import platform
import random
import statistics
import time
from pathlib import Path

import httpx

from ragcalibrate.contract import RetrieveRequest, RetrieveResponse
from ragcalibrate.corpora import evalsets
from ragcalibrate.corpora.schema import Gold, Query
from ragcalibrate.harness.adapter import TIMEOUT, HttpSut
from ragcalibrate.harness.cli import DEFAULT_FUSION_DEPTH, DEFAULT_RRF_K
from ragcalibrate.harness.run import QueryResult, retrieve_all, score, summarize
from ragcalibrate.ingest.chunkers import c1_id
from ragcalibrate.ingest.embedding import EMBEDDER_ID
from ragcalibrate.service.rerank import Reranker, rerank

CORPUS, K = "cuad", 10
CHUNKER = c1_id(EMBEDDER_ID, 256, 32)
EVALSETS = Path("evalsets")
BASE_URL = "http://127.0.0.1:8000"
DEPTHS = [10, 20, 30, 50]
SEED = 33
# What the reranker is given, from the question as sent. Only "as-sent" is what S4 does.
QUESTION_FORMS = {
    "as-sent": lambda text: text,
    "details": lambda text: text.split("Details:", 1)[1].strip(),
    "category": lambda text: text.split('"')[1],
}


def dev(sample: int | None) -> tuple[list[Query], dict[str, Gold]]:
    """Answerable dev queries, in file order, or a seeded random sample of them."""
    evalsets.verify(EVALSETS)
    gold = {g.query_id: g for g in evalsets.read_gold(EVALSETS, "dev") if g.answerable}
    queries = [q for q in evalsets.read_queries(EVALSETS, "dev") if q.id in gold]
    if sample is not None:
        queries = random.Random(SEED).sample(queries, sample)  # noqa: S311 (a sample, not a secret)
    return queries, gold


def top(response: RetrieveResponse, n: int) -> RetrieveResponse:
    return response.model_copy(update={"chunks": response.chunks[:n]})


def row(name: str, results: list[QueryResult], baseline: list[QueryResult]) -> str:
    means = summarize(results)
    # Paired with S3 on recall@5: queries where this is better, worse.
    pairs = [
        (r.metrics["recall@5"] or 0.0) - (b.metrics["recall@5"] or 0.0)
        for r, b in zip(results, baseline, strict=True)
    ]
    wins, losses = sum(d > 0 for d in pairs), sum(d < 0 for d in pairs)
    return (
        f"{name:14} {means['recall@5'].mean:6.3f} {means['hit@5'].mean:6.3f}"
        f" {means['recall@10'].mean:6.3f} {means['mrr@10'].mean:6.3f}"
        f" {statistics.fmean(pairs):+7.3f} {wins:5} {losses:5}"
    )


async def tune(sample: int | None, depths: list[int], question: str) -> None:
    queries, gold = dev(sample)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        candidates = await retrieve_all(
            HttpSut(client),
            queries,
            corpus=CORPUS,
            strategy="hybrid",
            chunker_id=CHUNKER,
            k=max(depths),
            concurrency=8,
            rrf_k=DEFAULT_RRF_K,
            fusion_depth=DEFAULT_FUSION_DEPTH,
        )
    reranker = Reranker()
    form = QUESTION_FORMS[question]
    started = time.perf_counter()
    scores: list[list[float]] = []
    for i, (query, response) in enumerate(zip(queries, candidates, strict=True), start=1):
        scores.append(reranker.score(form(query.text), [c.text for c in response.chunks]))
        if i % 500 == 0:
            print(f"reranked {i} of {len(queries)} ({time.perf_counter() - started:.0f} s)")
    pairs = sum(map(len, scores))
    elapsed = time.perf_counter() - started
    print(f"{pairs} pairs in {elapsed:.0f} s, {1000 * elapsed / pairs:.1f} ms per pair")

    golds = [gold[q.id] for q in queries]
    s3 = [score(top(r, K), g) for r, g in zip(candidates, golds, strict=True)]
    n_docs = len({q.document_id for q in queries})
    print(f"\n{len(queries)} answerable dev queries, {n_docs} documents, top {K} scored")
    print(f"S3: rrf_k {DEFAULT_RRF_K}, fusion_depth {DEFAULT_FUSION_DEPTH}")
    print(f"the reranker is given: {question}")
    print("delta, better, worse: recall@5 paired per query against S3\n")
    header = f"{'':14} {'R@5':>6} {'Hit@5':>6} {'R@10':>6} {'MRR':>6}"
    print(header + f" {'delta':>7} {'better':>5} {'worse':>5}")
    print(row("S3 hybrid", s3, s3))
    s4: dict[int, list[QueryResult]] = {}
    for depth in depths:
        s4[depth] = [
            score(r.model_copy(update={"chunks": rerank(r.chunks[:depth], s[:depth], k=K)}), g)
            for r, s, g in zip(candidates, scores, golds, strict=True)
        ]
        print(row(f"S4 depth {depth}", s4[depth], s3))

    print(f"\nrecall@5 by category: S3, then S4 at depths {', '.join(map(str, depths))}")
    categories = sorted({g.category for g in golds})
    for category in categories:
        pick = [i for i, g in enumerate(golds) if g.category == category]
        cells = [summarize([s3[i] for i in pick])["recall@5"].mean] + [
            summarize([s4[d][i] for i in pick])["recall@5"].mean for d in depths
        ]
        print(f"{category[:40]:40} {len(pick):4} " + " ".join(f"{c:6.3f}" for c in cells))


async def latency(rerank_depth: int, sample: int) -> None:
    queries, _ = dev(sample)
    common = {"corpus": CORPUS, "chunker_id": CHUNKER, "k": K, "rrf_k": DEFAULT_RRF_K}
    settings = {
        "S3 hybrid": {"strategy": "hybrid", "fusion_depth": DEFAULT_FUSION_DEPTH},
        f"S4 depth {rerank_depth}": {
            "strategy": "rerank",
            "fusion_depth": DEFAULT_FUSION_DEPTH,
            "rerank_depth": rerank_depth,
        },
    }
    print(f"{len(queries)} dev queries, one at a time; {platform.platform()}")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sut = HttpSut(client)
        for name, setting in settings.items():
            requests = [
                RetrieveRequest.model_validate(
                    {"query": q.text, "doc_id": q.document_id} | common | setting
                )
                for q in queries
            ]
            for request in requests[:20]:  # warm-up: connections, caches, thread pools
                await sut.retrieve(request)
            times: list[float] = []
            for request in requests:
                started = time.perf_counter()
                await sut.retrieve(request)
                times.append((time.perf_counter() - started) * 1000)
            p = statistics.quantiles(times, n=100, method="inclusive")
            print(
                f"{name:14} p50 {p[49]:7.1f} ms  p95 {p[94]:7.1f}  p99 {p[98]:7.1f}"
                f"  mean {statistics.fmean(times):7.1f}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    tuning = commands.add_parser("tune")
    tuning.add_argument("--sample", type=int, help="a seeded sample of dev queries (default: all)")
    tuning.add_argument("--depths", type=int, nargs="+", default=DEPTHS)
    tuning.add_argument("--question", choices=list(QUESTION_FORMS), default="as-sent")
    timing = commands.add_parser("latency")
    timing.add_argument("--rerank-depth", type=int, required=True)
    timing.add_argument("--sample", type=int, default=500)
    args = parser.parse_args()
    if args.command == "tune":
        asyncio.run(tune(args.sample, args.depths, args.question))
    else:
        asyncio.run(latency(args.rerank_depth, args.sample))


if __name__ == "__main__":
    main()
