# Evaluation spec: what the numbers mean

> **Status: APPROVED by the user on 2026-10-19** (plan step 1.8). Written by Claude; the user read it and approved it, including the generator-metric change in section 6.1. Sections marked provisional are still open by design, each with the step that finalizes it.
>
> **Scope:** the single source of truth for metric definitions, relevance, splits, the gate and the judge's criteria. Rationale lives in `docs/design/project-design.md` ("Design §N"); this file records the decisions. If code and this file disagree, one of them is a bug, and the fix is a dated amendment here, never a silent change in code.
>
> **Pre-registration rule.** Anything marked **fixed** is decided before any test-split number exists. Anything marked **provisional** has a named step that finalizes it, and the finalizing procedure is stated here so the outcome cannot be chosen after seeing which option favors a preferred strategy. Amendments after the test split has been touched are listed in the amendment log at the bottom, with the reason.

## 1. Primary task

**Fixed.** Retrieval is **within-document**. Every query carries a `doc_id`; the service filters candidates to that document's chunks. CUAD and QASPER are both of this shape (Design §5.1). Corpus-wide retrieval is out of scope.

A query is one `(document, category)` pair for CUAD (templated question) or one `(paper, question)` pair for QASPER. Query IDs are stable and derived from the source dataset's own identifiers.

## 2. Coordinates and relevance

**Fixed.**

- Gold spans and chunks share one coordinate system: half-open character offsets `[start, end)` into the **raw, un-normalized** document text as shipped by the dataset (Design §5.3). Invariants, enforced by property tests: `text[chunk.start:chunk.end] == chunk.text` for every chunk; `text[span.start:span.end] == span.text` for every gold span.
- **Overlap** of a chunk and a gold span in the same document is `max(0, min(c.end, s.end) - max(c.start, s.start))` characters.
- **Primary relevance rule (R1): a chunk is relevant if it overlaps at least one gold span by at least one character.** Reason: it is the rule behind Hit@k as defined in Design §8.2, it is parameter-free, and it cannot make a long gold span unreachable.
- Known weakness of R1: a chunk that touches a long span by one character counts as a full hit, and big chunks hit more often. That is why chunk comparisons use the token-budget metrics (§3.4) and not recall@k alone.
- **Sensitivity rule (R2), always reported next to R1 for the strategy comparison: a chunk is relevant if its overlap is at least `min(0.5 × span length, 0.5 × chunk length)`.** The `min` is deliberate: a plain "50% of the gold span" rule makes spans longer than two chunks unreachable by any single chunk. The sensitivity report states whether the ranking of strategies under R2 matches R1. R1 stays primary regardless of the outcome, and the gate uses R1 only.
- Whitespace-only overlaps are counted as overlaps. Step 1.7 measured that no CUAD gold span has leading or trailing whitespace (0 of 13,823, finding F-008), so an overlap at a span's edge always includes a non-whitespace character. No amendment needed.

## 3. Retrieval metrics

**Fixed definitions.** Notation: for a query, `G` is its list of gold spans (after merging spans that overlap each other, so a span is never counted twice), and `top_k` is the first k distinct chunk IDs of the ranked list returned for that query.

### 3.1 Which queries count

- Retrieval metrics are computed on **answerable queries only** (`G` non-empty). Unanswerable queries are excluded from every retrieval average, not scored as zero or one (Design §5.4).
- Every reported retrieval number carries its `n` (queries) and its number of clusters (documents).

### 3.2 Definitions and edge cases

| Metric | Definition | Edge cases |
| --- | --- | --- |
| Hit@k | 1 if any chunk in `top_k` is relevant, else 0 | Empty result list gives 0 |
| Recall@k | `#(spans in G overlapped by at least one relevant chunk in top_k) / #G` | Empty result list gives 0. A span split across two chunks counts once if either chunk is relevant. `G` empty: query excluded (§3.1) |
| MRR@k | `1 / rank` of the first relevant chunk in the list, or 0 if none within k | Rank is 1-based |
| nDCG@k | Optional. Binary gain from R1; not gated | Defined only if a step needs it |

- **Fewer than k results:** use what was returned, never pad. The count of queries with fewer than k results is reported as a diagnostic, because an approximate index under a filter can silently return fewer (Design §5.1).
- **Duplicate chunk IDs in a result list:** only the first occurrence counts and takes its rank; later duplicates are dropped and counted in a diagnostic.
- **Per-query values first, then the mean over queries.** The gate consumes the per-query values (paired by `query_id`), never only the means.

### 3.3 Citation metrics (deterministic, no judge)

Computed from the generator's `{present, answer, citations}` output, with citations resolved to chunk offsets.

