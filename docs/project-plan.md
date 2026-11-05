# Calibrated RAG Evaluation Lab: project plan (index)

> **Every agent starts here.** This file is an index and a status board, not the design. Read it, then open only the file your current step points to.

## What this project is

An open-source harness that answers: did this change make a RAG system better, by how much, and can I trust the judge that says so? It measures retrieval against span-level gold labels, calibrates its LLM judge against blind human labels (κ with CIs), and gates PRs on a paired, document-clustered bootstrap with a measured false-alarm rate and power. The system under test is a small hybrid-retrieval RAG service (FastAPI, Postgres with pgvector and FTS, a cross-encoder reranker) that the harness reaches only over HTTP. Full statement: `docs/design/project-design.md` §1.

## How to read this plan (progressive disclosure)

1. This file: status board, protocol, decisions, indexes. Always read.
2. The phase file for the step you are on (`docs/phases/`). Read that one only.
3. The Design section or skill reference that the step's **Refs** line names. Do not read the 50KB design end to end.
4. Findings: scan the findings index below; open a finding only if its **Affects** column lists your step.
5. `docs/results.md`, `docs/adr/` and `docs/eval-spec.md` (once it exists) when a step says so.

## Status board

Status values: `todo`, `in progress`, `blocked`, `done`. One short phrase per cell; the detail lives in the phase file.

| Phase | Design week | Status | Next step | File |
| --- | --- | --- | --- | --- |
| 0 Pre-flight | none | done | none (0.5, the API keys, moved to Phase 5 with D1) | [phase-0](phases/phase-0-preflight.md) |
| 1 Eval spec and skeleton | 1 | done 2026-10-19 | none | [phase-1](phases/phase-1-spec-and-skeleton.md) |
| 2 CUAD, C1, dense retrieval, metrics | 2 | done 2026-10-28 | none | [phase-2](phases/phase-2-cuad-ingest-and-dense-retrieval.md) |
| 3 Strategies, C2, run store | 3 | done 2026-11-05 | none | [phase-3](phases/phase-3-strategies-and-run-store.md) |
| 4 Stats and retrieval gate | 4 | in progress (exit criterion met 2026-11-05) | 4.11, then 4.8; 4.7b and 4.10 wait on the user | [phase-4](phases/phase-4-stats-and-retrieval-gate.md) |
| 5 Answers and LLM client | 5 | todo | 5.1, once D1 is answered | [phase-5](phases/phase-5-answers-and-llm-client.md) |
| 6 Judge and labels | 6 | todo | 6.1 | [phase-6](phases/phase-6-judge-and-labels.md) |
| 7 Calibration report | 7 | todo | 7.1 | [phase-7](phases/phase-7-calibration-report.md) |
| 8 Full gate, demo PRs, latency | 8 | todo | 8.1 | [phase-8](phases/phase-8-full-gate-and-demo-prs.md) |
| 9 QASPER and release | 9 | todo | 9.1 | [phase-9](phases/phase-9-qasper-and-release.md) |

Phases run in order. An agent does not start phase N+1 until phase N's exit criterion is checked, unless the user says otherwise. Phase 4 (retrieval-only gate) is the safety net: if time runs short, a credible project exists after it.

## Next

Rewrite this list at the end of every step; never append to it. Ten short lines at most.

- **4.11 (agent, now):** apply D8: store character recall at a word budget in every run, and gate a chunker change on character recall@512. A code step.
- **4.8 (agent, after 4.11 is committed):** go-ahead given 2026-11-05. Run the test split once per frozen config, on a clean commit.
- **4.7b (user):** open any PR to `main`, then push a second commit to it. The gate has never run: the `gate-test` PR was closed before the workflow existed. Checks (a) to (c) under 4.7b.
- **4.10 (user, then agent):** the OpenAI key in `.env` and a spend cap (D6).
- **Phase 5 (user):** D1, the generator's provider and the total budget. The judge is Claude.

What exists and how it fits together: the README (layout and commands) and the code. Per-step detail: the Done notes in `docs/phases/`. Headline numbers: `docs/results.md`.

**Run it:** Docker Desktop running and `uv` installed. `make up`, `make data` (CUAD), `make evalsets`, `make models` (134 MB embedding model and 91 MB cross-encoder), `make ingest` (applies migrations; about 7 minutes the first time), `make ingest CHUNKER=c2` (about 9 minutes), `make ingest SIZE=199` (the size-matched C1 for step 3.9, about 7 minutes), `make serve`, then `uv run ragcalibrate run configs/s2-dense.yaml` (S1 to S4: `configs/s*.yaml`), `make lint`, `make test`, `make test-integration`. `make down` stops Postgres. All downloads land in the gitignored `data/` and are sha256-checked.

