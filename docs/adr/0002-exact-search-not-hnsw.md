# ADR 0002: Exact search under the per-document filter, and no HNSW index

- **Status:** accepted
- **Date:** 2026-10-28
- **Step:** 2.8 (exact search vs HNSW under a per-document filter)

## Context
Retrieval is always within one contract (Design §5.1, eval-spec §1). The service's dense query (`DENSE_SQL` in `service/retrieval.py`) finds that contract's chunks through the `chunks` unique index, looks up each chunk's vector by primary key, and sorts them all by cosine distance: exact search. The question was whether an approximate HNSW index on `chunk_embeddings` would be faster without changing results. An approximate index under a selective filter has a known failure: it returns the nearest vectors in the whole table, and the filter can then leave fewer than k of them, or none.

Data at the time (step 2.6): 510 CUAD contracts, 24,872 C1 chunks with bge-small-en-v1.5 vectors (384 dimensions). One dev contract has 1 to 351 chunks (median 33), so a filter keeps 0.004% to 1.4% of the table. pgvector 0.8.7, Postgres 17, Docker on an Apple M5 laptop.

## Measurement
`uv run python scripts/measure_hnsw.py` (needs `make ingest` and `make evalsets`; about 11 minutes). It builds an HNSW index (`m` 16, `ef_construction` 64, the defaults; partial on the bge embedder id, on the expression `embedding::vector(384)` as an untyped column requires) inside a transaction that is rolled back, so the database is left unchanged. Building it took 1.6 s; it is 49 MB. Then, for every one of the 408 dev contracts and each of the 41 questions (16,728 pairs, k = 10), it runs the exact service query and three HNSW variants. "Short" means fewer rows than the contract can give, `min(k, chunks)`. Latency is measured in the client per query, so it includes a local round trip.

| Variant | Short results | Contracts affected | Top-10 overlap with exact | Same ranked list | p50 ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Exact (service query) | 0 | 0 | 1.0000 | 1.0000 | 0.56 | 1.74 |
| HNSW, planner left to choose | 41 | 1 | 0.9976 | 0.9975 | 0.38 | 1.50 |
| HNSW forced, `ef_search` 40 | 16,725 | 408 | 0.0081 | 0.0002 | 0.72 | 1.91 |
| HNSW forced + iterative scan, `strict_order` | 2,386 | 120 | 0.9047 | 0.5606 | 18.95 | 25.08 |
| HNSW forced + iterative scan, `relaxed_order` | 2,298 | 119 | 0.9321 | 0.6654 | 18.80 | 25.01 |

