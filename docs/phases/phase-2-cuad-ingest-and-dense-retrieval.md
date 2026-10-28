# Phase 2: CUAD, chunker C1, dense retrieval, retrieval metrics (Design Week 2)

**Goal:** a reproducible baseline number for dense retrieval (S2) on the CUAD dev set, with the offset and metric machinery proven by tests.
**Entry:** Phase 1 done (needs `eval-spec.md` for the relevance rule and metric definitions).
**Exit criterion:** offset property tests and metric fixture tests pass; one command reproduces dev recall@5 and MRR for S2.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 2.1 [x] `make data`: download and verify CUAD
- **Do:** script that downloads CUAD, verifies the checksum recorded in the CUAD-facts finding (step 1.7), and extracts into a gitignored `data/` directory. Idempotent. The raw dataset is never committed.
- **Verify:** running it twice is a no-op the second time; a corrupted file fails the checksum with a readable error.
- **Refs:** Design §10.
- Claimed: Claude, 2026-10-19
- **Done:** 2026-10-19, Claude. `scripts/fetch_cuad.py` (built in Phase 1) already downloads the pinned `data.zip` and verifies size and sha256; nothing new was written.
  Evidence: `make data` run twice prints `ok` both times and downloads nothing the second time; a 1000-byte truncated copy in a scratch directory exits 1 with `CHECKSUM MISMATCH ... delete it and investigate`.
  Files: none.
  Deviations: the step says "extracts into `data/`"; the zip is deliberately not extracted, later code reads members in memory (see the script's docstring), which is safer for untrusted input.

#### 2.2 [x] CUAD adapter: documents, queries, gold spans
- **Do:** `corpora/cuad.py` yields `Document`, `Query` and `GoldSpan` objects. Pydantic validates the file boundary only. Offsets are half-open character offsets into the **raw** text exactly as CUAD labeled it (no normalization, so Design §5.3 holds by construction). Queries with no gold span are kept, with `answerable = false`.
- **Verify:** unit test on a fixture contract: for every gold span, `doc.text[start:end]` equals the label text. A full-dataset check runs as an integration test or script and reports any mismatches by count.
- **Refs:** Design §5.1, §5.3, §5.4; skill EVAL-CRITICAL-2.
- Claimed: Claude, 2026-10-19
- **Done:** 2026-10-19, Claude. `corpora/schema.py` (frozen Pydantic types `Document`, `Query`, `Gold`, `GoldSpan`) and `corpora/cuad.py` (`load_cuad`) read `CUADv1.json` and `test.json` from the zip in memory. Raw text is untouched; unanswerable pairs are kept (empty spans).
  Evidence: `tests/unit/test_cuad.py` (fixture contract: every span slices back to its label text; a wrong offset raises) and `tests/unit/test_cuad_full.py` on the real data: 510 documents, 20,910 queries, 13,823 spans, 0 label/text mismatches (`load_cuad` raises on the first one), matching F-008.
  Files: `src/ragcalibrate/corpora/{schema,cuad}.py`, `tests/unit/test_cuad.py`, `tests/unit/test_cuad_full.py`, `pyproject.toml` and `uv.lock` (`pydantic` added as a direct dependency; it was only transitive).
  Deviations: `answerable` and the category are on `Gold`, not on `Query`, so the type the harness sends to the service carries no label (ADR 0005). `answerable` is derived from the spans so the two cannot disagree. The full-dataset check is a skipped-if-no-data unit test, not an integration test, because CI does not download CUAD.

#### 2.3 [x] Splits and the hashed eval sets
- **Do:** keep CUAD's shipped test split as test. Carve dev out of train **by contract** (never split a contract's 41 queries), with a recorded seed. Write `evalsets/cuad-{dev,test}.queries.jsonl` and `.gold.jsonl`, plus a hash file. Queries and gold live in separate files so the gold file can never be loaded by the service. Add CC BY attribution in an `evalsets/README`.
- **Verify:** test asserting no `document_id` appears in two splits; hash is stable across two generations; the service package contains no reference to `evalsets/`.
- **Refs:** Design §5.10, §8.1, §10; skill EVAL-CRITICAL-1.
- Claimed: Claude, 2026-10-19
- **Done:** 2026-10-19, Claude. `corpora/evalsets.py` builds deterministic JSONL files and `evalsets/cuad.manifest.json` (sha256 per file, source zip hash, counts, `evalset_hash`); `scripts/build_evalsets.py` and `make evalsets` generate them, `--check` verifies the disk against the pinned source. Queries and gold are separate files.
  Evidence: `evalset_hash 34987d1bf1ea...` identical on two generations; counts dev 408 documents / 16,728 queries / 5,458 answerable and test 102 / 4,182 / 1,244, equal to F-008. Unit tests: no document in two splits, hash changes when a label changes, tamper detection, and the service package contains none of `evalsets`, `ragcalibrate.harness`, `Gold`-importing code (the service is empty today, so this is a guard for later).
  Files: `src/ragcalibrate/corpora/evalsets.py`, `scripts/build_evalsets.py`, `evalsets/README.md` (CC BY attribution), `evalsets/cuad.manifest.json`, `Makefile`, `.gitignore`, `tests/unit/test_cuad.py`.
  Deviations: (1) No random seed: eval-spec section 7 says dev is all of CUAD's train split, so nothing is carved at random (the CI-subset seed belongs to Phase 4). (2) The four `.jsonl` files (about 19 MB) are gitignored; only the manifest is committed, and the files regenerate byte for byte. **Decision for the user**: if you prefer them committed, remove the `.gitignore` line; the cost is 19 MB in history on every change.