**Things that bite:**
- ruff line length is 100 and Markdown is excluded from `ruff format`; `Settings` is built only by `load_settings()`; `scripts/` may print, `src/` may not.
- Tests that need `data/` (CUAD or the model) skip when the files are missing. CI downloads the model but not CUAD.
- S1 returns only chunks that share a word with the query: fewer than k, or none, is a valid answer, not an error. Its text-search configuration lives in two places (migration 0003's generated column and `FTS_CONFIG` in `service/retrieval.py`); an integration test fails if they differ.
- Do not trust numbers copied from the design for CUAD; use F-008 and the 2.4 Done note (median contract 6,739 bge tokens).
- Round a number for `docs/results.md` once, from the exact mean (`summarize` over `RunStore.queries`, or `summary` in a run JSON from before 3.7), not from the CLI's four-decimal printout: S2's recall@5 was rounded twice (0.48846 to 0.4885 to 0.489) and quoted wrongly in nine places until 3.2.
- The contract is strict (`extra="forbid"`) and the harness sends every request field, including `rrf_k: null` and `fusion_depth: null`. A `make serve` started before a change to `contract.py` answers every harness request with 422 `Extra inputs are not permitted`: restart the service after changing the contract.
- S4 costs about 11 ms of CPU per (question, chunk) pair: a dev run at rerank depth 10 takes about 7.5 minutes, and `measure_rerank.py tune` at depth 30 about 26. Run other CPU-heavy work after, not alongside, or the timings are off.
- A test that passes locally can still fail on GitHub's slower runners when it depends on how threads and the event loop interleave (3.7's last note). Check CI (`gh run list`) after a push.
- Test files need unique basenames across `tests/unit`, `tests/property` and `tests/integration` (there is no `__init__.py`); a repeated name fails collection with `import file mismatch`.
- `ragcalibrate run` writes only to the run store; nothing reads the `runs/*.json` files from before step 3.7 any more (their per-query lists still parse as `QueryResult`). A config with C2's chunker id needs `make ingest CHUNKER=c2` first; otherwise the service answers with an error that names the chunker. `--resume` is refused if the config, eval set, commit or dirty flag changed; a crashed run leaves `runs.sqlite-wal` beside the store until the next clean open, so copy the store only after a clean close.
- When planting bugs to check that tests catch them, set `PYTHONDONTWRITEBYTECODE=1` and delete `__pycache__`: an edit of the same size, restored within the same second, leaves a stale `.pyc` that Python keeps running.
- The query-level bootstrap (each query its own cluster) peaks near 1 GB on all of dev; the clustered one needs 63 MB.
- `make gate` uses ports 8101 and 8102 and refuses to start if either is taken. It does not ingest: both sides read one Postgres index, so a chunking change must change the chunker id and be loaded first. Through `make`, a Fail and a gate that cannot run both exit 2; run `scripts/gate.py` directly to tell them apart (1 and 2).
- The gate workflow (4.7b) builds the index with the PR's code only, so a PR that changes a chunker id or the corpus text cannot be gated in CI (the baseline lacks its chunks or text). Its index cache is per PR: a PR's first run ingests (slow), later pushes restore. A GitHub job has no neutral state: Inconclusive passes with a warning.
- A subsampling study on dev must draw contracts with replacement: without it, subsets of 300 of the 408 contracts overlap so much that false Fails drop to 0 and power looks better than it is (F-014).
- A process started with `&` from a non-interactive shell ignores SIGINT; to interrupt a background ingest, use SIGTERM.
- `docs/private/`, `.env` and `data/` are gitignored on purpose. The old Design §15 text is still in public git history (decision for the user, not an agent).
- Agents never commit or push; propose a commit message and list new files that need `git add`.

## Agent protocol

**Picking work.** Take the first item in **Next** marked for an agent, or the step the user names. Steps that wait on the user are not yours: say what is needed. If no step is open to an agent, say so and stop; do not fill the session with doc edits.

**Where the effort goes.** A step's work is code, tests and measurements. Docs record the result; they are not progress. Read this file, your step in its phase file, and only what the step's **Refs** line names.

**Finishing.** A step is done only when its **Verify** check has actually been run and passed. Then change its `[ ]` to `[x]` and add under it:

