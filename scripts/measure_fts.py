"""How S1 (Postgres FTS) should turn a CUAD question into a tsquery, on ingested CUAD (step 3.1).

CUAD's questions are one long template ("Highlight the parts (if any) of this contract related
to "<category>" that should be reviewed by a lawyer. Details: <description>"), and
`websearch_to_tsquery` ANDs every word (finding F-002). For each way of building the tsquery,
runs every answerable dev query against its own contract and reports how many return fewer rows
than k (or none), retrieval quality with the harness's metrics, and latency. Then offers a GIN
index inside a rolled-back transaction and shows whether the planner uses it.

The category and description are cut out of the question text itself, never from the gold
file; gold spans are used only to score. Dev only: the choice must not see the test split.
Usage: uv run python scripts/measure_fts.py   (needs `make ingest` and `make evalsets`)
"""

import re
import statistics
import time
from collections.abc import Callable
from pathlib import Path

import psycopg

from ragcalibrate.config import load_settings
from ragcalibrate.corpora import evalsets
from ragcalibrate.harness.metrics.retrieval import (
    Interval,
    RankedChunk,
    hit_at_k,
    mrr_at_k,
    recall_at_k,
)
from ragcalibrate.ingest.chunkers import c1_id
from ragcalibrate.ingest.embedding import EMBEDDER_ID
from ragcalibrate.service.retrieval import FTS_CONFIG, FTS_SQL

CORPUS, K = "cuad", 10
CHUNKER = c1_id(EMBEDDER_ID, 256, 32)
EVALSETS = Path("evalsets")
TEMPLATE = re.compile(
    r'Highlight the parts \(if any\) of this contract related to "(?P<category>[^"]+)"'
    r" that should be reviewed by a lawyer\. Details: (?P<details>.*)",
    re.S,
)

# The service's query, with the tsquery and the rank function swapped in. {tsquery} reads the
# text from %(query)s.
SQL = """
WITH q AS (SELECT {tsquery} AS query)
SELECT c.id, c.start_char, c.end_char, {rank}(c.tsv, q.query) AS score
FROM q, documents d
JOIN chunks c ON c.document_id = d.id AND c.chunker_id = %(chunker_id)s
WHERE d.corpus = %(corpus)s AND d.external_id = %(doc_id)s AND c.tsv @@ q.query
ORDER BY score DESC, c.start_char
LIMIT %(k)s
"""
AND = "websearch_to_tsquery(%(config)s::regconfig, %(query)s)"
PLAIN_AND = "plainto_tsquery(%(config)s::regconfig, %(query)s)"
# The same OR construction as FTS_SQL in service/retrieval.py.
OR = r"""(SELECT string_agg(
    '''' || replace(replace(lexeme, '\', '\\'), '''', '''''') || '''', ' | ')::tsquery
  FROM unnest(to_tsvector(%(config)s::regconfig, %(query)s)))"""


def full(text: str) -> str:
    return text


def no_template(text: str) -> str:
    parts = _parts(text)
    return f"{parts['category']} {parts['details']}"


def category(text: str) -> str:
    return _parts(text)["category"]


def _parts(text: str) -> dict[str, str]:
    found = TEMPLATE.fullmatch(text.strip())
    if found is None:
        raise ValueError(f"not a CUAD template question: {text[:80]!r}")
    return found.groupdict()


# name -> (text sent, SQL). The service row runs the service's own query unchanged.
VARIANTS: dict[str, tuple[Callable[[str], str], str]] = {
    "and: full question (websearch_to_tsquery)": (full, SQL.format(tsquery=AND, rank="ts_rank_cd")),
    "or: full question, ts_rank_cd": (full, SQL.format(tsquery=OR, rank="ts_rank_cd")),
    "or: full question, ts_rank (service)": (full, FTS_SQL),
    "or: template wording removed": (no_template, SQL.format(tsquery=OR, rank="ts_rank_cd")),
    "and: category name only": (category, SQL.format(tsquery=PLAIN_AND, rank="ts_rank_cd")),
    "or: category name only": (category, SQL.format(tsquery=OR, rank="ts_rank_cd")),
}


