# Phase 3: Lexical, hybrid and rerank strategies; chunker C2; run store (Design Week 3)

**Goal:** all four retrieval strategies runnable through one reproducible CLI, with results stored append-only.
**Entry:** Phase 2 done.
**Exit criterion:** the same config run twice gives identical retrieval results.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 3.1 [x] S1: Postgres full-text search
Claimed: Claude (Opus 5.5, VS Code session), 2026-10-28
- **Do:** generated `tsvector` column plus GIN index (migration). Text-search config: start with `english`; comment why (and that `simple` disables stemming, which is the planned demo regression in Phase 8). The query is a long templated question: `websearch_to_tsquery` ANDs terms, so a whole question may match nothing. Decide and document how the query becomes a tsquery (OR semantics, stopword/template stripping, or keyword extraction). Name it "Postgres FTS", never "BM25".
- **Verify:** on dev, report the share of queries returning fewer than k rows for each approach; ADR 0009 updated with the choice and numbers. Integration test on real Postgres.
- **Refs:** Design §5.9, §7; finding F-002.
- Note (2026-10-28, from 2.7): `/retrieve` does not dispatch on `strategy` yet. It always embeds the query and calls `retrieval.dense`, which was safe only while `Strategy` in `ragcalibrate/contract.py` is `Literal["dense"]`. Adding S1 means extending that literal, dispatching on it in `service/routes.py`, skipping the embedder for a lexical strategy and returning `embedder_id: null` (the response model already documents null for lexical). The tsvector migration must also bump `SCHEMA_REVISION` in `service/routes.py`; `tests/unit/test_contract.py` fails until it equals Alembic's head. Integration-test fixtures (testcontainers) are in `tests/integration/conftest.py`.
- **Done:** 2026-10-28, Claude (Opus 5.5, VS Code session). Migration 0003 adds `chunks.tsv`, a stored generated `to_tsvector('english', text)`; `/retrieve` takes `strategy: "fts"` (S1) next to `"dense"`, with no embedder and `embedder_id: null`, and rejects an `embedder_id` sent with `fts`. Six ways of building the tsquery were measured on dev; S1 is an OR over the question's lexemes ranked with `ts_rank`. `websearch_to_tsquery` (AND) returned no rows for 84% of dev queries (F-002 confirmed and resolved). `ragcalibrate run` gained `--strategy`.
  Evidence: `uv run python scripts/measure_fts.py`: short (fewer rows than min(10, chunks)) / empty / recall@5 per approach: AND 94.8% / 84.0% / 0.048; OR `ts_rank_cd` 7.4% / 0.2% / 0.515; **OR `ts_rank` (chosen) 7.4% / 0.2% / 0.560**; OR without template wording 12.2% / 0.3% / 0.533; category only AND 87.7% / 48.2% / 0.314; category only OR 47.7% / 3.5% / 0.589 (table in ADR 0009). `uv run ragcalibrate run --strategy fts`: recall@5 0.560, MRR@10 0.455, n = 5,458 (results ledger), identical in a second run; a rerun of `--strategy dense` gave per-query rankings identical to the committed S2 baseline. With a GIN index offered, `EXPLAIN ANALYZE` on the largest contract uses the unique btree index for both AND and OR. `make lint` clean (ruff, format, pyright strict, import-linter); `make test` 64 passed; `make test-integration` 34 passed (15 new: S1 ranking, offsets and tiebreak, stemming, matches only, empty answers, query-syntax characters including a URL that yields a quoted lexeme, the configuration matching the column, S1 error cases); `alembic downgrade -1` then `upgrade head` on the local database rebuilds `tsv` for all 24,872 chunks.
  Files: `migrations/versions/0003_chunks_tsv.py` (new), `scripts/measure_fts.py` (new), `src/ragcalibrate/contract.py`, `src/ragcalibrate/service/retrieval.py`, `src/ragcalibrate/service/routes.py`, `src/ragcalibrate/harness/cli.py`, `tests/unit/test_contract.py`, `tests/integration/test_service.py`, `docs/adr/0009-postgres-fts-is-not-bm25.md`, `docs/findings/F-002-fts-query-semantics.md`, `docs/findings/F-011-fts-beats-dense-on-cuad-dev.md` (new), `docs/findings/F-004-ceiling-effect-per-document-retrieval.md`, `docs/results.md`, `docs/phases/phase-8-full-gate-and-demo-prs.md` (note under 8.5), `.claude/skills/master-code-skill/references/python/database-rules.md` (DB-HIGH-2 no longer says to use `websearch_to_tsquery`), `.claude/skills/master-code-skill/SKILL.md` (state line), `README.md`, `docs/project-plan.md`.
  Deviations: (1) no GIN index, though the step says "plus GIN index": the planner does not use one under the per-document filter (ADR 0009). (2) `ts_rank` instead of Design §7's `ts_rank_cd`, chosen on dev (4.5 points of recall@5). (3) S1 beats S2 on dev; written up as finding F-011 now rather than waiting for 3.9. The results-ledger S1 row was measured on a dirty tree (these changes uncommitted) and should be rerun on the commit.

