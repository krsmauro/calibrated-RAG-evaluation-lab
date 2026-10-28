# Calibrated RAG Evaluation Lab: project plan (index)

> **Every agent starts here.** This file is an index and a status board, not the design. Read it, then open only the file your current step points to. Last structural change: 2026-10-19.

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
| 2 CUAD, C1, dense retrieval, metrics | 2 | in progress | 2.1 to 2.5, 2.9 and 2.11 done; next 2.6 (ingest), then 2.7, 2.8, 2.10 | [phase-2](phases/phase-2-cuad-ingest-and-dense-retrieval.md) |
| 3 Strategies, C2, run store | 3 | todo | 3.1 | [phase-3](phases/phase-3-strategies-and-run-store.md) |
| 4 Stats and retrieval gate | 4 | todo | 4.1 | [phase-4](phases/phase-4-stats-and-retrieval-gate.md) |
| 5 Answers and LLM client | 5 | todo | 5.1 | [phase-5](phases/phase-5-answers-and-llm-client.md) |
| 6 Judge and labels | 6 | todo | 6.1 | [phase-6](phases/phase-6-judge-and-labels.md) |
| 7 Calibration report | 7 | todo | 7.1 | [phase-7](phases/phase-7-calibration-report.md) |
| 8 Full gate, demo PRs, latency | 8 | todo | 8.1 | [phase-8](phases/phase-8-full-gate-and-demo-prs.md) |
| 9 QASPER and release | 9 | todo | 9.1 | [phase-9](phases/phase-9-qasper-and-release.md) |

Phases run in order. An agent does not start phase N+1 until phase N's exit criterion is checked, unless the user says otherwise. Phase 4 (retrieval-only gate) is the safety net: if time runs short, a credible project exists after it.

## Current state and how to resume (handoff, 2026-10-28)

**Exists and works** (CI green on `main` at 4e41c31; everything after that is local until the user commits and pushes): `uv` project on Python 3.12, ruff, pyright strict on `src/`, pre-commit; Docker Compose with `pgvector/pgvector:0.8.7-pg17` on `127.0.0.1:5433`; `config.py`, `logs.py`; Alembic migration 0001 (`documents`, `chunks`, no embedding storage yet); CUAD loader and hashed eval sets (`corpora/`); retrieval metrics (`harness/metrics/retrieval.py`); chunker C1 (`ingest/chunkers.py`); the local embedder (`ingest/embedding.py`, ADR 0011); 53 unit and property tests. `service/`, `stats/`, `llm/`, `report/` are still empty.

**Run it:** Docker Desktop running and `uv` installed. `make up`, `uv run alembic upgrade head`, `make data` (CUAD), `make evalsets`, `make models` (134 MB embedding model), `make lint`, `make test`. `make down` stops Postgres. All downloads land in the gitignored `data/` and are sha256-checked.

**Finish line (D2, 2026-10-28):** as soon as possible. Get to the end of Phase 4 (retrieval-only gate) first; apply the cut list to Phases 5 to 9.

**Waiting on the user:**
- Commit and push the 2.4, 2.5 and 2.11 work; the first CI run of the new `make models` step is untested.
- Whether to add an embedding-model comparison (a second dense strategy on the same chunks) and which model; ADR 0011 says how storage must look for it, and step 2.6 carries a note.
- F-009 wording for Design §3 and the README (judge-agreement differentiator).
- D1 (provider, keys, budget) and 0.5 before Phase 5; whether labeling (Phase 6, 5 to 10 hours, F-005) is feasible, decided when Phase 6 starts.

**Next work:** 2.6 (idempotent ingest; embeddings in a table keyed by `(chunk_id, embedder_id)`), 2.7 (service and `/retrieve`, embedder called via `asyncio.to_thread`), 2.8 (exact vs HNSW, ADR 0002), 2.10 (first baseline; report recall at several k and per category, F-004, F-008).