("Forced" sets `enable_sort = off` so the planner uses the index; iterative scans use pgvector's default `hnsw.max_scan_tuples` of 20,000.)

What the plans show (full output from the script; the query vector is elided):

**Exact, largest dev contract (351 chunks): 0.43 ms, 10 rows.**
```text
Limit (actual time=0.414..0.415 rows=10 loops=1)
  ->  Sort (actual time=0.414..0.415 rows=10 loops=1)
        Sort Key: (('1'::double precision - (e.embedding <=> '<query vector>'::vector))) DESC, c.start_char
        Sort Method: top-N heapsort  Memory: 57kB
        ->  Nested Loop (actual time=0.020..0.370 rows=351 loops=1)
              ->  Nested Loop (actual time=0.017..0.120 rows=351 loops=1)
                    ->  Index Scan using documents_corpus_external_id_key on documents d (rows=1)
                    ->  Index Scan using chunks_document_id_chunker_id_start_char_end_char_key on chunks c (rows=351)
              ->  Index Scan using chunk_embeddings_pkey on chunk_embeddings e (rows=1 loops=351)
Execution Time: 0.428 ms
```

**HNSW, planner's own choice, same contract: 0 rows.** With the index present, the planner picks it for this contract. The index returns the 40 nearest chunks of the whole corpus (`ef_search`), none of them in this contract, and the filter removes all 40. All 41 short results in the table are this contract: every question about the largest contract in the corpus would return nothing, silently.
```text
Limit (actual time=0.429..0.429 rows=0 loops=1)
  ->  Nested Loop (actual time=0.429..0.429 rows=0 loops=1)
        ->  Index Scan using hnsw_measure on chunk_embeddings e (actual time=0.369..0.381 rows=40 loops=1)
              Order By: ((embedding)::vector(384) <=> '<query vector>'::vector(384))
        ->  Index Scan using chunks_pkey on chunks c (actual time=0.001..0.001 rows=0 loops=40)
              Filter: ((chunker_id = '...') AND (document_id = '87'::smallint))
              Rows Removed by Filter: 1
Execution Time: 0.433 ms
```

**HNSW with iterative scan, smallest dev contract (1 chunk): 21 ms, 0 rows.** The scan visits 19,877 of 24,872 vectors, reaches the 20,000-tuple limit and stops without finding the contract's one chunk. Exact search answers the same query in 0.04 ms.
```text
Limit (actual time=20.919..20.919 rows=0 loops=1)
  ->  Nested Loop (actual time=20.918..20.919 rows=0 loops=1)
        Join Filter: (c.id = e.chunk_id)
        Rows Removed by Join Filter: 19877
        ->  Index Scan using hnsw_measure on chunk_embeddings e (actual time=0.191..18.231 rows=19877 loops=1)
        ->  Materialize (rows=1 loops=19877)
              ->  Index Scan using chunks_document_id_chunker_id_start_char_end_char_key on chunks c (rows=1)
Execution Time: 20.925 ms
```

**HNSW results also change between index builds.** The script was run twice, each time on a newly built index. Exact search, the planner's choice and the forced variant gave the same short counts both times. The iterative variants did not: 2,341 then 2,386 short results (`strict_order`) and 2,256 then 2,298 (`relaxed_order`), most likely because HNSW assigns graph levels at random when it builds (not verified, for example by querying one index twice). Either way, a rebuild alone would move retrieval metrics, which an evaluation tool cannot accept as noise it does not control.

## Decision
Keep exact search, and create no ANN index on `chunk_embeddings`. Exact search is already sub-millisecond at the median (0.56 ms) and returns the true top k for every query. Every HNSW variant either returns short results for some contracts, or is about 34 times slower, or both, and an index rebuild can change its results.

## Alternatives considered
- **HNSW with default settings.** Loses: almost every query returns fewer than k rows (16,725 of 16,728).
- **HNSW and let the planner decide.** Loses: it saves about 0.2 ms at the median, and for the largest contract it silently returns nothing. The planner's estimate cannot see that the index's 40 candidates will all be filtered away.
- **HNSW with iterative scans** (pgvector 0.8). Loses: 18.8 to 19 ms at the median, about 34 times slower than exact, and still short in 119 to 120 of 408 contracts, because the scan stops at `max_scan_tuples`. Raising that limit to the table size turns it into a slower full scan.
- **A larger `ef_search`.** Not measured separately. To find a 1-chunk contract it must reach most of the table, which is what the iterative-scan rows show.
- **One partial HNSW index per contract.** Loses: 510 indexes, one per document, to speed up a query that already takes under a millisecond.

## Consequences
- Retrieval numbers come from exact search, so no metric in this project carries ANN recall loss. A strategy comparison measures the strategy, not the index.
- Cost grows with the size of one contract, not the corpus: about 1 ms per 350 chunks at 384 dimensions. A 1536-dimension hosted model (step 4.10) costs about 4 times the distance arithmetic per row. That is still a few milliseconds, but 4.10 should measure it rather than assume it.
- The service's query uses the plain `<=>` on the untyped column, so an expression index on `embedding::vector(384)` could not be used by it even if one existed. Anyone adding such an index for an experiment must rerun this script: the planner's-choice row shows how a new index can silently change results.
- Revisit if retrieval becomes corpus-wide (the filter disappears and ANN indexes are the standard tool), or if one document grows to tens of thousands of chunks.