#### 3.2 [ ] S3: Reciprocal Rank Fusion
- **Do:** RRF over S1 and S2 rankings, smoothing constant as a parameter (start at the commonly used default; tune on dev only).
- **Verify:** Hypothesis tests: duplicates, ties, permutation of input order, empty input from one side. Hand-computed fixture.
- **Refs:** Design §7, §9 (Testing).
- Note (2026-10-28, from 3.1): the empty side is real, not only a test case: S1 returns only chunks that share a word with the query, fewer than 10 for 500 of 5,458 dev queries and none for 13. Decide how deep each side's list is (fusing two top-10 lists is not the same as fusing two top-100 lists) and treat that depth as a parameter. S1 is now the strongest single strategy on dev (F-011), so S3 has to beat S1, not just S2. Dispatch is a `match` on `strategy` in `service/routes.py`; pyright flags a missing case.

#### 3.3 [ ] S4: cross-encoder rerank
- **Do:** local cross-encoder rerank of the top N from S3, run off the event loop. Rerank depth N is a parameter tuned on dev. Measure the latency cost per query on stated hardware.
- **Verify:** reranker loaded once in lifespan; the latency number is recorded next to the quality delta in `docs/results.md`.
- **Refs:** Design §7, §8.6; skill BE-CRITICAL-2, BE-CRITICAL-3.
- Note (2026-10-28, from 2.7): models loaded once live in `Resources` (`service/deps.py`), built in the lifespan in `service/app.py`. Add the reranker there and call it through `asyncio.to_thread`, as `/retrieve` does for the embedder.

#### 3.4 [ ] Chunker C2: structure-aware
- **Do:** split on section/clause headings and numbering; fall back to C1 for long sections. Same offset invariants as C1. Ingest CUAD with C2 under its own `chunker_id`.
- **Verify:** the Phase 2 property tests run against C2 too. Report how many contracts hit the fallback. If C2 does not help, say so (Design §16 risk).
- **Refs:** Design §5.3, §7, §10.
- Note (2026-10-28, from 2.6): `ingest_documents` and `embed_chunks` in `ingest/load.py` take any chunker id and chunk function, so C2 is a second call over the same documents and is resumable the same way. `scripts/ingest.py` is hard-wired to C1 and needs a way to pick the chunker. C1's id names its tokenizer and parameters (`c1v1:bge-small-en-v1.5@5c38ec7c405e:size=256:overlap=32`); give C2's id the same treatment. The same offset checks apply: `count_offset_mismatches` must return 0.

#### 3.5 [ ] SQLite run store
- **Do:** `harness/store.py` with the schema in Design §6 (`runs, retrievals, query_metrics, answers, judgments`). Append-only: no UPDATE of stored results. Writes idempotent on `(run_id, query_id)`. Read-back through Pydantic since the schema can drift.
- **Verify:** test: writing the same row twice leaves one row; reopening the file and reading returns identical data; a schema-version mismatch fails loudly.
- **Refs:** Design §5.8, §6, §9 (Resilience); skill EVAL-CRITICAL-4.

