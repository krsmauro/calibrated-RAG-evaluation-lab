# Phase 3: Lexical, hybrid and rerank strategies; chunker C2; run store (Design Week 3)

**Goal:** all four retrieval strategies runnable through one reproducible CLI, with results stored append-only.
**Entry:** Phase 2 done.
**Exit criterion:** the same config run twice gives identical retrieval results.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 3.1 [ ] S1: Postgres full-text search
- **Do:** generated `tsvector` column plus GIN index (migration). Text-search config: start with `english`; comment why (and that `simple` disables stemming, which is the planned demo regression in Phase 8). The query is a long templated question: `websearch_to_tsquery` ANDs terms, so a whole question may match nothing. Decide and document how the query becomes a tsquery (OR semantics, stopword/template stripping, or keyword extraction). Name it "Postgres FTS", never "BM25".
- **Verify:** on dev, report the share of queries returning fewer than k rows for each approach; ADR 0009 updated with the choice and numbers. Integration test on real Postgres.
- **Refs:** Design §5.9, §7; finding F-002.

#### 3.2 [ ] S3: Reciprocal Rank Fusion
- **Do:** RRF over S1 and S2 rankings, smoothing constant as a parameter (start at the commonly used default; tune on dev only).
- **Verify:** Hypothesis tests: duplicates, ties, permutation of input order, empty input from one side. Hand-computed fixture.
- **Refs:** Design §7, §9 (Testing).

#### 3.3 [ ] S4: cross-encoder rerank
- **Do:** local cross-encoder rerank of the top N from S3, run off the event loop. Rerank depth N is a parameter tuned on dev. Measure the latency cost per query on stated hardware.
- **Verify:** reranker loaded once in lifespan; the latency number is recorded next to the quality delta in `docs/results.md`.
- **Refs:** Design §7, §8.6; skill BE-CRITICAL-2, BE-CRITICAL-3.

#### 3.4 [ ] Chunker C2: structure-aware
- **Do:** split on section/clause headings and numbering; fall back to C1 for long sections. Same offset invariants as C1. Ingest CUAD with C2 under its own `chunker_id`.
- **Verify:** the Phase 2 property tests run against C2 too. Report how many contracts hit the fallback. If C2 does not help, say so (Design §16 risk).
- **Refs:** Design §5.3, §7, §10.

#### 3.5 [ ] SQLite run store
- **Do:** `harness/store.py` with the schema in Design §6 (`runs, retrievals, query_metrics, answers, judgments`). Append-only: no UPDATE of stored results. Writes idempotent on `(run_id, query_id)`. Read-back through Pydantic since the schema can drift.
- **Verify:** test: writing the same row twice leaves one row; reopening the file and reading returns identical data; a schema-version mismatch fails loudly.
- **Refs:** Design §5.8, §6, §9 (Resilience); skill EVAL-CRITICAL-4.

#### 3.6 [ ] Run manifest
- **Do:** record per run: git SHA and dirty flag, config hash, eval-set hash, chunker id, strategy parameters, `uv.lock` hash, RNG seeds, hardware description. Model IDs and prompt hashes join in Phase 5.
- **Verify:** changing one config value changes the config hash; a dirty tree sets the flag.
- **Refs:** Design §8.6.

#### 3.7 [ ] `ragcalibrate run` (full)
- **Do:** experiment YAML (versioned; hash is the experiment identity), async runner with bounded concurrency, resumable (skips `(run_id, query_id)` already stored), one retry layer only with backoff and jitter. `--max-cost` flag exists but is a no-op until Phase 5.
- **Verify:** kill the run midway, resume, final store equals an uninterrupted run. Config validation errors are readable.
- **Refs:** Design §8.6, §9; `docs/llm-production-best-practices.md` (Retries and timeouts).

#### 3.8 [ ] Determinism test
- **Do:** make ranking deterministic: explicit tiebreak (for example by chunk id) after score sort, so equal scores cannot reorder between runs.
- **Verify:** run S1 to S4 twice; the `retrievals` tables are identical. If floating-point differences break exact equality for dense scores, record the tolerance in a finding and compare ranks, not raw scores.
- **Refs:** Design §11 (Week 3 exit).

#### 3.9 [ ] Run S1 to S4 and C1 vs C2 on dev
- **Do:** strategies compared at a fixed chunker; chunkers compared in a separate experiment at a fixed retrieved-token budget (not recall@k alone).
- **Verify:** runs stored; provisional numbers entered in `docs/results.md`; any surprising result (for example S1 beating S2) written up as a finding, not hidden.
- **Refs:** Design §5.2, §7.
