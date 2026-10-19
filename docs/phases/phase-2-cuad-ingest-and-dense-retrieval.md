# Phase 2: CUAD, chunker C1, dense retrieval, retrieval metrics (Design Week 2)

**Goal:** a reproducible baseline number for dense retrieval (S2) on the CUAD dev set, with the offset and metric machinery proven by tests.
**Entry:** Phase 1 done (needs `eval-spec.md` for the relevance rule and metric definitions).
**Exit criterion:** offset property tests and metric fixture tests pass; one command reproduces dev recall@5 and MRR for S2.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 2.1 [ ] `make data`: download and verify CUAD
- **Do:** script that downloads CUAD, verifies the checksum recorded in the CUAD-facts finding (step 1.7), and extracts into a gitignored `data/` directory. Idempotent. The raw dataset is never committed.
- **Verify:** running it twice is a no-op the second time; a corrupted file fails the checksum with a readable error.
- **Refs:** Design §10.

#### 2.2 [ ] CUAD adapter: documents, queries, gold spans
- **Do:** `corpora/cuad.py` yields `Document`, `Query` and `GoldSpan` objects. Pydantic validates the file boundary only. Offsets are half-open character offsets into the **raw** text exactly as CUAD labeled it (no normalization, so Design §5.3 holds by construction). Queries with no gold span are kept, with `answerable = false`.
- **Verify:** unit test on a fixture contract: for every gold span, `doc.text[start:end]` equals the label text. A full-dataset check runs as an integration test or script and reports any mismatches by count.
- **Refs:** Design §5.1, §5.3, §5.4; skill EVAL-CRITICAL-2.

#### 2.3 [ ] Splits and the hashed eval sets
- **Do:** keep CUAD's shipped test split as test. Carve dev out of train **by contract** (never split a contract's 41 queries), with a recorded seed. Write `evalsets/cuad-{dev,test}.queries.jsonl` and `.gold.jsonl`, plus a hash file. Queries and gold live in separate files so the gold file can never be loaded by the service. Add CC BY attribution in an `evalsets/README`.
- **Verify:** test asserting no `document_id` appears in two splits; hash is stable across two generations; the service package contains no reference to `evalsets/`.
- **Refs:** Design §5.10, §8.1, §10; skill EVAL-CRITICAL-1.

#### 2.4 [ ] Chunker C1 (fixed-size token windows with overlap)
- **Do:** `ingest/chunkers.py` with a versioned `chunker_id` (parameters in the id). Uses the embedding model's tokenizer so a chunk never exceeds the model's context. Returns `(start_char, end_char, text)`. Chunk size and overlap are parameters; the defaults are tuned on dev only, later.
- **Verify:** Hypothesis property tests: `doc.text[c.start:c.end] == c.text`; chunks cover the document; no chunk exceeds the token limit; deterministic for the same input.
- **Refs:** Design §5.3, §7, §9 (Testing).

#### 2.5 [ ] Choose and wrap the local embedding model
- **Do:** pick a local embedding model. Decision criteria: license permits the use, fits CPU in CI, context length at least the chunk size, runtime per chunk. Record the choice, version/revision and the benchmark in a finding or ADR. Embedding is CPU-bound: run it off the event loop (`asyncio.to_thread` or a process pool) and batch it.
- **Verify:** embedding the same text twice gives the same vector (or document the tolerance); throughput measured on stated hardware.
- **Refs:** Design §7 (local models); skill BE-CRITICAL-2.

#### 2.6 [ ] Idempotent ingest with bulk load
- **Do:** `ingest` keyed on document content hash; chunks keyed on `(document_id, chunker_id, start_char, end_char)`; bulk-load with `COPY`; migration adds the B-tree on `(document_id, chunker_id)`. `make ingest` ingests all CUAD documents with C1.
- **Verify:** integration test against real Postgres via testcontainers: ingest twice, row counts unchanged; an interrupted ingest resumes cleanly.
- **Refs:** Design §6, §9 (Database).

#### 2.7 [ ] Service skeleton and `/retrieve` for S2
- **Do:** FastAPI app with lifespan-created pool and model. Wire models (`RetrieveRequest`, `RetrieveResponse`) live in **one** module imported by both `service` and the harness adapter. `POST /retrieve {query, doc_id, strategy, chunker_id, k}` returns chunks with offsets and scores. `GET /healthz`, `GET /readyz`. Errors as RFC 9457 problem details through one registered handler. Add the import-linter contract: `harness` must not import `service`, and `service` must not import `harness`.
- **Verify:** `httpx` async client test; OpenAPI schema matches; import-linter passes; the request model has no `gold`, `answerable` or `expected` field.
- **Refs:** Design §6, §9 (API, Boundaries); skill XC-CRITICAL-3, EVAL-CRITICAL-1.

#### 2.8 [ ] Exact search vs HNSW under a per-document filter
- **Do:** measure, on the real data, exact search versus an HNSW index with the filter (including pgvector's iterative scans if the installed version supports them): latency from `EXPLAIN ANALYZE`, and whether HNSW ever returns fewer than k rows. Write ADR 0002 with the numbers. Default stays exact search unless the data says otherwise.
- **Verify:** ADR contains the query plans and the counts of short results.
- **Refs:** Design §5.1, §12 (ADR 2).

#### 2.9 [ ] Retrieval metrics
- **Do:** `harness/metrics/retrieval.py`: span-overlap function, Hit@k, Recall@k, MRR@k, character precision/recall at a token budget B. Overlap threshold comes from `eval-spec.md` and is a parameter, so the sensitivity analysis is possible. Pure functions.
- **Verify:** write the hand-computed fixtures first. Cover: no gold spans (undefined, excluded, not zero), duplicate chunks, overlapping gold spans, a gold span split across two chunks, ties.
- **Refs:** Design §8.2; skill EVAL-CRITICAL-2.

#### 2.10 [ ] Minimal `ragcalibrate run` for S2 and the baseline number
- **Do:** harness HTTP adapter plus a minimal run command: dev queries, answerable only, S2, C1. Writes a JSON result (the SQLite run store replaces this in Phase 3). Report recall@k for several k, not only 5 (see F-004), plus MRR.
- **Verify:** one command reproduces the numbers twice. Record the values in `docs/results.md` as provisional (dev, not final).
- **Refs:** Design §8.2; finding F-004.

#### 2.11 [ ] Write `references/eval/eval-integrity-rules.md`
- **Do:** short checklist for leakage, ground truth, metric definitions, manifests, abstention, drawn from Design §5 and the skill's inline EVAL rules.
- **Verify:** file exists and SKILL.md's map is updated.