#### 3.6 [ ] Run manifest
- **Do:** record per run: git SHA and dirty flag, config hash, eval-set hash, chunker id, strategy parameters, `uv.lock` hash, RNG seeds, hardware description. Model IDs and prompt hashes join in Phase 5.
- **Verify:** changing one config value changes the config hash; a dirty tree sets the flag.
- **Refs:** Design §8.6.
- Note (2026-10-28, from 2.7 and 4.10): add the embedder id to the list above; step 4.10 compares two embedders on the same chunks and needs it. The 2.10 JSON manifest already records `git_sha`, `git_dirty`, `evalset_hash`, `corpus`, `split`, `strategy`, `chunker_id`, `embedder_id` (the one the service reports it used), `k` and `base_url`; keep all of them.

#### 3.7 [ ] `ragcalibrate run` (full)
- **Do:** experiment YAML (versioned; hash is the experiment identity), async runner with bounded concurrency, resumable (skips `(run_id, query_id)` already stored), one retry layer only with backoff and jitter. `--max-cost` flag exists but is a no-op until Phase 5.
- **Verify:** kill the run midway, resume, final store equals an uninterrupted run. Config validation errors are readable.
- **Refs:** Design §8.6, §9; `docs/llm-production-best-practices.md` (Retries and timeouts).
- Note (2026-10-28, from 2.10): `harness/run.py` and `harness/cli.py` are the minimal version: answerable dev queries only, one JSON file per run in the gitignored `runs/`, no retries, no resume. 3.5 to 3.7 replace the JSON file and the flags; keep the eval-set hash check, the per-query rankings and the per-category table. The CLI logs every HTTP request at INFO through httpx's logger (one line per query, 5,458 on dev), which buries the summary; quiet that logger in the rewrite.

#### 3.8 [ ] Determinism test
- **Do:** make ranking deterministic: explicit tiebreak (for example by chunk id) after score sort, so equal scores cannot reorder between runs.
- **Verify:** run S1 to S4 twice; the `retrievals` tables are identical. If floating-point differences break exact equality for dense scores, record the tolerance in a finding and compare ranks, not raw scores.
- **Refs:** Design §11 (Week 3 exit).
- Note (2026-10-28, from 2.7): S2 already breaks ties by position (`ORDER BY score DESC, c.start_char` in `DENSE_SQL`). Use the same rule for the other strategies, RRF included, so ties sort the same way everywhere.
- Note (2026-10-28, from 3.1): S1 (`FTS_SQL`) uses the same tiebreak, and `ts_rank` produces many equal scores, so the tiebreak matters there. Two S1 runs on dev already gave identical rankings and scores.

#### 3.9 [ ] Run S1 to S4 and C1 vs C2 on dev
- **Do:** strategies compared at a fixed chunker; chunkers compared in a separate experiment at a fixed retrieved-token budget (not recall@k alone).
- **Verify:** runs stored; provisional numbers entered in `docs/results.md`; any surprising result (for example S1 beating S2) written up as a finding, not hidden.
- **Refs:** Design §5.2, §7.
- Note (2026-10-28, from 2.10): the S2 baseline is the first row in `docs/results.md`. F-004 asks for the ceiling check on S4 here. F-008's note says the front-matter categories (Parties, Document Name, Agreement Date) are among the hardest for S2, and a lexical strategy may behave very differently on them, so report per category.
- Note (2026-10-28, from 3.1): S1 beats S2 on dev (recall@5 0.560 vs 0.489; finding F-011, with per-category numbers and the caveat that S1's ranking function was tuned on dev). On the front-matter categories S1 is ahead on Agreement Date and Effective Date, about even on Parties and Document Name; both strategies are weak there.