```
- **Done:** YYYY-MM-DD. What changed, in one or two sentences.
  Evidence: the command run and the result that matters.
  Deviations: only if the step was not done as written.
```

**Doc budget.** At the end of a step, edit only:

1. the step's checkbox and Done note;
2. the phase's row in the status board, if the phase's state changed;
3. the **Next** list (rewrite it).

Only when the step produced one, also add: a row in `docs/results.md` for a measured headline number; a finding for something another step needs; an ADR for a hard-to-reverse decision; an eval-spec change the user approved.

- Do not edit the README, the design or the coding skill during a phase. Refresh the README once when a phase ends.
- Add a note under a later step only if that step would go wrong without it, in three lines at most.
- Keep lines short: one fact per bullet, no paragraph over about 300 characters, so edits stay small.
- Git is the change log: no change log in this file and no file lists in Done notes. The suggested commit message is a short summary, not a copy of the Done note.

**Blocked or skipped.** Mark `[!]` with the reason and what unblocks it. Never mark a step done when its Verify was skipped, failed or only reasoned about; write what was and was not checked. If the step as written is wrong or impossible, do not silently do something else: record a finding, add a `Deviations` line, and tell the user if it changes scope.

**Findings.** Create `docs/findings/F-NNN-slug.md` (next free number; copy `_template.md`) when you learn something another step or a future reader needs: a measured number that changes a decision, a data quirk, a result that contradicts the design, a hypothesis you could not check, a failed approach. Add one row to the findings index below in the same edit. Trivia about your own step goes in its Done note instead. State the evidence level honestly (measured, read from a source, hypothesis).

**Decisions.** A decision that is hard to reverse or that a reviewer will question becomes an ADR in `docs/adr/` at the moment it is made (copy `_template.md`), and gets a row in the ADR index. Decisions that belong to the user (the table below) are never made by an agent.

**Numbers.** Measured headline numbers go in `docs/results.md` with the regenerating command and run id. Nothing unreproducible goes in the README.

**Code.** Follow `.claude/skills/master-code-skill/SKILL.md` for every code change: smallest change that meets the step, a hand-computed test before a metric or statistic, real Postgres for SQL, gold labels never reaching the service. Run the real toolchain (ruff, pyright, pytest) and report what you ran.

**Git.** Never commit, merge, rebase or push, and never add Claude or Anthropic attribution anywhere in history (global rule from the user). Leave changes in the working tree, say which new files need `git add`, and propose a commit message. Steps that need a push or a PR are blocked on the user.

**Cut list and never-cut.** If the schedule slips, cut in the order of Design §11 (optional AWS deployment; self-preference test and PPI; chunker C3 and the weighted-fusion and paraphrase ablations; shrink QASPER). Never cut: blind human labels, clustered bootstrap, false-alarm and power measurements, demo PRs.

## Decisions needed from the user

Agents must not decide these. When answered, fill the row and date it. Source: Design §17.

