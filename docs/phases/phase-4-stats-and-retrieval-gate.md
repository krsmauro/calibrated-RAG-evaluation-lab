# Phase 4: Paired cluster bootstrap and the retrieval-only gate (Design Week 4)

**Goal:** the headline feature in a cheap, deterministic form. After this phase a credible project exists even if later phases slip.
**Entry:** Phase 3 done (stored runs for S1 to S4).
**Exit criterion:** bootstrap coverage test passes; the clustered false-alarm rate is close to nominal.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 4.1 [ ] Paired cluster bootstrap
- **Do:** `stats/bootstrap.py`, pure functions, seeded RNG, no I/O. Input: per-query metric values for candidate and baseline, joined on `query_id`, with a cluster label (`document_id`). Resample clusters, take all queries of each sampled cluster, compute the mean paired difference. Percentile CI, 10,000 resamples by default. Seed is returned with the result. Use numpy (already needed); no new dependency.
- **Verify:** known-answer tests on tiny hand-computed inputs (for example two clusters, where the bootstrap distribution is enumerable); same seed gives the same CI; unpaired or mismatched query sets raise.
- **Refs:** Design §8.5; skill EVAL-CRITICAL-3.

#### 4.2 [ ] Coverage test on synthetic data
- **Do:** simulate data with a known true delta and within-cluster correlation. Check that about 95 percent of 95 percent intervals contain the truth for the cluster bootstrap, and show that the query-level bootstrap under-covers when clusters are correlated. Run it for several cluster counts, **including small ones** (about 20 to 40 contracts), because percentile bootstraps can under-cover with few clusters.
- **Verify:** test asserts coverage within a tolerance band computed from the number of simulations; the small-cluster result is recorded in a finding. If coverage is poor at the planned CI-subset size, record it and escalate (options: larger subset, BCa intervals, a t-based interval). Do not proceed on a silent shortfall.
- **Refs:** Design §8.5; finding F-003.

#### 4.3 [ ] Gate decision function
- **Do:** `stats/gate.py`: given `[lo, hi]` and δ, return Pass, Fail or Inconclusive per the rule in Design §8.5, including the "small regression detected" note. Holm-Bonferroni helper only if more than one metric gates (default: one primary metric).
- **Verify:** property tests on every boundary (`lo == -δ`, `hi == 0`); exhaustive table test of the three outcomes.
- **Refs:** Design §8.5.

#### 4.4 [ ] `ragcalibrate compare` and the first report
- **Do:** compare two stored runs, output a Markdown table (metric, baseline, candidate, delta, CI, outcome, n queries, n documents) and an HTML report. Secondary metrics are shown but never gate.
- **Verify:** the strategy comparison table on dev for S1 to S4 regenerates from one command. Every number shows its n.
- **Refs:** Design §8.5, §14.

#### 4.5 [ ] Fixed CI subset
- **Do:** a fixed, stratified sample of dev contracts, written to a hashed file in `evalsets/`. Size is **provisional** until 4.6 produces the power curve; make it easy to regenerate at another size.
- **Verify:** reproducible from a seed; no overlap with test.
- **Refs:** Design §8.1.

#### 4.6 [ ] Subsampling study: false alarms, power, MDE
- **Do:** treat all of dev as the population, run each configuration once on all of dev, then draw 1,000 random CI-sized subsets of contracts and apply the gate to each using only stored results.
  1. False-alarm rate for two configurations with about zero full-dev delta, with query-level and cluster-level resampling side by side.
  2. Power: seed regressions of known size (for example drop the relevant chunks from the top k on a random p percent of queries) and plot the share of subsets that Fail against the size. Read off the minimum detectable effect.
  3. Use the power curve to set the CI-subset size and δ. The size comes from this, not from a guess.
- **Verify:** script plus output committed (or regenerable by one command); numbers in `docs/results.md`; a finding states the chosen subset size and δ with the evidence. Watch for ceiling effects (F-004): if recall@5 is near 1.0, power on it will be poor and another primary metric or k may be needed.
- **Refs:** Design §8.5; findings F-003, F-004.

#### 4.7 [ ] Retrieval-only GitHub Action
- **Do:** composite action in `action/`: bring up the stack, run the CI subset for candidate and baseline, compare, post or update one sticky PR comment, set the exit code (fail on Fail; neutral on Inconclusive). Baseline for retrieval is recomputed at the merge base in the same job. Least-privilege permissions; no secrets needed for this stage; never `pull_request_target`.
- **Verify:** runs end to end on a test PR (the user pushes; mark `[!]` blocked-on-user until confirmed); the comment updates rather than duplicating.
- **Refs:** Design §8.5 (baseline management, fork PRs, PR comment), §12 (ADR 10).