def pct(values: list[float], q: int) -> float:
    return statistics.quantiles(values, n=100)[q - 1]


def main() -> None:
    evalsets.verify(EVALSETS)
    gold = {g.query_id: g for g in evalsets.read_gold(EVALSETS, "dev") if g.answerable}
    queries = [q for q in evalsets.read_queries(EVALSETS, "dev") if q.id in gold]
    url = load_settings().database_url.get_secret_value()
    with psycopg.connect(url) as conn:
        sizes = dict(
            conn.execute(
                "SELECT d.external_id, count(*) FROM documents d"
                " JOIN chunks c ON c.document_id = d.id AND c.chunker_id = %s"
                " WHERE d.corpus = %s GROUP BY 1",
                (CHUNKER, CORPUS),
            ).fetchall()
        )
        n_docs = len({q.document_id for q in queries})
        print(f"{len(queries)} answerable dev queries, {n_docs} documents, k = {K}")
        print(f"config {FTS_CONFIG}; 'short' = fewer rows than min(k, chunks in the document)\n")
        header = f"{'variant':44} {'short':>6} {'empty':>6} {'R@5':>6} {'Hit@5':>6} {'MRR':>6}"
        print(header + f" {'p50 ms':>7} {'p95 ms':>7}")
        for name, (transform, query_sql) in VARIANTS.items():
            short = empty = 0
            recall: list[float] = []
            hit: list[float] = []
            mrr: list[float] = []
            latency: list[float] = []
            for q in queries:
                params = {
                    "config": FTS_CONFIG,
                    "query": transform(q.text),
                    "corpus": CORPUS,
                    "doc_id": q.document_id,
                    "chunker_id": CHUNKER,
                    "k": K,
                }
                started = time.perf_counter()
                rows = conn.execute(query_sql, params).fetchall()
                latency.append((time.perf_counter() - started) * 1000)
                short += len(rows) < min(K, sizes[q.document_id])
                empty += not rows
                ranked = [RankedChunk(str(r[0]), r[1], r[2]) for r in rows]
                spans = [Interval(s.start, s.end) for s in gold[q.id].spans]
                recall.append(recall_at_k(ranked, spans, 5) or 0.0)
                hit.append(hit_at_k(ranked, spans, 5) or 0.0)
                mrr.append(mrr_at_k(ranked, spans, 10) or 0.0)
            n = len(queries)
            print(
                f"{name:44} {short / n:6.1%} {empty / n:6.1%} {statistics.fmean(recall):6.3f}"
                f" {statistics.fmean(hit):6.3f} {statistics.fmean(mrr):6.3f}"
                f" {statistics.median(latency):7.2f} {pct(latency, 95):7.2f}"
            )
        explain_with_gin(conn, queries[0].text, max(sizes, key=sizes.__getitem__))


def explain_with_gin(conn: psycopg.Connection, question: str, largest_doc: str) -> None:
    """Does the planner use a GIN index on tsv for the service's per-document query?"""
    with conn.transaction(force_rollback=True):
        conn.execute("CREATE INDEX fts_measure ON chunks USING gin (tsv)")
        conn.execute("ANALYZE chunks")
        and_sql = SQL.format(tsquery=AND, rank="ts_rank_cd")
        for name, query_sql in (("and", and_sql), ("or (service)", FTS_SQL)):
            params = {
                "config": FTS_CONFIG,
                "query": question,
                "corpus": CORPUS,
                "doc_id": largest_doc,
                "chunker_id": CHUNKER,
                "k": K,
            }
            plan = conn.execute("EXPLAIN (ANALYZE, COSTS OFF) " + query_sql, params).fetchall()
            text = "\n".join(r[0] for r in plan)
            uses = "fts_measure" in text
            print(f"\n{name}, largest document, GIN index offered: planner uses it = {uses}")
            print(text)


if __name__ == "__main__":
    main()