| ID | Question | Blocks | Answer | Date |
| --- | --- | --- | --- | --- |
| D1 | LLM provider(s) for generator and judge, and the total budget. Two model families are needed for the self-preference test and are advisable for judge vs generator in any case. | Phase 5; 0.5 | 2026-11-05, partly answered by the user: the **judge is Claude** (Anthropic; the user has a key). Still open: the generator's provider and the total budget. Claude recommends OpenAI for the generator: a different model family from the judge (Design §8.4's mitigation), on the same account as D6's key. Was (2026-10-19): deferred until Phase 5. | 2026-11-05 |
| D2 | Hours per week available (the schedule assumes about 20; at 10, plan 14 to 16 weeks or apply the cut list now). | Schedule | Changed 2026-10-28: finish as soon as possible. First finish line is the end of Phase 4 (retrieval-only gate, no LLM spend, no labels); the cut list (Design §11, items 1 to 4) applies to Phases 5 to 9. Was (2026-10-19): not time-bound, cut list not applied. | 2026-10-28 |
| D3 | Public from day one or at v0.1? (Design leans toward public early. If yes, do 0.3 immediately and note that `docs/` is visible.) | 0.3, 9.8 | Already public (origin/main pushed). `docs/` is visible, including history before step 0.3. | 2026-10-19 |
| D4 | Second corpus: QASPER (recommended) or another. | Phase 9 | QASPER | 2026-10-19 |
| D5 | Package name (was the placeholder `rageval`). | Phase 1 | `ragcalibrate`. Rejected: `raglab` (taken on PyPI, clashes with RAGLAB) and `rageval` (crowded GitHub names). Free on PyPI, npm and GitHub on 2026-10-19. | 2026-10-19 |
| D6 | Embedding-model comparison (step 4.10): which second model, and its API key and spend cap. | 4.10 | 2026-10-28: comparison approved by the user. 2026-11-05, the user: **model OpenAI `text-embedding-3-small`**, confirmed. The user first asked for Anthropic; Anthropic has no embedding model (its docs point to Voyage AI, a separate MongoDB key), and when offered Voyage's models the user kept OpenAI. Key and spend cap: owner user, still needed before 4.10 starts. This brings one provider decision forward from D1, for embeddings only; D1 (generator and judge) is unchanged, and the user chose on 2026-11-05 to leave it until Phase 5. | 2026-11-05 |
| D7 | CUAD query text: keep CUAD's templated question ("Highlight the parts (if any) of this contract related to X that should be reviewed by a lawyer. Details: Y", as `docs/eval-spec.md` §1 says now), or use the question a user would ask (the "Details" part, perhaps with the category name)? Any change goes into the eval set, for every strategy, never into the service. | Re-baselining S1 to S4 (3.9) if changed | 2026-11-04, the user: **keep CUAD's templated question.** `docs/eval-spec.md` §1, the eval-set hash and the S1 to S4 runs stay as they are; S4 stays below S3 on dev, as measured. The question-alone result stays a diagnostic in F-012, not a scheduled ablation. Context when raised (2026-10-28, step 3.3): with the template the cross-encoder lowers recall@5 on dev (-1.5 points against S3); given only the "Details" part it raises it (+8.6 at rerank depth 20). Claude had recommended keeping the template, since changing it after seeing dev results is the move a careful reviewer flags. | 2026-11-04 |
| D8 | Which metric gates a **chunker** change? Eval spec §6.1 gives every retrieval change one primary metric, recall@5 (nothing saturated in the 3.9 check), but §3.4 says chunkers must not be compared on recall@k, which rewards big chunks. Measured on dev (F-013): going from 256- to 199-token windows would Fail the gate on recall@5 for S1 and S3 while retrieving more gold text per word. Claude recommends: when the two runs' chunker ids differ, the gate uses character recall@512 (already the fourth candidate in §6.1) instead of recall@5; every other retrieval change keeps recall@5. Alternative: keep §6.1 as written and state that chunker changes are out of the gate's scope. Either answer amends the user-approved spec. | An outcome from `compare` (4.4) when the chunkers differ (none until then); a chunker demo PR (Phase 8) | 2026-11-05, the user: **apply the recommendation.** When the two runs' chunker ids differ, the gate uses character recall@512 instead of recall@5; every other retrieval change keeps recall@5. Step 4.11 builds it and amends eval-spec §6.1. | 2026-11-05 |
| D9 | What does the CI gate run on? Step 4.6 (F-014) measured the gate on subsets of dev. Its false-alarm rate holds (2.5%), but with the noise of a strategy swap the smallest regression it catches 80% of the time is 0.051 at the current 60 contracts, 0.025 at 200, 0.021 at 300 and 0.018 on all 408 dev contracts. Eval-spec §6.3 (approved) says: if the MDE is above δ, enlarge the subset, and only then raise δ. Claude recommends: **the CI gate runs on all 408 dev contracts, δ stays 0.02**. That is the only size that meets δ; 90% of harmless strategy-sized changes Pass and 89% of 2-point regressions Fail; it is simpler (a CI run is an ordinary dev run, nothing to record about subsets). Cost: CI downloads CUAD and ingests 408 contracts (about 6 minutes on an M5, longer on a GitHub runner unless embeddings are cached), and an S4 run takes about 7.5 minutes. Alternatives: 300 contracts (MDE 0.021, about a quarter less CI time); or keep 60 and raise δ to 0.05, which would let through regressions three times the size of the S1-to-S3 gap. The yardstick (a strategy swap's noise) is also a choice: a change that touches few queries is caught at 40 contracts. Either answer amends eval-spec §6.3 and §7. | Step 4.7 (what CI runs and ingests); `CI_SIZE` stays 60 until then | 2026-11-05, the user: **apply the recommendation**: the retrieval gate runs on all 408 dev contracts, δ stays 0.02 (eval-spec §6.3, §7 amended). The user also chose to build the gate as a local command first (step 4.7a, `make gate`), with the GitHub Action (4.7b) wrapping it. | 2026-11-05 |

## Findings index

Open one only if **Affects** lists your step. Newest last.

| ID | One line | Affects | Status | Evidence |
| --- | --- | --- | --- | --- |
| [F-001](findings/F-001-judge-criteria-inconsistent.md) | Design lists three judge criteria in §5.6 but two in §8.3 | 1.8, 6.x, 7.2 | resolved (eval-spec §5) | read |
| [F-002](findings/F-002-fts-query-semantics.md) | Long templated questions under `websearch_to_tsquery` (AND) match almost nothing: no rows for 84% of dev queries. S1 uses an OR over the lexemes instead (ADR 0009) | 3.1, 3.9 | resolved | measured |
| [F-003](findings/F-003-few-clusters-bootstrap-coverage.md) | The cluster bootstrap under-covers below about 40 contracts (93.3% at 30, false fails 3.0% for a nominal 2.5%); the query-level one under-covers at every size (false fails 5.7% to 7.2% at dev's correlation). On real dev subsets (4.6): clustered 2.5%, query-level 3.7% | 4.2, 4.4, 4.5, 4.6 | confirmed (synthetic data and real dev subsets) | measured |
| [F-004](findings/F-004-ceiling-effect-per-document-retrieval.md) | Per-document retrieval may saturate recall@5, leaving no power. On dev no strategy is near a ceiling: recall@5 0.488 (S2) to 0.576 (S3), recall@10 at most 0.704 | 1.8, 2.10, 3.9, 4.6, 8.5 | refuted for S1 to S4 (C1); power is limited by churn, not a ceiling (4.6) | measured |
| [F-005](findings/F-005-labels-must-attach-to-frozen-answers.md) | Labels must key on frozen answer text; there is only one labeler | 6.3, 6.5, 7.2, 9.5 | open | read |
| [F-006](findings/F-006-skill-and-best-practices-doc-mismatch.md) | Skill references missing files; best-practices doc mostly targets another system | 0.4, 1.11, 2.11, 4.9, 5.9 | open | measured |
| [F-007](findings/F-007-not-plug-and-play-for-other-rag-systems.md) | No contract spec, conformance check, BYO eval-set format or offset-less fallback; not usable by outsiders yet | 2.7, 3.7, 4.7, 8.x, 9.5 | open | read |
| [F-008](findings/F-008-cuad-facts.md) | CUAD measured: 67.9% of pairs unanswerable (design said over a third); 6,702 answerable pairs; skewed category mix | 1.8, 2.x, 4.6, 6.x | confirmed | measured |
| [F-009](findings/F-009-prior-art-check.md) | Prior art checked: gate, false-alarm/power and span gold are novel in sources checked; judge-human kappa is not (TruLens, Langfuse have it). Suggested wording accepted and applied to Design §3 and the README on 2026-11-05; 9.x repeats the check | 1.1, 9.x, README | resolved | read |
| [F-010](findings/F-010-cuad-duplicate-contract.md) | One CUAD contract appears twice (both dev); the copies' labels differ in 2 of 41 categories, so some "no answer" labels are missed clauses | 2.6, 4.1, 4.2, 5.8, 7.x | confirmed | measured |
| [F-011](findings/F-011-fts-beats-dense-on-cuad-dev.md) | S1 (Postgres FTS) beats S2 (dense) on dev: recall@5 0.560 vs 0.488, ahead in 29 of 41 categories (S1 minus S2 +0.072 [+0.057, +0.087], step 4.4); S1's ranking function was tuned on dev. S3 (RRF) adds only 1.6 points over S1 (note from 3.2) | 3.2, 3.3, 3.9, 4.10, 8.5 | confirmed (dev, provisional) | measured |
| [F-012](findings/F-012-rerank-hurts-on-templated-questions.md) | S4 (cross-encoder rerank of S3's top N) lowers recall@5 on CUAD dev with the templated question; three models tried, all below S3. Given only the question's "Details" part, the same model raises it by 8.6 points. D7 answered 2026-11-04: the template stays | 3.3, 3.9, 4.x, 8.5, eval-spec §1 | resolved (D7: template kept) | measured |
| [F-013](findings/F-013-c2-helps-at-a-fixed-budget.md) | Chunker C2 beats C1 on dev at a fixed retrieved budget for S1 to S3, not at fixed k. The size-matched control (3.9) shows both causes: at 256 words, smaller windows give S2 +0.047 and C2's cuts +0.036 more at a matched size; size and structure about even at 512 and 1,024 words; that split depends on the budget unit, the gains for S2 and S3 do not (4.9, ADR 0004). Gate stays on C1 at 256; D8 raised | 3.9, 4.4, 4.9, 5.x, 8.x | confirmed (dev, provisional; cause measured) | measured |
| [F-014](findings/F-014-ci-subset-too-small-for-delta.md) | The clustered gate holds its false-alarm rate on real dev subsets (2.5%; query-level 3.7%), but with a strategy swap's noise its minimum detectable effect is 0.051 at the 60-contract CI subset and reaches δ = 0.02 only on all 408 dev contracts (0.018). D9: the gate runs on all of dev | 4.6, 4.7, 4.9, 8.x | resolved (D9: gate on all of dev) | measured |

F-001 to F-007 come from reading the docs while writing this plan; their hypotheses are things to check, not facts. F-008 (CUAD facts) is measured; F-009 (prior art) is read from public docs and papers on 2026-10-19.

## ADR index

Write each ADR when the decision is made (Design §12). Statuses: `planned`, `accepted`, `superseded`.

| # | Decision | Written in step | Status |
| --- | --- | --- | --- |
| 0001 | Postgres with pgvector rather than a dedicated vector database | 1.9 | accepted |
| 0002 | Exact search under the per-document filter, and no HNSW index (measured: HNSW returns short results, the planner picks it for the largest contract and returns 0 rows) | 2.8 | accepted |
| 0003 | Separate SQLite run store next to the Postgres corpus store | 1.9 | accepted |
| 0004 | Span-overlap relevance (R1 primary, R2 sensitivity) and budget metrics, with the budget counted in whitespace-separated words (R2 changes no gate outcome among S1 to S4; F-013's split between size and structure depends on the unit) | 4.9 | accepted |
| 0005 | Gold labels live in the harness, never in the system under test | 1.9 | accepted |
| 0006 | Binary per-criterion judge verdicts | 7.8 | planned |
| 0007 | Paired, document-clustered bootstrap and the three-outcome gate: recall@5, δ 0.02, all 408 dev contracts, 40-contract floor; validated by F-003 and F-014; generator metric deviation from Design §8.5 | 4.9 | accepted |
| 0008 | Caching and determinism strategy | 7.8 | planned |
| 0009 | Postgres FTS naming and the BM25 question; S1 query construction (OR over lexemes, `ts_rank`, no GIN index) | 1.9, 3.1 | accepted |
| 0010 | Baseline management in CI: retrieval recomputed at the merge base in the same job, only the index cached (accepted); LLM baseline stored from `main` with its age (planned, 8.2) | 4.9, 8.2 | accepted (retrieval) |
| 0011 | Local embedding model bge-small-en-v1.5 via ONNX Runtime (not sentence-transformers/PyTorch) | 2.5 | accepted |
| 0012 | Hosted embedding model for the comparison: pinning, cost, determinism, caching | 4.10 | planned |
| 0013 | Local cross-encoder ms-marco-MiniLM-L6-v2 for S4, via ONNX Runtime (three models piloted; all lower recall with CUAD's template) | 3.3 | accepted |

## Document map

| What | Where | When to open |
| --- | --- | --- |
| Design: rationale, methodology, schedule, risks (original plan, "Design §N"; changed since: §15 moved out in 0.3, §3 updated for F-009 on 2026-11-05) | `docs/design/project-design.md` | Only the section a step cites |
| Per-phase actionable steps and Done notes | `docs/phases/` | Your current phase |
| Findings | `docs/findings/` | When listed against your step |
| ADRs | `docs/adr/` | When your step writes or cites one |
| Results ledger | `docs/results.md` | When a step produces or reads a headline number |
| Eval spec (what the numbers mean) | `docs/eval-spec.md` (written in step 1.8) | Before touching metrics, splits, or the gate |
| Judge rubric | `docs/judge-rubric.md` (written in step 6.1) | Phase 6 and 7 |
| LLM production practices (partly applicable, see F-006) | `docs/llm-production-best-practices.md` | Phase 5 constraints are quoted inline |
| Project explainer for study and interviews (root README; refreshed once when a phase ends) | `README.md` | To understand or defend a decision |
| Coding rules for agents | `.claude/skills/master-code-skill/SKILL.md` | Any code change |
| Private career notes (after step 0.3) | `docs/private/` (gitignored) | Never in a public artifact |