#### 4.8 [ ] Freeze retrieval configs and run CUAD test once (needs user go-ahead)
- **Do:** only when the user says the retrieval configs are final: freeze them (config hashes in the plan), run the test split once per final config, record in `docs/results.md`. Never tune after seeing test numbers.
- **Verify:** `docs/results.md` rows reference run IDs; a finding records which configs were frozen and when.
- **Refs:** Design §8.1.

#### 4.9 [ ] ADRs and skill reference
- **Do:** ADR 0004 (span-overlap relevance and token-budget metrics), 0007 (paired clustered bootstrap and the three-outcome gate), 0010 (baseline management). Write `references/eval/stats-rules.md`.
- **Verify:** ADR index in the plan updated; the reference file exists.

#### 4.10 [ ] Embedding-model comparison: bge-small-en-v1.5 vs a hosted model (added 2026-10-28 at the user's request)
- **Why:** the user wants a benchmark that answers "does the popular hosted embedding model beat the free local one on legal contracts, and by how much?", measured with this project's own machinery (paired, document-clustered CIs). It is also a candidate for a Phase 8 demo PR ("swap the embedding model, let the gate decide").
- **Entry:** 2.6 (embeddings stored per embedder id), 2.7 (`/retrieve` can select the embedder), 2.10 (S2 baseline), 3.5 and 3.6 (run store and manifest), 4.1 and 4.4 (`compare`). Decision D6 answered: model confirmed, API key in `.env`, spend cap set by the user in the provider's dashboard. Not part of the Phase 4 exit criterion. It is new scope, so it is the first thing to cut if time runs short (not on the never-cut list).
- **Do:**
  1. Candidate: OpenAI `text-embedding-3-small` (proposed, confirm with D6). Before writing code, read the provider's current docs and record in ADR 0012: price per million tokens (about $0.02 at Claude's last knowledge; verify), output dimension (1536 by default; keep the default, so the comparison is the model as people use it), maximum input tokens, per-request batch limits, and whether a dated snapshot exists. If none exists, the stored vectors are the reproducible artifact and the embedding date goes into the embedder id.
  2. Change one thing only: the embedder. Keep the same C1 chunks (`c1v1:bge-small-en-v1.5@5c38ec7c405e:size=256:overlap=32`; do not re-chunk with the other model's tokenizer), the same dev queries (answerable only for retrieval metrics), the same k values and metrics, and the same retrieval path (exact cosine search under the per-document filter).
  3. A thin hosted-embedding client: `httpx` (add the official SDK only if justified, DEP-CRITICAL-1/2); key from `Settings` as `SecretStr` (add it to `config.py` and to `.env.example` with an empty value), never logged; explicit timeout; bounded concurrency; retry with backoff on 429 and 5xx only; batched requests. If Phase 5's `llm/` client exists by then, reuse it instead.
  4. Ingest: embed all C1 chunks once into the embeddings table under their own `embedder_id` (for example `openai:text-embedding-3-small:d1536:YYYY-MM-DD`). Idempotent and resumable: chunks already embedded for that id are skipped, so a crash or a rate limit never pays twice. Count tokens with the provider's tokenizer before calling and record tokens billed and cost. Expected size: 24,872 chunks, roughly 6M tokens (the 510 contracts total 5,529,156 bge tokens before overlap, measured in step 2.4; other tokenizers differ).
  5. Queries: CUAD has only 41 distinct question strings. The service embeds query text through a content-addressed cache keyed by `(embedder_id, sha256(text))`, so reruns make no API calls. The hosted strategy runs locally only; CI stays free and keyless (Design §7). The run manifest records the embedder id and the cache mode.
  6. Determinism: embed the 41 questions twice with the cache bypassed; report the maximum absolute difference and whether any top-10 ranking changes. Hosted embeddings are not guaranteed to be bitwise stable.
  7. Run S2 once per embedder on dev, store both runs, and `ragcalibrate compare` them: the primary metric from `docs/eval-spec.md` (fixed in 4.6), plus recall@{1,3,5,10}, MRR@10, character precision/recall at B, a per-category breakdown (F-008: four easy categories dominate the answerable pairs), n queries and n documents. Also report latency per query (local bge: 4.4 ms on an Apple M5, step 2.5) and the one-off cost.
  8. Dev only (EVAL-CRITICAL-5). A test-split number for the hosted model exists only if it is among the configs frozen in 4.8.
- **Verify:** both runs regenerate from one command each, and the hosted rerun makes no API calls (stored vectors plus the query cache); the comparison table shows deltas with 95% CIs and n; a provisional row in `docs/results.md`; a finding states the outcome as measured, including "no detectable difference" if that is what the CI says; ADR 0012 written; the key does not appear in any log (grep a run's log for it).
- **Refs:** ADR 0011 (Consequences), Design §7, §8.5; skill DEP-HIGH-1 (pin model ids), SEC and reliability rules, EVAL-CRITICAL-3 and -5, EVAL-HIGH-2.
