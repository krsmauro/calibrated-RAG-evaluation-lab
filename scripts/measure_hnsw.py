"""Exact search vs an HNSW index under the per-document filter, on ingested CUAD (plan step 2.8).

Builds an HNSW index inside one transaction and rolls it back at the end, so the database is
left unchanged. For every dev document and every question, runs the service's exact query and
three HNSW variants, then reports short results (fewer rows than the document can give),
agreement with exact search, latency, and the query plans for the largest document.
Usage: uv run python scripts/measure_hnsw.py   (needs `make ingest` and `make evalsets`)
"""

import json
import re
import statistics
import time
from pathlib import Path

import psycopg
from psycopg import sql

from ragcalibrate.config import load_settings
from ragcalibrate.ingest.chunkers import c1_id
from ragcalibrate.ingest.embedding import EMBEDDER_ID, Embedder
from ragcalibrate.ingest.load import vector_literal
from ragcalibrate.service.retrieval import DENSE_SQL

CORPUS, K = "cuad", 10
CHUNKER = c1_id(EMBEDDER_ID, 256, 32)
QUERIES = Path("evalsets/cuad-dev.queries.jsonl")

# The ORDER BY must use the indexed expression, or the index cannot serve it.
HNSW_SQL = """
SELECT c.id FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id
WHERE e.embedder_id = %(embedder_id)s AND c.chunker_id = %(chunker_id)s
  AND c.document_id = %(document_id)s
ORDER BY e.embedding::vector(384) <=> %(query)s::vector(384)
LIMIT %(k)s
"""
# name -> settings. enable_sort = off makes the planner take the HNSW index (which returns rows
# in order) instead of exact search; "planner" shows what it picks when left alone.
ITERATIVE = "hnsw.iterative_scan"
VARIANTS: dict[str, dict[str, str]] = {
    "hnsw (planner's choice)": {"enable_sort": "on", ITERATIVE: "off"},
    "hnsw ef_search=40": {"enable_sort": "off", ITERATIVE: "off"},
    "hnsw + iterative strict_order": {"enable_sort": "off", ITERATIVE: "strict_order"},
    "hnsw + iterative relaxed_order": {"enable_sort": "off", ITERATIVE: "relaxed_order"},
}
Params = dict[str, object]


def configure(conn: psycopg.Connection, settings: dict[str, str]) -> None:
    for name, value in settings.items():
        conn.execute("SELECT set_config(%s, %s, true)", (name, value))


def timed(conn: psycopg.Connection, query: str, params: Params) -> tuple[list[int], float]:
    started = time.perf_counter()
    rows = conn.execute(query, params).fetchall()
    return [r[0] for r in rows], (time.perf_counter() - started) * 1000


def explain(conn: psycopg.Connection, query: str, params: Params) -> str:
    plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) " + query, params).fetchall()
    # Postgres prints the vector in its own float format; elide it so the plan stays readable.
    return re.sub(r"'\[[-0-9.e,]+\]'", "'<query vector>'", "\n".join(r[0] for r in plan))


def pct(values: list[float], q: int) -> float:
    return statistics.quantiles(values, n=100)[q - 1]