**Things that bite:**
- ruff line length is 100 and Markdown is excluded from `ruff format`; `Settings` is built only by `load_settings()`; `scripts/` may print, `src/` may not.
- Tests that need `data/` (CUAD or the model) skip when the files are missing. CI downloads the model but not CUAD.
- Do not trust numbers copied from the design for CUAD; use F-008 and the 2.4 Done note (median contract 6,739 bge tokens).
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

## Findings index

Open one only if **Affects** lists your step. Newest last.

| ID | One line | Affects | Status | Evidence |
| --- | --- | --- | --- | --- |
| [F-001](findings/F-001-judge-criteria-inconsistent.md) | Design lists three judge criteria in §5.6 but two in §8.3 | 1.8, 6.x, 7.2 | resolved (eval-spec §5) | read |
| [F-002](findings/F-002-fts-query-semantics.md) | Long templated questions under `websearch_to_tsquery` (AND) may match almost nothing | 3.1, 3.9 | open | hypothesis |
| [F-003](findings/F-003-few-clusters-bootstrap-coverage.md) | Cluster bootstrap on a small CI subset may under-cover | 4.2, 4.5, 4.6 | open | hypothesis |
| [F-004](findings/F-004-ceiling-effect-per-document-retrieval.md) | Per-document retrieval may saturate recall@5, leaving no power | 1.8, 2.10, 4.6, 8.5 | open | hypothesis |
| [F-005](findings/F-005-labels-must-attach-to-frozen-answers.md) | Labels must key on frozen answer text; there is only one labeler | 6.3, 6.5, 7.2, 9.5 | open | read |
| [F-006](findings/F-006-skill-and-best-practices-doc-mismatch.md) | Skill references missing files; best-practices doc mostly targets another system | 0.4, 1.11, 2.11, 4.9, 5.9 | open | measured |
| [F-007](findings/F-007-not-plug-and-play-for-other-rag-systems.md) | No contract spec, conformance check, BYO eval-set format or offset-less fallback; not usable by outsiders yet | 2.7, 3.7, 4.7, 8.x, 9.5 | open | read |

| [F-008](findings/F-008-cuad-facts.md) | CUAD measured: 67.9% of pairs unanswerable (design said over a third); 6,702 answerable pairs; skewed category mix | 1.8, 2.x, 4.6, 6.x | confirmed | measured |
| [F-009](findings/F-009-prior-art-check.md) | Prior art checked: gate, false-alarm/power and span gold are novel in sources checked; judge-human kappa is not (TruLens, Langfuse have it); wording needs your decision | 1.1, 9.x, README | confirmed (wording pending) | read |

F-001 to F-007 come from reading the docs while writing this plan; their hypotheses are things to check, not facts. F-008 (CUAD facts) is measured; F-009 (prior art) is read from public docs and papers on 2026-10-19.

## ADR index

Write each ADR when the decision is made (Design §12). Statuses: `planned`, `accepted`, `superseded`.

| # | Decision | Written in step | Status |
| --- | --- | --- | --- |
| 0001 | Postgres with pgvector rather than a dedicated vector database | 1.9 | accepted |
| 0002 | Exact search vs HNSW under per-document filters, with measurements | 2.8 | planned |
| 0003 | Separate SQLite run store next to the Postgres corpus store | 1.9 | accepted |
| 0004 | Span-overlap relevance and token-budget metrics | 4.9 | planned |
| 0005 | Gold labels live in the harness, never in the system under test | 1.9 | accepted |
| 0006 | Binary per-criterion judge verdicts | 7.8 | planned |
| 0007 | Paired, document-clustered bootstrap and the three-outcome gate | 4.9 | planned |
| 0008 | Caching and determinism strategy | 7.8 | planned |
| 0009 | Postgres FTS naming and the BM25 question (and S1 query construction) | 1.9, 3.1 | accepted (naming); query construction added in 3.1 |
| 0010 | Baseline management in CI | 4.9, 8.2 | planned |
| 0011 | Local embedding model bge-small-en-v1.5 via ONNX Runtime (not sentence-transformers/PyTorch) | 2.5 | accepted |

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