- **Citation precision:** `#(cited chunks that are relevant under R1) / #cited chunks`. Defined only for queries where the answer has at least one citation; reported with its own `n`.
- **Citation recall:** `#(spans in G overlapped by a cited relevant chunk) / #G`, on answerable queries; an abstention on an answerable query scores 0.
- On an unanswerable query, any citation at all is recorded as a diagnostic (`citations_on_unanswerable`), not folded into the two metrics above.

### 3.4 Token-budget and character metrics (for comparing chunkers)

recall@k rewards large chunks (Design §5.2), so chunker comparisons use these, not recall@k.

- Concatenate the ranked chunks in order until a budget of **B tokens** is reached; the chunk that crosses the budget is cut at the token boundary. Let `Ret` be the set of document characters in that prefix (a character covered by two overlapping chunks counts once) and `Gold` the set of characters in the merged gold spans.
- **Character precision@B** = `|Ret ∩ Gold| / |Ret|`. If `Ret` is empty the value is 0 (returning nothing is a failure, not an undefined case).
- **Character recall@B** = `|Ret ∩ Gold| / |Gold|`. `Gold` empty: query excluded.
- **Tokenizer: provisional.** It must be one fixed, version-pinned, provider-neutral tokenizer applied identically to every strategy and chunker (not any embedding model's own). The choice and the exact library are made in step 4.9 (ADR 0004). Until then B is stated in that tokenizer's tokens in every config.

## 4. Unanswerable queries, answer metrics and abstention

**Fixed.**

- A CUAD query is **unanswerable** if its (document, category) pair has no gold span. This is a statement about the labels, not about the contract: an annotator may have missed a clause. That label-noise risk is stated in the README's threats to validity, and step 1.7 measures the unanswerable share.
- The generator returns `{present: bool, answer: str, citations: [chunk_id]}`, validated at parse time (Design §8.3).
- **Presence accuracy** over all queries: `present == answerable`.
- **Abstention** treats "abstain" (`present=false`) as the positive class.
  - Abstention precision = `#(abstained and unanswerable) / #abstained`.
  - Abstention recall = `#(abstained and unanswerable) / #unanswerable`.
  - A zero denominator makes the metric undefined and the report prints "n/a", never 0 or 1. A system that always abstains has recall 1 and a precision equal to the unanswerable share; a system that never abstains has recall 0 and undefined precision. Both are visible in the report.
- Retrieval itself is not asked to abstain: the retriever always returns k chunks.

## 5. Judge criteria

**Fixed, resolving finding F-001.** The judge grades **two** criteria, each a binary pass or fail with a short rationale (Design §5.6, §8.3):

1. **Faithfulness:** every claim in the answer is supported by the **cited chunks' text**. The judge sees the question, the answer and the cited chunks only. It does not see the gold span.
2. **Correctness:** the answer matches the content of the gold clause. The judge additionally sees the gold span text. (The judge is part of the instrument, not the system under test, so this is not leakage.)

"Citation support" is **not** a third judged criterion. Two parts of it already exist:

- Whether a cited chunk overlaps the gold span is the deterministic check in §3.3.
- Whether a cited chunk semantically supports the claim is covered by faithfulness, because faithfulness is judged against the cited text only. The citation-trust bias test (swap the citations, keep the answer text) probes exactly this and must make faithfulness fail.

**When the judge runs.**

- Faithfulness: every answer with `present=true`.
- Correctness: `present=true` on an answerable query. All other cases are deterministic: abstaining on an unanswerable query is correct; abstaining on an answerable query and `present=true` on an unanswerable query are incorrect.

**Label sources and the claim they support.** Every κ in a report states its source: derived, perturbation or human (Design §5.5). Only κ against blind human labels is a headline number. The labeler is a single person (the author); this is stated as a threat to validity (finding F-005). Labels are keyed by a hash of the frozen answer text and its context, never by `(run_id, query_id)`.

The detailed rubric is `docs/judge-rubric.md` (step 6.1). Sample sizes, the κ protocol and the bias tests follow Design §8.4 and are deferred to Phases 6 and 7.

## 6. Primary metrics, δ and the gate

### 6.1 One primary metric per kind of change

Only the primary metric gates. Everything else is reported as secondary, non-gating information (Design §8.5).

**Retrieval changes (fixed rule, provisional outcome).**

- Candidates in this fixed order: **recall@5, recall@3, MRR@5, character recall@B (B = 512 tokens)**.
- The primary metric is the **first candidate whose best dev mean across S1 to S4 (chunker fixed, Design §7) is below 0.95**. The check runs once, on **dev only**, in step 2.10 and again in 3.9 when S1 to S4 all exist. It never looks at which strategy wins and never at test.
- Default if nothing saturates: recall@5.
- If every candidate is saturated, that is itself a finding: the corpus-and-task combination cannot separate the strategies, and the spec is amended with a harder variant before any claim is made.

**Generator or prompt changes (decided: deviates from Design §8.5; approved 2026-10-19).**

- Design §8.5 names the judge faithfulness pass rate. Taken alone, that metric can be gamed: a prompt that abstains more often removes unfaithful answers from the denominator and looks better.
- Decision: the primary metric is the **end-to-end correct rate** over all queries. A query is correct when the system abstains on an unanswerable query, or says present on an answerable query and is judged correct. This cannot be improved by always abstaining (answerable queries all fail) or by always answering (unanswerable queries all fail).
- Faithfulness pass rate, over answers with `present=true`, is then a **guard metric**: two metrics gate together, so Holm-Bonferroni applies (Design §8.5), and each gate decision is made at the corrected level.
- The design's version (faithfulness alone as primary) was rejected for the gaming reason above. The deviation from Design §8.5 is recorded in the plan change log and in ADR 0007 (step 4.9).

### 6.2 Comparison

**Fixed.** Candidate and baseline run on the same queries. For each query compute `candidate − baseline` of the primary metric. Resample **documents** (all queries of each sampled document go together), 10,000 resamples, percentile 95% interval, seed recorded in the report and the manifest. BCa is allowed only if the coverage study (step 4.2) shows percentile intervals under-cover (finding F-003).

A comparison that has fewer than the **minimum cluster count** is reported `Inconclusive` without computing an interval. The minimum is **provisional**: set from the coverage simulation in step 4.2 across cluster counts of about 20 to 40 up to full dev.

### 6.3 δ, the smallest regression worth blocking

- Retrieval primary metric: **δ = 0.02** (2 points), **provisional**. Rationale: on the order of two more missed relevant clauses per hundred queries, small enough to matter to a contract-review user and the figure used in Design §8.5.
- Generator primary metric: **δ = 0.05**, **provisional**, to be revisited after the A/A study measures run-to-run noise (step 8.x).
- **Finalizing rule.** δ is chosen first on the merits above. The power study (step 4.6) then reports the minimum detectable effect (MDE) of the CI subset. If MDE > δ, the response is to enlarge the CI subset (cheap for retrieval), and only then to raise δ, with the reason recorded here. δ is never lowered to look good after seeing results.

### 6.4 Gate rule

**Fixed.** Let `[lo, hi]` be the 95% interval of candidate minus baseline for the primary metric (with Holm correction applied to the level when two metrics gate).

| Outcome | Condition | Meaning |
| --- | --- | --- |
| Pass | `lo ≥ −δ` | Any regression is smaller than δ. If `hi < 0` also, add the note "small regression detected" |
| Fail | `hi < 0` and `lo < −δ` | Confidently worse, and a regression of at least δ cannot be ruled out |
| Inconclusive | `lo < −δ` and `hi ≥ 0` | The subset is too small to tell; neutral status, suggest a full dev run |

The three rows cover every case: either `lo ≥ −δ`, or `lo < −δ` and then `hi` is either below zero or not.

Observation to check in step 4.6: Fail does not require the true regression to be as large as δ, only that δ cannot be ruled out. A tiny real regression measured on a small subset can Fail. That is by design, but the false-fail and "failed on a regression below δ" rates are both reported separately.

Gate validation (subsampling study, A/A study, coverage test) follows Design §8.5. The false-alarm study is run with both query-level and document-level resampling, and only the document-level result is the gate.

## 7. Splits

**Fixed** unless noted.

- **Unit of splitting is the document.** A document's queries never straddle two splits.
- **Test:** the dataset's official test split (Design §8.1 expects 102 CUAD contracts and 4,182 rows; step 1.7 confirms). Touched once per frozen configuration. Every touch is logged in `docs/results.md` with the config hash and run id. A new config hash is a new touch and is listed as such; reruns of the same hash (cache read-only) are not new touches.
- **Dev:** every CUAD document in the official train split (measured in step 1.7: 408 contracts, 16,728 pairs, 5,458 answerable; test is 102 contracts, 4,182 pairs, 1,244 answerable; finding F-008). The unit is the (contract, category) pair from `CUADv1.json`; `train_separate_questions.json` has a different unit (one row per answer span) and is not used. Reason: nothing in this project is trained (fine-tuning is a non-goal), so no data needs to be held back for training. Tuning of chunk size, RRF parameters, rerank depth and prompts happens on dev only.
- **CI subset:** a fixed sample of dev documents, stratified by document length (terciles by characters). Its size is **provisional**: set from the coverage and power studies (steps 4.2 and 4.6), not from a runtime budget alone. The sampling seed and the document list are committed with the eval set.
- **Judge development vs calibration (provisional):** documents used to write and revise the judge rubric and prompt are disjoint from documents whose answers go into the human-labeled calibration set. The judge prompt is frozen (version and hash) before any calibration label is made. The sizes are fixed in step 6.1.
- QASPER follows the same rules with its own official splits; the mapping is written in Phase 9.
- A paraphrased-query ablation (Design §10) uses dev; it is not part of the gate.

## 8. Values of k and the token budget

**Provisional list, fixed rule.**

- Always computed and reported in the same run: recall@k and Hit@k for **k ∈ {1, 3, 5, 10}**, MRR@10, and character precision and recall at **B ∈ {256, 512, 1024, 2048} tokens**. They cost nothing extra, and reporting several k values shows saturation instead of hiding it.
- Which one gates is decided only by the rule in §6.1 (finding F-004). The values are chosen for headroom on dev, never because a favored strategy wins on them.
- Note on F-004: a saturated metric hurts the strategy comparison (ties) and improvement detection most. It hurts regression gating less than finding F-004 suggests, since a ceiling does not stop a regression from dropping below it. Step 4.6 measures this; until then it is a hypothesis, not a fact.

## 9. Reproducibility requirements that the metrics depend on

**Fixed.** Every run records the manifest in Design §8.6: git SHA and dirty flag, config hash, eval-set hash, chunker ID, dated model snapshots, prompt hashes, `uv.lock` hash, RNG seeds. The eval-set hash covers the queries, the gold spans, the split assignment and the CI-subset list. Changing any of them is a new eval set version. Results are append-only. A figure in a report or the README comes from one command and is logged in `docs/results.md`.

## 10. Coverage of Design §5 and §8

| Design section | Where it is settled |
| --- | --- |
| §5.1 Per-document retrieval | §1 |
| §5.2 Span overlap, fixed token budget | §2, §3.4 |
| §5.3 Offsets survive normalization | §2 (invariants; property tests in Phase 2) |
| §5.4 Unanswerable queries | §3.1, §4 |
| §5.5 Label sources | §5 (sizes deferred to step 6.1) |
| §5.6 Binary verdicts per criterion | §5 |
| §5.7 Two sources of noise, cache | Deferred to steps 4.6 (subsampling) and 8.x (A/A with cache off); manifest in §9 |
| §5.8 Two databases | Not a metric question; ADR 0003 (step 1.9) |
| §5.9 FTS is not BM25 | Not a metric question; ADR 0009 (step 1.9) |
| §5.10 Gold labels never reach the SUT | Not a metric question; ADR 0005 (step 1.9) |
| §8.1 Splits | §7 |
| §8.2 Retrieval metrics | §3 |
| §8.3 Answers and answer metrics | §3.3, §4, §5 |
| §8.4 Judge calibration protocol | Deferred to steps 6.x and 7.x (rubric, κ protocol, bias tests, mitigations, PPI) |
| §8.5 The CI gate | §6; validation studies deferred to steps 4.2, 4.6 and 8.x; baseline management to ADR 0010 |
| §8.6 Reproducibility, cost, latency | §9 for the manifest; cost, latency and cache modes deferred to steps 3.x, 5.x and 8.x |

## Decisions for the user

Resolved on 2026-10-19 by approval of the whole spec:

1. Generator primary metric: end-to-end correct rate, with faithfulness as a Holm-corrected guard (§6.1).
2. Relevance rule: R1 (one character of overlap) primary, R2 as sensitivity (§2).
3. Dev is all of the train split (§7).
4. Fallback order for the retrieval primary metric and the 0.95 saturation threshold (§6.1).
5. Starting δ values 0.02 and 0.05, provisional (§6.3).

Still open, no answer needed yet:

6. **Single labeler.** Can even 50 calibration items be labeled by a second person (finding F-005)? It would allow inter-rater κ. Decide before Phase 6.

## Amendment log

- 2026-10-19: draft written (Claude). No test-split number exists yet.
- 2026-10-19: approved by the user. Generator primary metric changed from the design's faithfulness pass rate to the end-to-end correct rate with a faithfulness guard (§6.1). Still no test-split number.
- 2026-10-19: step 1.7 measurements added to §2 and §7 as facts (F-008). No decision changed. Noted in F-008: 67.9% of CUAD pairs are unanswerable, so the always-abstain baseline for presence accuracy is about 68% and must be reported beside it.