#### 2.4 [x] Chunker C1 (fixed-size token windows with overlap)
- **Do:** `ingest/chunkers.py` with a versioned `chunker_id` (parameters in the id). Uses the embedding model's tokenizer so a chunk never exceeds the model's context. Returns `(start_char, end_char, text)`. Chunk size and overlap are parameters; the defaults are tuned on dev only, later.
- **Verify:** Hypothesis property tests: `doc.text[c.start:c.end] == c.text`; chunks cover the document; no chunk exceeds the token limit; deterministic for the same input.
- **Refs:** Design §5.3, §7, §9 (Testing).
- Claimed: Claude, 2026-10-28. Starting defaults chosen by the user on 2026-10-28: 256 tokens, 32 overlap.
- **Done:** 2026-10-28, Claude. `ingest/chunkers.py`: `chunk_c1(text, tokenizer, size, overlap)` returns `Chunk(start_char, end_char, text)` windows of the bge tokenizer's tokens, with edges moved to word starts so a chunk re-tokenizes to exactly its window and never starts or ends mid-word. `c1_id` names version, tokenizer and parameters (`c1v1:bge-small-en-v1.5@5c38ec7c405e:size=256:overlap=32`).
  Evidence: `tests/property/test_chunker_c1.py`, 12 tests: Hypothesis properties (exact ordered slices, every token inside a chunk, no chunk over its window, zero overlap means disjoint, deterministic), a hand-worked example, the long-word split, empty input, bad parameters. Hypothesis found one bug during development (a window whose end moved back produced a chunk inside the previous one, input `"The The Licensee"`, size 2, overlap 1); fixed and covered. Passes with five seeds and the derandomized CI profile. On all 510 CUAD contracts at 256/32: 24,872 chunks (per contract min 1, median 30, p95 160, max 351), longest re-tokenized chunk 256 tokens, 0 words split, median chunk 1,255 characters, 87.0% of gold spans (12,021 of 13,823) lie wholly inside one chunk, top 5 chunks are 16.7% of a median contract. Contracts are 6,739 tokens at the median (p95 35,681, max 78,591; F-008 estimated about 8,300 from chars/4). No contract contains a NUL character (Postgres text would reject it). Chunking all of CUAD takes 8.3 s.
  Files: `src/ragcalibrate/ingest/chunkers.py`, `tests/property/test_chunker_c1.py`, `tests/conftest.py` (Hypothesis `ci` profile, derandomized when `CI` is set), `pyproject.toml` and `uv.lock` (`hypothesis` dev dependency).
  Deviations: chunks follow word boundaries, which the step did not ask for; the reason is in the docstring. A single word longer than the window is split (none in CUAD at 256). The chunker takes the tokenizer as an argument and the id names it, so another embedding model can embed the same chunks (see ADR 0011, Consequences).

