# Phase 5: Cited answers, LLM client, cache, cost, tracing (Design Week 5)

**Goal:** the service answers with citations and can abstain; every LLM call is cached, costed and traceable; deterministic answer metrics exist.
**Entry:** Phase 4 done; D1 (provider and budget) answered; 0.5 done.
**Exit criterion:** cost per run is reported; a warm-cache rerun costs about $0.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

Constraints from `docs/llm-production-best-practices.md` that apply here (the rest of that document targets a different kind of system; see F-006): pin dated model snapshots; retry at exactly one layer; check the stop reason on every response; validate output structure and repair once then fall back; never hold a DB connection during an LLM call; stamp prompt version and model on every record.

---

#### 5.1 [ ] LLM client
- **Do:** `llm/client.py`, one thin provider interface used by both generator and judge. No framework. Explicit timeout on every call. Turn off the provider SDK's own retries and keep a single retry layer: exponential backoff with jitter, honor `Retry-After`, no retry on non-retryable errors (invalid request, context too long). Check the stop reason; a truncated answer is an error, not a result. Capture input and output token counts. Models are dated snapshots, never moving aliases.
- **Verify:** unit tests with recorded fixtures (no network): 429 with `Retry-After`, 5xx, truncated output, timeout. Grep shows no second retry layer.
- **Refs:** Design §8.6, §9; skill BE-CRITICAL-2, reliability rules.

#### 5.2 [ ] Content-addressed cache
- **Do:** separate SQLite file. Key = hash of provider, model snapshot, prompt template hash, rendered input, parameters. Three modes: `read-write`, `read-only`, `off`. Decide whether a write-only mode is needed for A/A runs (skill mentions it) and document why.
- **Verify:** tests prove each key component changes the key; `off` never reads; `read-only` never writes. Document the A/A requirement in a code comment next to the mode switch.
- **Refs:** Design §5.7, §8.6, §12 (ADR 8); skill EVAL-CRITICAL-5.

#### 5.3 [ ] Cost accounting and `--max-cost`
- **Do:** versioned price file with a date; cost computed from recorded tokens. `--max-cost` estimates spend before a run (from prompt sizes and expected output cap) and aborts above the limit. Report cost per run and per query.
- **Verify:** unit test for cost arithmetic against a hand-computed example; a run with a tiny limit aborts before the first paid call.
- **Refs:** Design §8.6.

#### 5.4 [ ] Generator prompt and structured output
- **Do:** versioned prompt file (hash recorded). Output validated by Pydantic: `{present: bool, answer: str, citations: [chunk_id]}`. Citations must be a subset of the retrieved chunk ids; anything else is a validation failure. On failure: one repair attempt with the error sent back, then a defined fallback. Count each path (valid, repaired, fallback). Set the output cap deliberately.
- **Verify:** tests for each path; the counts appear in the run report.
- **Refs:** Design §8.3; best-practices "Handling model output".

#### 5.5 [ ] `/answer` endpoint
- **Do:** `POST /answer {query, doc_id, strategy, chunker_id}` returns answer, citations (chunk ids plus offsets), `abstained`, token usage. Retrieve first, release the DB connection, then call the LLM. Wire models in the shared module.
- **Verify:** test shows no pool connection is checked out during the LLM call (for example, pool size 1 plus a slow fake LLM, concurrent requests still progress). OpenAPI matches.
- **Refs:** Design §6; best-practices "Database connections"; skill XC-CRITICAL-3.

#### 5.6 [ ] Deterministic answer metrics
- **Do:** presence accuracy, abstention precision and recall (reported separately), citation precision (cited chunks overlapping gold / cited chunks), citation recall. Pure functions, hand-computed fixtures, with the edge cases: no citations, abstained with citations, no gold.
- **Verify:** fixtures pass; a degenerate system that always abstains and one that never abstains each score badly on exactly one abstention metric (test it).
- **Refs:** Design §5.4, §8.3.

#### 5.7 [ ] Optional Langfuse tracing
- **Do:** one trace per query with spans for retrieve, rerank, generate, judge. Off by default; enabled by environment variable or a Compose profile. First check Langfuse's current self-host requirements, since they change.
- **Verify:** run with tracing off (no Langfuse reachable) and on; both work. `run_id` and `query_id` appear in logs and spans. No prompts containing contract text at INFO level.
- **Refs:** Design §8.6; skill BE-CRITICAL-5.

#### 5.8 [ ] Run answers on dev; report cost
- **Do:** run the chosen retrieval config with generation on dev, cold cache, then again warm. Record the manifest including model snapshots and prompt hashes.
- **Verify:** warm rerun costs about $0 and returns identical answers; cold cost per run and per query are in `docs/results.md`. Fill the budget targets left blank in Design §8.6 and record them in a finding.
- **Refs:** Design §8.6, §11.

#### 5.9 [ ] Write the remaining skill references
- **Do:** `references/eval/llm-rules.md`, and `references/python/{reliability,async-error,observability,security}-rules.md`, short and derived from what was actually built.
- **Verify:** files exist; SKILL.md map updated.
