# Calibrated RAG Evaluation Lab: project plan (index)

> **Every agent starts here.** This file is an index and a status board, not the design. Read it, then open only the file your current step points to. Last structural change: 2026-10-28.

## What this project is

An open-source harness that answers: did this change make a RAG system better, by how much, and can I trust the judge that says so? It measures retrieval against span-level gold labels, calibrates its LLM judge against blind human labels (κ with CIs), and gates PRs on a paired, document-clustered bootstrap with a measured false-alarm rate and power. The system under test is a small hybrid-retrieval RAG service (FastAPI, Postgres with pgvector and FTS, a cross-encoder reranker) that the harness reaches only over HTTP. Full statement: `docs/design/project-design.md` §1.

## How to read this plan (progressive disclosure)

1. This file: status board, protocol, decisions, indexes. Always read.
2. The phase file for the step you are on (`docs/phases/`). Read that one only.
3. The Design section or skill reference that the step's **Refs** line names. Do not read the 50KB design end to end.
4. Findings: scan the findings index below; open a finding only if its **Affects** column lists your step.
5. `docs/results.md`, `docs/adr/` and `docs/eval-spec.md` (once it exists) when a step says so.

## Status board

Status values: `todo`, `in progress`, `blocked`, `done`. Update the row when a step changes the phase's state. The step-level detail lives in the phase file, not here.

| Phase | Design week | Status | Next step | File |
| --- | --- | --- | --- | --- |
| 0 Pre-flight | none | done (exit criterion met) | 0.3, 0.4, 0.6 done; D1 to D5 answered; 0.5 (API key and spend limit, owner: user) deferred to Phase 5 with D1 | [phase-0](phases/phase-0-preflight.md) |
| 1 Eval spec and skeleton | 1 | done (exit criterion met 2026-10-19; CI green, clean-clone check passed) | F-009 wording decision for Design §3 and the README is still pending with the user | [phase-1](phases/phase-1-spec-and-skeleton.md) |
| 2 CUAD, C1, dense retrieval, metrics | 2 | done (exit criterion met 2026-10-28; CI green at b0b3aea) | S2 dev baseline: recall@5 0.488, MRR@10 0.393 (provisional, `docs/results.md`) | [phase-2](phases/phase-2-cuad-ingest-and-dense-retrieval.md) |
| 3 Strategies, C2, run store | 3 | in progress | 3.1 and 3.2 done 2026-10-28 (dev recall@5: S1 0.560, S3 0.576, only 1.6 points above S1: F-011); next 3.3 (S4, rerank) | [phase-3](phases/phase-3-strategies-and-run-store.md) |
| 4 Stats and retrieval gate | 4 | todo | 4.1; 4.10 (embedding-model comparison, added 2026-10-28) runs after 4.4 and is outside the exit criterion | [phase-4](phases/phase-4-stats-and-retrieval-gate.md) |
| 5 Answers and LLM client | 5 | todo | 5.1 | [phase-5](phases/phase-5-answers-and-llm-client.md) |
| 6 Judge and labels | 6 | todo | 6.1 | [phase-6](phases/phase-6-judge-and-labels.md) |
| 7 Calibration report | 7 | todo | 7.1 | [phase-7](phases/phase-7-calibration-report.md) |
| 8 Full gate, demo PRs, latency | 8 | todo | 8.1 | [phase-8](phases/phase-8-full-gate-and-demo-prs.md) |
| 9 QASPER and release | 9 | todo | 9.1 | [phase-9](phases/phase-9-qasper-and-release.md) |

Phases run in order. An agent does not start phase N+1 until phase N's exit criterion is checked, unless the user says otherwise. Phase 4 (retrieval-only gate) is the safety net: if time runs short, a credible project exists after it.

## Current state and how to resume (handoff, 2026-10-28, after step 3.2)