#### 2.5 [x] Choose and wrap the local embedding model
- **Do:** pick a local embedding model. Decision criteria: license permits the use, fits CPU in CI, context length at least the chunk size, runtime per chunk. Record the choice, version/revision and the benchmark in a finding or ADR. Embedding is CPU-bound: run it off the event loop (`asyncio.to_thread` or a process pool) and batch it.
- **Verify:** embedding the same text twice gives the same vector (or document the tolerance); throughput measured on stated hardware.
- **Refs:** Design §7 (local models); skill BE-CRITICAL-2.
- Claimed: Claude, 2026-10-28. Model chosen by the user on 2026-10-28: `BAAI/bge-small-en-v1.5`.
- **Done:** 2026-10-28, Claude. `ingest/embedding.py`: `Embedder` runs the model's own ONNX export with ONNX Runtime on CPU (CLS pooling, L2 norm, batched), pinned to commit `5c38ec7c4...`; `scripts/fetch_models.py` and `make models` download and sha256-check the two files into `data/models/`. ADR 0011 records the choice, alternatives and numbers.
  Evidence: against sentence-transformers 6.2.0 on 241 CUAD texts, min cosine 0.9999998, max abs difference 3.6e-7, identical top-10 rankings for all 41 questions. Same text twice: bitwise identical; alone vs in a padded batch: at most 9.7e-8. Throughput on an Apple M5 (10 cores): 59 chunks/s at batch 16 (all of CUAD in about 7 minutes), 4.4 ms per question. `make models` twice: second run downloads nothing. `tests/unit/test_embedding.py`, 6 tests (pinned reference values, shape and norm, empty input, determinism, batching tolerance, a relevance sanity check). Whole suite 53 passed; ruff, format and pyright clean; `actionlint` clean.
  Files: `src/ragcalibrate/ingest/embedding.py`, `scripts/fetch_models.py`, `tests/unit/test_embedding.py`, `docs/adr/0011-local-embedding-model-onnx.md`, `Makefile` (`models`), `.github/workflows/ci.yml` (test job runs `make models`), `README.md` (commands), `pyproject.toml` and `uv.lock` (`onnxruntime`, `tokenizers`, `numpy`).
  Deviations: ONNX Runtime instead of sentence-transformers and PyTorch (ADR 0011). Embedding is batched but not yet called off the event loop, because there is no async caller yet; the module docstring requires `asyncio.to_thread`, and step 2.7 must do it. The CI change is untested until you push. No query instruction prefix (ADR 0011).

#### 2.6 [ ] Idempotent ingest with bulk load
- **Do:** `ingest` keyed on document content hash; chunks keyed on `(document_id, chunker_id, start_char, end_char)`; bulk-load with `COPY`; migration adds the B-tree on `(document_id, chunker_id)`. `make ingest` ingests all CUAD documents with C1.
- **Verify:** integration test against real Postgres via testcontainers: ingest twice, row counts unchanged; an interrupted ingest resumes cleanly.
- **Refs:** Design §6, §9 (Database).
- Note (2026-10-28, from 2.5): store embeddings in their own table keyed by `(chunk_id, embedder_id)` rather than as a fixed `vector(384)` column on `chunks`, so a second embedding model can be compared on the same chunks without a schema rewrite (ADR 0011).

#### 2.7 [ ] Service skeleton and `/retrieve` for S2
- **Do:** FastAPI app with lifespan-created pool and model. Wire models (`RetrieveRequest`, `RetrieveResponse`) live in **one** module imported by both `service` and the harness adapter. `POST /retrieve {query, doc_id, strategy, chunker_id, k}` returns chunks with offsets and scores. `GET /healthz`, `GET /readyz`. Errors as RFC 9457 problem details through one registered handler. Add the import-linter contract: `harness` must not import `service`, and `service` must not import `harness`.
- **Verify:** `httpx` async client test; OpenAPI schema matches; import-linter passes; the request model has no `gold`, `answerable` or `expected` field.
- **Refs:** Design §6, §9 (API, Boundaries); skill XC-CRITICAL-3, EVAL-CRITICAL-1.