def main() -> None:
    queries = [json.loads(line) for line in QUERIES.open()]
    questions = sorted({q["text"] for q in queries})
    dev_docs = sorted({q["document_id"] for q in queries})
    vectors = [vector_literal(v) for v in Embedder().embed(questions)]
    url = load_settings().database_url.get_secret_value()
    # No automatic prepared statements: each query is planned with its values, so the planner
    # can prove the partial index's predicate (embedder_id = ...) every time.
    with psycopg.connect(url, prepare_threshold=None) as conn:
        docs = conn.execute(
            "SELECT d.external_id, d.id, count(c.id) FROM documents d"
            " JOIN chunks c ON c.document_id = d.id AND c.chunker_id = %s"
            " WHERE d.corpus = %s GROUP BY 1, 2",
            (CHUNKER, CORPUS),
        ).fetchall()
        doc_ids = {ext: (doc_id, n) for ext, doc_id, n in docs}
        sizes = [doc_ids[d][1] for d in dev_docs]
        print(f"{len(dev_docs)} dev documents x {len(questions)} questions, k = {K}")
        print(
            f"chunks per dev document: min {min(sizes)}, median {statistics.median(sizes)},"
            f" max {max(sizes)}; all chunks {sum(n for _, n in doc_ids.values())}"
        )
        [(version,)] = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchall()
        print(f"pgvector {version}")

        with conn.transaction(force_rollback=True):
            started = time.perf_counter()
            conn.execute(
                sql.SQL(
                    "CREATE INDEX hnsw_measure ON chunk_embeddings"
                    " USING hnsw ((embedding::vector(384)) vector_cosine_ops)"
                    " WHERE embedder_id = {}"
                ).format(sql.Literal(EMBEDDER_ID))
            )
            build_s = time.perf_counter() - started
            [(size,)] = conn.execute(
                "SELECT pg_size_pretty(pg_relation_size('hnsw_measure'))"
            ).fetchall()
            conn.execute("ANALYZE chunk_embeddings")
            print(f"HNSW index (default m=16, ef_construction=64): {build_s:.1f} s, {size}")

            names = ["exact (service query)", *VARIANTS]
            latency: dict[str, list[float]] = {n: [] for n in names}
            short = dict.fromkeys(names, 0)
            short_docs: dict[str, set[str]] = {n: set() for n in names}
            agree: dict[str, list[float]] = {n: [] for n in names}
            same_order = dict.fromkeys(names, 0)
            pairs = 0
            for ext in dev_docs:
                document_id, n_chunks = doc_ids[ext]
                want = min(K, n_chunks)
                for vector in vectors:
                    pairs += 1
                    configure(conn, {"enable_sort": "on", ITERATIVE: "off"})
                    exact_params = {
                        "query": vector, "corpus": CORPUS, "doc_id": ext,
                        "chunker_id": CHUNKER, "embedder_id": EMBEDDER_ID, "k": K,
                    }  # fmt: skip
                    exact, ms = timed(conn, DENSE_SQL, exact_params)
                    results = {"exact (service query)": (exact, ms)}
                    params = {
                        "query": vector, "embedder_id": EMBEDDER_ID, "chunker_id": CHUNKER,
                        "document_id": document_id, "k": K,
                    }  # fmt: skip
                    for name, settings in VARIANTS.items():
                        configure(conn, settings)
                        results[name] = timed(conn, HNSW_SQL, params)
                    for name, (ids, ms) in results.items():
                        latency[name].append(ms)
                        if len(ids) < want:
                            short[name] += 1
                            short_docs[name].add(ext)
                        agree[name].append(len(set(ids) & set(exact)) / want)
                        same_order[name] += ids == exact

            print(f"\n{pairs} (document, question) pairs per variant")
            print(
                f"{'variant':34} {'short':>7} {'in docs':>7} {'top-k overlap':>13}"
                f" {'same list':>9} {'p50 ms':>7} {'p95 ms':>7} {'max ms':>7}"
            )
            for name in names:
                ms = latency[name]
                print(
                    f"{name:34} {short[name]:7} {len(short_docs[name]):7}"
                    f" {statistics.fmean(agree[name]):13.4f}"
                    f" {same_order[name] / pairs:9.4f} {statistics.median(ms):7.2f}"
                    f" {pct(ms, 95):7.2f} {max(ms):7.2f}"
                )

            largest = max(dev_docs, key=lambda d: doc_ids[d][1])
            smallest = min(dev_docs, key=lambda d: doc_ids[d][1])
            vector = vectors[0]
            for label, ext in (("largest", largest), ("smallest", smallest)):
                document_id, n_chunks = doc_ids[ext]
                print(f"\n=== plans, {label} dev document ({n_chunks} chunks), question 1 ===")
                configure(conn, {"enable_sort": "on", ITERATIVE: "off"})
                exact_params = {
                    "query": vector, "corpus": CORPUS, "doc_id": ext,
                    "chunker_id": CHUNKER, "embedder_id": EMBEDDER_ID, "k": K,
                }  # fmt: skip
                plan = explain(conn, DENSE_SQL, exact_params)
                print(f"--- exact (service query)\n{plan}")
                params = {
                    "query": vector, "embedder_id": EMBEDDER_ID, "chunker_id": CHUNKER,
                    "document_id": document_id, "k": K,
                }  # fmt: skip
                for name, settings in VARIANTS.items():
                    configure(conn, settings)
                    print(f"--- {name}\n{explain(conn, HNSW_SQL, params)}")
    print("\nindex rolled back; the database is unchanged")


if __name__ == "__main__":
    main()