**Exists and works** (Phase 2 and steps 3.1 and 3.2 committed and pushed, CI green at 503ff72): `uv` project on Python 3.12, ruff, pyright strict on `src/`, import-linter, pre-commit; Docker Compose with `pgvector/pgvector:0.8.7-pg17` on `127.0.0.1:5433`; `config.py`, `logs.py`; Alembic migrations 0001 (`documents`, `chunks`), 0002 (`chunk_embeddings`, untyped `vector`, one row per chunk and embedder) and 0003 (`chunks.tsv`, stored generated `to_tsvector('english', text)`, no GIN index); CUAD loader and hashed eval sets (`corpora/`); retrieval metrics (`harness/metrics/retrieval.py`); chunker C1 (`ingest/chunkers.py`); the local embedder (`ingest/embedding.py`, ADR 0011); resumable ingest (`ingest/load.py`, `make ingest`: 510 documents, 24,872 chunks, 24,872 vectors); the wire models (`contract.py`); the service (`service/`, `make serve`: `/retrieve` with `strategy` `fts` (S1, OR over the question's lexemes, `ts_rank`, ADR 0009), `dense` (S2, exact search, ADR 0002) or `hybrid` (S3, RRF in `service/fusion.py`, with `rrf_k` and `fusion_depth` required on the request), `/healthz`, `/readyz`, problem-details errors); the minimal harness (`harness/{adapter,run,cli}.py`, `uv run ragcalibrate run [--strategy fts|hybrid]`: dev answerable queries, JSON result in `runs/`); measurement scripts `scripts/measure_hnsw.py` (2.8), `scripts/measure_fts.py` (3.1) and `scripts/measure_rrf.py` (3.2). `ragcalibrate run` checks `/readyz` first and stops with one line if the service is not up. Tests: 86 unit and property, 42 integration (testcontainers, `make test-integration`). `stats/`, `llm/`, `report/` are still empty.

**Run it:** Docker Desktop running and `uv` installed. `make up`, `make data` (CUAD), `make evalsets`, `make models` (134 MB embedding model), `make ingest` (applies migrations; about 7 minutes the first time), `make serve`, `make lint`, `make test`, `make test-integration`. `make down` stops Postgres. All downloads land in the gitignored `data/` and are sha256-checked.

**Finish line (D2, 2026-10-28):** as soon as possible. Get to the end of Phase 4 (retrieval-only gate) first; apply the cut list to Phases 5 to 9.

**Waiting on the user:**
- D6, before step 4.10 starts: confirm the second embedding model (proposed: OpenAI `text-embedding-3-small`), create the API key, set a spend cap. The comparison itself was approved on 2026-10-28.
- F-009 wording for Design §3 and the README (judge-agreement differentiator).
- D1 (provider, keys, budget) and 0.5 before Phase 5; whether labeling (Phase 6, 5 to 10 hours, F-005) is feasible, decided when Phase 6 starts.

**Next work:** Phase 3 from 3.3 (S4, rerank), then 3.4 to 3.9; the minimal JSON run (2.10) becomes the SQLite run store and full runner in 3.5 to 3.7. Then Phase 4; the embedding comparison (4.10) after 4.4. Storage and `/retrieve` already support a second embedder (`embedder_id`). Numbers to keep in mind (dev, provisional, no CI): recall@5 and MRR@10 are S1 0.560 and 0.455, S2 0.488 and 0.393, S3 0.576 and 0.477. S1 is ahead of S2 in 29 of 41 categories; S3 gains where S2 is strong and gives back part of S1's lead on exact legal terms, netting 1.6 points (F-011), so S4 must beat S3 and S1. None of the three is near a ceiling (F-004). The Phase 3 file carries notes under 3.3, 3.4, 3.6, 3.7, 3.8 and 3.9; read the one for your step before starting it.

**Things that bite:**
- ruff line length is 100 and Markdown is excluded from `ruff format`; `Settings` is built only by `load_settings()`; `scripts/` may print, `src/` may not.
- Tests that need `data/` (CUAD or the model) skip when the files are missing. CI downloads the model but not CUAD.
- S1 returns only chunks that share a word with the query: fewer than k, or none, is a valid answer, not an error. Its text-search configuration lives in two places (migration 0003's generated column and `FTS_CONFIG` in `service/retrieval.py`); an integration test fails if they differ.
- Do not trust numbers copied from the design for CUAD; use F-008 and the 2.4 Done note (median contract 6,739 bge tokens).
- Round a number for `docs/results.md` once, from the exact mean in the run JSON (`summary`), not from the CLI's four-decimal printout: S2's recall@5 was rounded twice (0.48846 to 0.4885 to 0.489) and quoted wrongly in nine places until 3.2.
- The contract is strict (`extra="forbid"`) and the harness sends every request field, including `rrf_k: null` and `fusion_depth: null`. A `make serve` started before a change to `contract.py` answers every harness request with 422 `Extra inputs are not permitted`: restart the service after changing the contract.
- Test files need unique basenames across `tests/unit`, `tests/property` and `tests/integration` (there is no `__init__.py`); a repeated name fails collection with `import file mismatch`.
- A process started with `&` from a non-interactive shell ignores SIGINT; to interrupt a background ingest, use SIGTERM.
- `docs/private/`, `.env` and `data/` are gitignored on purpose. The old Design §15 text is still in public git history (decision for the user, not an agent).
- Agents never commit or push; propose a commit message and list new files that need `git add`.

## Agent protocol

**Picking work.** Take the first step in the lowest-numbered unfinished phase whose prerequisites are met, or the step the user names. Steps marked "owner: user" are not yours: tell the user what is needed and move to the next unblocked step.

**Claiming.** Before starting, re-read the phase file, then change the step's `[ ]` to `[~]` and add a line `Claimed: <agent or session name>, YYYY-MM-DD`. If it is already `[~]` and the date is recent, pick something else. Edit only your step's lines, and re-read the file immediately before editing; other agents may have changed it.

**Finishing.** A step is done only when its **Verify** check has actually been run and passed. Then: change `[~]` to `[x]`, and append under the step:

```
- **Done:** YYYY-MM-DD, <agent>. What was done (one to three sentences).
  Evidence: <command run and the result that matters, or the path of the output>.
  Files: <paths created or changed>.
  Deviations: <anything that differs from the step as written, or "none">.
```

Then update the phase's row in the status board (status and next step). If the phase's exit criterion is now met, say so in the row and note it in the phase file.

**Blocked or skipped.** Mark `[!]` with the reason and what unblocks it. Never mark a step done when its Verify was skipped, failed or only reasoned about; write what was and was not checked. If the step as written is wrong or impossible, do not silently do something else: record a finding, add a `Deviations` note, and tell the user if it changes scope.

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
| D1 | LLM provider(s) for generator and judge, and the total budget. Two model families are needed for the self-preference test and are advisable for judge vs generator in any case. | Phase 5; 0.5 | Deferred until Phase 5: the user will choose providers, keys and budget when we get there. | 2026-10-19 |
| D2 | Hours per week available (the schedule assumes about 20; at 10, plan 14 to 16 weeks or apply the cut list now). | Schedule | Changed 2026-10-28: finish as soon as possible. First finish line is the end of Phase 4 (retrieval-only gate, no LLM spend, no labels); the cut list (Design §11, items 1 to 4) applies to Phases 5 to 9. Was (2026-10-19): not time-bound, cut list not applied. | 2026-10-28 |
| D3 | Public from day one or at v0.1? (Design leans toward public early. If yes, do 0.3 immediately and note that `docs/` is visible.) | 0.3, 9.8 | Already public (origin/main pushed). `docs/` is visible, including history before step 0.3. | 2026-10-19 |
| D4 | Second corpus: QASPER (recommended) or another. | Phase 9 | QASPER | 2026-10-19 |
| D5 | Package name (was the placeholder `rageval`). | Phase 1 | `ragcalibrate`. Rejected: `raglab` (taken on PyPI, clashes with RAGLAB) and `rageval` (crowded GitHub names). Free on PyPI, npm and GitHub on 2026-10-19. | 2026-10-19 |
| D6 | Embedding-model comparison (step 4.10): which second model, and its API key and spend cap. | 4.10 | 2026-10-28: comparison approved by the user. Model: OpenAI `text-embedding-3-small`, proposed by Claude and not yet explicitly confirmed. Key and spend cap: owner user, needed before 4.10 starts. This brings one provider decision forward from D1, for embeddings only; D1 (generator and judge) is unchanged. | 2026-10-28 |

## Findings index

Open one only if **Affects** lists your step. Newest last.

| ID | One line | Affects | Status | Evidence |
| --- | --- | --- | --- | --- |
| [F-001](findings/F-001-judge-criteria-inconsistent.md) | Design lists three judge criteria in §5.6 but two in §8.3 | 1.8, 6.x, 7.2 | resolved (eval-spec §5) | read |
| [F-002](findings/F-002-fts-query-semantics.md) | Long templated questions under `websearch_to_tsquery` (AND) match almost nothing: no rows for 84% of dev queries. S1 uses an OR over the lexemes instead (ADR 0009) | 3.1, 3.9 | resolved | measured |
| [F-003](findings/F-003-few-clusters-bootstrap-coverage.md) | Cluster bootstrap on a small CI subset may under-cover | 4.2, 4.5, 4.6 | open | hypothesis |
| [F-004](findings/F-004-ceiling-effect-per-document-retrieval.md) | Per-document retrieval may saturate recall@5, leaving no power. S2 on dev: recall@5 0.488, so no ceiling for S2; recheck S4 in 3.9 | 1.8, 2.10, 3.9, 4.6, 8.5 | refuted for S2 | measured (S2) |
| [F-005](findings/F-005-labels-must-attach-to-frozen-answers.md) | Labels must key on frozen answer text; there is only one labeler | 6.3, 6.5, 7.2, 9.5 | open | read |
| [F-006](findings/F-006-skill-and-best-practices-doc-mismatch.md) | Skill references missing files; best-practices doc mostly targets another system | 0.4, 1.11, 2.11, 4.9, 5.9 | open | measured |
| [F-007](findings/F-007-not-plug-and-play-for-other-rag-systems.md) | No contract spec, conformance check, BYO eval-set format or offset-less fallback; not usable by outsiders yet | 2.7, 3.7, 4.7, 8.x, 9.5 | open | read |
| [F-008](findings/F-008-cuad-facts.md) | CUAD measured: 67.9% of pairs unanswerable (design said over a third); 6,702 answerable pairs; skewed category mix | 1.8, 2.x, 4.6, 6.x | confirmed | measured |
| [F-009](findings/F-009-prior-art-check.md) | Prior art checked: gate, false-alarm/power and span gold are novel in sources checked; judge-human kappa is not (TruLens, Langfuse have it); wording needs your decision | 1.1, 9.x, README | confirmed (wording pending) | read |
| [F-010](findings/F-010-cuad-duplicate-contract.md) | One CUAD contract appears twice (both dev); the copies' labels differ in 2 of 41 categories, so some "no answer" labels are missed clauses | 2.6, 4.1, 4.2, 5.8, 7.x | confirmed | measured |
| [F-011](findings/F-011-fts-beats-dense-on-cuad-dev.md) | S1 (Postgres FTS) beats S2 (dense) on dev: recall@5 0.560 vs 0.488, ahead in 29 of 41 categories; no CI yet, and S1's ranking function was tuned on dev. S3 (RRF) adds only 1.6 points over S1 (note from 3.2) | 3.2, 3.3, 3.9, 4.10, 8.5 | confirmed (dev, provisional) | measured |

F-001 to F-007 come from reading the docs while writing this plan; their hypotheses are things to check, not facts. F-008 (CUAD facts) is measured; F-009 (prior art) is read from public docs and papers on 2026-10-19.

## ADR index

Write each ADR when the decision is made (Design §12). Statuses: `planned`, `accepted`, `superseded`.

| # | Decision | Written in step | Status |
| --- | --- | --- | --- |
| 0001 | Postgres with pgvector rather than a dedicated vector database | 1.9 | accepted |
| 0002 | Exact search under the per-document filter, and no HNSW index (measured: HNSW returns short results, the planner picks it for the largest contract and returns 0 rows) | 2.8 | accepted |
| 0003 | Separate SQLite run store next to the Postgres corpus store | 1.9 | accepted |
| 0004 | Span-overlap relevance and token-budget metrics | 4.9 | planned |
| 0005 | Gold labels live in the harness, never in the system under test | 1.9 | accepted |
| 0006 | Binary per-criterion judge verdicts | 7.8 | planned |
| 0007 | Paired, document-clustered bootstrap and the three-outcome gate | 4.9 | planned |
| 0008 | Caching and determinism strategy | 7.8 | planned |
| 0009 | Postgres FTS naming and the BM25 question; S1 query construction (OR over lexemes, `ts_rank`, no GIN index) | 1.9, 3.1 | accepted |
| 0010 | Baseline management in CI | 4.9, 8.2 | planned |
| 0011 | Local embedding model bge-small-en-v1.5 via ONNX Runtime (not sentence-transformers/PyTorch) | 2.5 | accepted |
| 0012 | Hosted embedding model for the comparison: pinning, cost, determinism, caching | 4.10 | planned |

## Document map

| What | Where | When to open |
| --- | --- | --- |
| Design: rationale, methodology, schedule, risks (original plan, unchanged, "Design §N") | `docs/design/project-design.md` | Only the section a step cites |
| Per-phase actionable steps and Done notes | `docs/phases/` | Your current phase |
| Findings | `docs/findings/` | When listed against your step |
| ADRs | `docs/adr/` | When your step writes or cites one |
| Results ledger | `docs/results.md` | When a step produces or reads a headline number |
| Eval spec (what the numbers mean) | `docs/eval-spec.md` (written in step 1.8) | Before touching metrics, splits, or the gate |
| Judge rubric | `docs/judge-rubric.md` (written in step 6.1) | Phase 6 and 7 |
| LLM production practices (partly applicable, see F-006) | `docs/llm-production-best-practices.md` | Phase 5 constraints are quoted inline |
| Project explainer for study and interviews (root README; keep in sync with the design) | `README.md` | To understand or defend a decision |
| Coding rules for agents | `.claude/skills/master-code-skill/SKILL.md` | Any code change |
| Private career notes (after step 0.3) | `docs/private/` (gitignored) | Never in a public artifact |

## Plan change log

Append one line per structural change to the plan. Newest last.

- 2026-10-19: Converted this file from the single design document into an index. The original text is preserved byte-for-byte at `docs/design/project-design.md`; section numbers are unchanged, so "Design §N" references remain valid. Added phases 0 to 9, findings F-001 to F-006, ADR index and results ledger. Added Phase 0 (not in the original schedule) for user-owned blockers.
- 2026-10-19: Step 0.3 moved Design §15 to `docs/private/career-notes.md` (gitignored); the design file is no longer byte-for-byte the original at that section. Step 0.4 repointed the skill's citations to the design file.
- 2026-10-19: Package renamed from the placeholder `rageval` to `ragcalibrate` in all docs and the skill (D5).
- 2026-10-19: Phase 0 closed (exit criterion met; 0.5 deferred to Phase 5). Added this file's "Current state and how to resume" section.
- 2026-10-19: Steps 1.1 to 1.4 and 1.6 to 1.11 done; 1.5 written and blocked on the user's push. Added findings F-008 (CUAD facts) and F-009 (prior art) and ADRs 0001, 0003, 0005, 0009. README status, layout and command sections updated to match; Design §3 and the README differentiator wording left unchanged pending the user's decision on F-009.
- 2026-10-19: Step 1.8 done. `docs/eval-spec.md` approved. It deviates from Design §8.5 on the generator primary metric (end-to-end correct rate, faithfulness as guard) and uses all of train as dev (§8.1).
- 2026-10-28: D2 changed (finish as soon as possible; Phase 4 first, cut list for Phases 5 to 9). Steps 2.4, 2.5 and 2.11 done; ADR 0011 added (embedding model via ONNX Runtime). Handoff section refreshed.
- 2026-10-28: Added step 4.10 (embedding-model comparison, user request) and decision D6; notes on 2.6 and 2.7 so storage and `/retrieve` support a second embedder; a results-ledger row; ADR 0012 reserved for the hosted embedder. Handoff section updated after commit 014cd8c.
- 2026-10-28: Steps 2.6 (ingest) and 2.7 (service) done; a chunker bug from 2.4 fixed (note under 2.4); finding F-010 (duplicate CUAD contract); stray blank line removed from the findings table so F-008 and F-009 render as rows. Handoff section refreshed.
- 2026-10-28: Steps 2.8 (ADR 0002: exact search, no HNSW) and 2.10 (first S2 baseline, results ledger) done; Phase 2 exit criterion met. F-004 refuted for S2; F-008 carries a measured note on per-category results.
- 2026-10-28: After commit b0b3aea: CI result recorded; S2 baseline rerun on the clean commit (same values) and the results-ledger row repointed to it; notes from Phase 2 added to Phase 3 steps; stale state text fixed in the README status, the coding skill (wire models live in `contract.py`) and F-007.
- 2026-10-28: Step 3.1 done (S1, Postgres FTS): migration 0003, ADR 0009 completed, F-002 resolved, finding F-011 added (S1 beats S2 on dev), an S1 row in the results ledger, notes under 3.2, 3.8, 3.9 and 8.5, and the coding skill's FTS rule (DB-HIGH-2) updated. Handoff section refreshed.
- 2026-10-28: After commit 8875b32 (CI green): S1 rerun on the clean commit (identical per query) and its ledger row repointed. Step 3.2 done (S3, RRF): fusion parameters on the request, a dev tuning script, an S3 ledger row, a note on F-011 (S3 only 1.6 points above S1), notes under 3.3, 3.6 and 3.8. Corrected S2's recall@5 from a mis-rounded 0.489 to 0.488 (exact 0.48846) everywhere it was quoted. Handoff section refreshed.
- 2026-10-28: After commit 503ff72 (CI green): S3 rerun on the clean commit (identical per query) and its ledger row repointed. `ragcalibrate run` now checks the service's readiness before a run and reports a down service in one line (note under 3.7, F-007). Handoff section refreshed.