#### 2.8 [ ] Exact search vs HNSW under a per-document filter
- **Do:** measure, on the real data, exact search versus an HNSW index with the filter (including pgvector's iterative scans if the installed version supports them): latency from `EXPLAIN ANALYZE`, and whether HNSW ever returns fewer than k rows. Write ADR 0002 with the numbers. Default stays exact search unless the data says otherwise.
- **Verify:** ADR contains the query plans and the counts of short results.
- **Refs:** Design §5.1, §12 (ADR 2).

#### 2.9 [x] Retrieval metrics
- **Do:** `harness/metrics/retrieval.py`: span-overlap function, Hit@k, Recall@k, MRR@k, character precision/recall at a token budget B. Overlap threshold comes from `eval-spec.md` and is a parameter, so the sensitivity analysis is possible. Pure functions.
- **Verify:** write the hand-computed fixtures first. Cover: no gold spans (undefined, excluded, not zero), duplicate chunks, overlapping gold spans, a gold span split across two chunks, ties.
- **Refs:** Design §8.2; skill EVAL-CRITICAL-2.
- Claimed: Claude, 2026-10-19
- **Done:** 2026-10-19, Claude. `harness/metrics/retrieval.py`: `overlap`, `merge_spans`, `dedupe`, `hit_at_k`, `recall_at_k`, `mrr_at_k` and `char_precision_recall_at_budget`. The overlap rule is a parameter (`min_overlap_frac`: 0 is R1, 0.5 is R2 with the spec's `min(span, chunk)` form). Undefined cases return `None`.
  Evidence: `tests/unit/test_retrieval_metrics.py`, 17 tests with hand-computed values written before the code, covering no gold, empty results, duplicate chunks, overlapping gold spans, a span split across chunks, half-open adjacency, k beyond the list, R2 and the token-budget cut. Two deliberate mutations (merge on adjacency; no dedupe) each made a test fail. Whole suite: 35 passed; ruff and pyright clean.
  Files: `src/ragcalibrate/harness/metrics/{__init__,retrieval}.py`, `tests/unit/test_retrieval_metrics.py`.
  Deviations: the tokenizer is injected as `token_ends(text) -> list[int]` because the real one is chosen in step 4.9 (ADR 0004); the tests use a whitespace tokenizer, so the token-budget metric is verified but not yet usable on real data. Ties in a ranking are not handled here: the metric takes the order it is given.

#### 2.10 [ ] Minimal `ragcalibrate run` for S2 and the baseline number
- **Do:** harness HTTP adapter plus a minimal run command: dev queries, answerable only, S2, C1. Writes a JSON result (the SQLite run store replaces this in Phase 3). Report recall@k for several k, not only 5 (see F-004), plus MRR.
- **Verify:** one command reproduces the numbers twice. Record the values in `docs/results.md` as provisional (dev, not final).
- **Refs:** Design §8.2; finding F-004.

#### 2.11 [x] Write `references/eval/eval-integrity-rules.md`
- **Do:** short checklist for leakage, ground truth, metric definitions, manifests, abstention, drawn from Design §5 and the skill's inline EVAL rules.
- **Verify:** file exists and SKILL.md's map is updated.
- **Done:** 2026-10-28, Claude. Nothing new written: the file was created in step 0.4 (Phase 0) and already covers leakage (EVAL-CRITICAL-1), ground truth and span overlap (-2), chunk-size bias (-3), abstention (-4), dev/test discipline (-5), metric definitions (EVAL-HIGH-1), manifests (-2), append-only runs (-3) and honest reporting (-4).
  Evidence: the file exists (57 lines, ten rule sections); SKILL.md links it twice (routing table and reference map).
  Files: none.
  Deviations: the step was already satisfied by Phase 0 work.
