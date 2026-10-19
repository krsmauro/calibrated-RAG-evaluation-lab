# Eval Integrity Rules

Read this first when touching `harness/`, `corpora/`, `evalsets/`, `configs/`, `report/` or any metric. A bug here doesn't crash; it produces a plausible wrong number. Source of truth: `docs/project-plan.md` §5 and §8 (if this file and the plan disagree, ask).

## EVAL-CRITICAL-1 — Gold labels never reach the system under test

- Queries and gold spans live in `evalsets/` as versioned, hashed files. The Postgres corpus holds `documents` and `chunks` only.
- `service/` must not import `harness/`, read `evalsets/`, or accept fields like `gold`, `answerable`, `category`-as-label, `expected` in any request.
- The harness reaches the SUT only through the adapter interface (HTTP by default), so a different RAG service can be plugged in.
- Review test: grep the service package and DB schema for gold/answerable fields; there must be none.

## EVAL-CRITICAL-2 — Relevance is span overlap in one coordinate system

- Chunks and gold spans share **character offsets into the raw document text**, half-open `[start, end)`.
- Any normalization (whitespace collapse, header stripping, de-hyphenation) shifts offsets: chunk the raw text, or keep an explicit offset map. Never "clean" text and reuse old offsets.
- Property tests: `doc.text[chunk.start:chunk.end] == chunk.text` for every chunk; every gold span's text matches its label.
- State the overlap rule (any overlap vs ≥ 50% of the gold span), report which, and make it configurable and recorded in the manifest. Don't change it silently.

## EVAL-CRITICAL-3 — Don't let chunk size inflate recall

`recall@k` rewards big chunks (five 2,000-token chunks cover more than five 200-token chunks). Comparing **chunkers** requires recall at a fixed retrieved-token budget plus character-level precision/recall. `recall@k` / MRR are fine for comparing **strategies over the same chunks**. Vary one thing at a time: hold the chunker fixed when comparing strategies and vice versa.

## EVAL-CRITICAL-4 — Unanswerable queries are part of the task

- Retrieval metrics are computed on **answerable** queries only (recall is undefined with no gold span). Return a defined "not applicable" (not `0.0`, not `nan` that poisons a mean) and exclude it explicitly; report `n`.
- Answer quality includes abstention. Report abstention **precision and recall separately** so "always abstain" and "never abstain" both score badly on one of them.
- Retrieval is **within-document** (`doc_id` filter) for CUAD/QASPER; don't evaluate corpus-wide unless the corpus supports it (plan §5.1).

## EVAL-CRITICAL-5 — Tune on dev, report on test, once

Chunk size, RRF parameters, rerank depth, prompts: tuned on **dev only**. Test numbers are produced once per final configuration. The CI subset is a fixed, stratified sample of dev contracts, with a size justified by the power study. Code that lets a config read the test split during tuning is a bug; make the split an explicit, recorded field and guard it.

## EVAL-HIGH-1 — Metric definitions are executable specs

- Each metric (Hit@k, Recall@k, MRR@k, char precision/recall at budget B, abstention P/R, citation P/R) has: a docstring with the formula, a known-answer test with hand-computed fixtures, and edge cases: no gold span, duplicate chunks, overlapping gold spans, a gold span split across two chunks, `k` > number of results.
- Averages are per query, then over queries. Say so; don't micro-average by accident.
- Changing a metric's definition = new metric name/version. Old runs are not comparable; don't rescore them silently.

## EVAL-HIGH-2 — Run manifest: every number is regenerable

Recorded for every run: git SHA + dirty flag, config hash, evalset hash, chunker ID, strategy, model IDs (dated snapshots, never moving aliases like `latest`), prompt hashes, `uv.lock` hash, RNG seeds, cache mode, hardware for latency numbers, attempted/failed counts. Store it with the run (`manifest_json`). A dirty tree is flagged in the report, and a gate on a dirty tree is refused or marked.

## EVAL-HIGH-3 — Results are append-only and comparable

Never edit a stored run. Corrections are new runs. `compare` refuses to pair runs with mismatched evalset hash or split unless explicitly forced, and prints why. Pairing is by `query_id`; queries missing from either run are reported, not dropped silently.

## EVAL-HIGH-4 — Report honestly

- Every reported statistic carries `n` and a CI (or says why not).
- Every κ says its **label source**: derived (partly circular), perturbation, or blind human (the headline).
- Name things accurately: "Postgres FTS", never "BM25".
- Show negative and inconclusive results. A gate that shows only passes is not credible.
- Numbers in README/reports come from one regenerating command, not hand-copied.

## EVAL-MEDIUM-1 — Idempotent, resumable runs

Runs can be resumed: finished `(run_id, query_id)` pairs are skipped; a query's rows are written atomically. A crashed run is marked incomplete and cannot be used for a gate decision until finished or explicitly accepted with its denominator stated.
