# Phase 1: Eval spec and repo skeleton (Design Week 1)

**Goal:** write down every decision that would otherwise produce an indefensible number, and get a repo where `make up` works from a clean clone.
**Entry:** Phase 0 done, or at least D5 (package name, answered) in the plan.
**Exit criterion:** `make up` works from a clean clone; CI green on the empty app; `docs/eval-spec.md` written; first ADRs written.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 1.1 [x] Read the prior art and verify the comparison table
- **Do:** read ARES (Saad-Falcon et al., 2023), LegalBench-RAG (Pipitone and Alami, 2024) and the current Ragas, DeepEval, promptfoo and TruLens docs. For each row of the prior-art table, mark it verified or corrected, with the date checked.
- **Verify:** a finding (`docs/findings/`) lists, per tool, what was checked and what changed. Anything that changes the differentiator in Design §3 is flagged to the user.
- **Refs:** Design §3, §8.4 (PPI).
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude, using three research agents whose key claims Claude re-checked. Read ARES (arXiv 2311.09476 v2) and LegalBench-RAG (arXiv 2408.10343 v1) in full-text HTML, and the current docs of Ragas, DeepEval, promptfoo, TruLens and Langfuse (the table row "TruLens, Langfuse evals" is split in two). Finding F-009 lists, per tool, what was checked and what changed.
  Evidence: F-009 (comparison table, dates, versions, what was verified directly and what was not). The Design §3 differentiator changes: judge-human kappa exists in TruLens and Langfuse, so that claim must be narrowed to a bootstrap CI on kappa with blind labels. **Flagged to the user; Design §3 and the README are not edited until they decide.**
  Files: `docs/findings/F-009-prior-art-check.md`, `docs/project-plan.md` (findings index).
  Deviations: tool docs were read, not tool source code; hosted and paid features were not examined; the prior-art row for "TruLens, Langfuse evals" is now two rows in the finding. Papers were read as HTML renderings, not PDFs. The LegalBench-RAG metric definition was confirmed in its code, because the paper does not define it.
#### 1.2 [x] Repo skeleton: uv, ruff, pyright, pre-commit
- **Do:** `pyproject.toml` with the `src/ragcalibrate` layout (name per D5), a committed `uv.lock`, ruff lint and format, pyright strict on `src/`, pre-commit with ruff and a secret scanner (gitleaks). Add `import-linter` only when there are two packages to separate (step 2.7). Pin the Python version and record why. Empty packages for `corpora/ ingest/ service/ llm/ harness/ stats/ report/`, each with a one-line docstring and nothing else.
- **Verify:** `uv sync && uv run ruff check . && uv run ruff format --check . && uv run pyright` all pass on a fresh clone.
- **Refs:** Design §9 (Tooling), §13; skill Layer 2 (XC-CRITICAL-4: no dependency without an importer).
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. `pyproject.toml` (uv_build backend, Python pinned to 3.12 with the reason in a comment, no runtime dependencies), committed `uv.lock`, ruff (E,F,I,B,UP,ASYNC,S,T20,RUF), pyright strict on `src/`, empty packages with one-line docstrings, test directories, `.pre-commit-config.yaml` and Python entries in `.gitignore`.
  Evidence: in a scratch copy of the non-ignored files (git-initialised, 54 files): `uv sync --frozen`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright` (0 errors) and `uv run pre-commit run --all-files` (all 8 hooks passed, including gitleaks on staged files). Installed: uv 0.13.1, ruff 0.17.1, pyright 1.1.414, pre-commit 4.7.0.
  Files: `pyproject.toml`, `uv.lock`, `.python-version`, `.pre-commit-config.yaml`, `.gitignore`, `src/ragcalibrate/**/__init__.py`, `src/ragcalibrate/py.typed`, `tests/{unit,property,integration}/.gitkeep`; also fixed one leftover `RAGEVAL_` env prefix in the skill.
  Deviations: not a real `git clone` (nothing is committed yet), a copy of the non-ignored working tree instead; rerun from a real clone at step 1.12. Ruff here also formats Markdown code blocks, so `*.md` is excluded from `ruff format`. Pre-commit hooks run ruff and pyright through `uv run` so `uv.lock` is the only version pin. The gitleaks hook needs the binary on PATH (`brew install gitleaks`). `pre-commit install` was not run (it would write into your `.git/hooks`).
  Not checked: pytest (no tests or dependency yet; arrives with step 1.6).
#### 1.3 [x] Docker Compose with Postgres and pgvector
- **Do:** `docker-compose.yml` with a pgvector-enabled Postgres, image pinned to an explicit tag (not `latest`), a healthcheck, a named volume. Makefile targets: `up`, `down`, `test`, `lint`. `.env.example` lists every setting.
- **Verify:** `make up` then `psql -c "select extversion from pg_extension where extname='vector'"` after step 1.4 returns a version. Record the pgvector version in the manifest notes.
- **Refs:** Design §9, §6 (data model).
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. `docker-compose.yml` (image `pgvector/pgvector:0.8.7-pg17`, healthcheck, named volume, compose project name `ragcalibrate`), `Makefile` (`up`, `down`, `test`, `lint`), `.env.example`.
  Evidence: `make up` ended `Healthy`; `psql` inside the container returned pgvector 0.8.7 available and PostgreSQL 17.11; after migration 0001, `select extversion from pg_extension where extname='vector'` returned 0.8.7. **Manifest note: pgvector 0.8.7, PostgreSQL 17.11.**
  Files: `docker-compose.yml`, `Makefile`, `.env.example` (and an untracked local `.env` copied from it by `make up`).
  Deviations: Postgres is published on `127.0.0.1:5433` (not 5432) so it cannot clash with another Postgres on the machine. `make up` creates `.env` from the example, whose values are local-development only. pg17 chosen over pg18 as the mature release. `make down` was not exercised yet (step 1.12 does).
#### 1.4 [x] Settings module and Alembic baseline
- **Do:** one `pydantic-settings` class in `ragcalibrate/config.py` (no other `os.environ` use). Alembic initialised; first migration creates the `vector` extension, `documents` and `chunks` per Design §6 data model (no `tsv` or HNSW index yet; those arrive in Phases 2 and 3 with the evidence behind them). No `create_all` anywhere.
- **Verify:** `uv run alembic upgrade head` on an empty database succeeds, then `downgrade base` then `upgrade head` again. `grep -rn "os.environ\|os.getenv" src/` returns only `config.py`.
- **Refs:** skill BE-CRITICAL-1; Design §9 (Database).
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. `ragcalibrate/config.py` (one `Settings` class with `RAGCALIBRATE_` prefix, a masked `SecretStr` database URL, `load_settings()`), Alembic at the repo root with an env.py that takes its URL from settings, and migration `0001` creating the `vector` extension, `documents` and `chunks`. Dependencies added with their importers: pydantic-settings (config.py), alembic and sqlalchemy (migrations/env.py), psycopg[binary] (the driver SQLAlchemy loads), pytest (tests).
  Evidence: against the real Postgres, `alembic downgrade base` left only `alembic_version` and no vector extension; then `upgrade head`, `downgrade base`, `upgrade head` all succeeded and `alembic current` printed `0001 (head)`. `grep -rn "os.environ\|os.getenv" src/ migrations/` returns nothing. Constraints checked by hand in a rolled-back transaction: a valid chunk is accepted; a duplicate chunk, a text length that differs from `end-start`, an empty span and a duplicate `(corpus, external_id)` are all rejected. `make test` 4 passed; ruff, format check and pyright (strict on `src/`) clean.
  Files: `src/ragcalibrate/config.py`, `alembic.ini`, `migrations/{env.py,script.py.mako,versions/0001_baseline.py}`, `tests/unit/test_config.py`, `pyproject.toml`, `uv.lock`, `.env.example`, `Makefile`.
  Deviations: the `chunks.embedding` column (and its model id) is not in this migration: its dimension depends on the embedding model, chosen in step 2.5, so Phase 2 adds it with that migration. The ids are `bigint` identity columns, and `documents` is unique on `(corpus, external_id)` with `sha256` stored but not unique. `chunks` has a `char_length(text) = end_char - start_char` check and relies on its unique index for the per-document lookup instead of a separate btree. Line length set to 100 in ruff. One `pyright: ignore` in `load_settings()` (pyright mis-reads pydantic-settings fields as required arguments). Offline (SQL-script) Alembic mode is not supported on purpose. Integration test of the migration is not written yet (testcontainers arrives with the first integration test).
#### 1.5 [!] CI workflow
- **Do:** GitHub Actions workflow running lint, pyright and unit tests on every PR, with a Postgres service for integration tests later. Least-privilege `permissions:`. Never `pull_request_target`.
- **Verify:** workflow file passes `actionlint` if available; first run is green on the empty app. (Needs the user to push; the agent cannot. Mark `[!]` blocked-on-user until the user confirms the run is green.)
- **Refs:** Design §8.5 (fork PRs), §9.
- Claimed: Claude (session 6137b804), 2026-10-19
- **Blocked on the user:** the workflow is written and passes `actionlint`; it needs a push, then confirmation that the first run is green. Unblocks when the user pushes and reports the run result.
  Written: `.github/workflows/ci.yml` with four jobs (lint: ruff, format, pyright; test: `make test`; migrations: `make up` then `alembic upgrade head`, `downgrade base`, `upgrade head` on the Compose Postgres; secrets: gitleaks over full history). `permissions: contents: read`, triggers `pull_request` and `push` to `main` only (never `pull_request_target`), all three third-party actions pinned to commit SHAs with the tag in a comment (checkout v7.0.1, setup-uv v10.3.0, gitleaks-action v3.0.0; SHAs from the GitHub API on 2026-10-19).
  Checked locally: `actionlint` clean, YAML check passes, and each command in the lint, test and migrations jobs was run locally. Not checked: any run on GitHub; the gitleaks action in particular (its licence terms for your account type and its behaviour on forks) is untested.
#### 1.6 [x] Structured logging skeleton
- **Do:** JSON logs with `run_id` and `query_id` fields available via contextvars. No `print`.
- **Verify:** a unit test captures one log line and asserts the fields.
- **Refs:** Design §9 (Logging).
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. `ragcalibrate/logs.py`: a stdlib-only `JsonFormatter` (one JSON object per line: ts, level, logger, event, any `extra` fields, `exception`), two context variables `run_id` and `query_id` that the formatter adds when set, and `configure_logging()` for the entrypoint (stderr).
  Evidence: `tests/unit/test_logs.py` (5 tests) captures a real line and asserts the fields, the context IDs, that explicit `extra` wins over context, that IDs are absent when unset, and that the traceback is kept; `make test` 9 passed; pyright strict clean; running `configure_logging()` printed valid JSON lines with `run_id`.
  Files: `src/ragcalibrate/logs.py`, `tests/unit/test_logs.py`.
  Deviations: none. No helper to set and reset the IDs was added (nothing uses one yet); the runner in Phase 3 adds it when it needs one.
#### 1.7 [x] Measure the CUAD facts the spec depends on
- **Do:** download CUAD with a checksum (script lives in `scripts/`, no new dependency beyond what step 1.2 installed unless justified). Compute and record: number of contracts and categories; total pairs (510 x 41 = 20,910 claimed); share of pairs with no gold span (Design §5.4 says "more than a third"); number of gold spans per answerable pair (distribution); number of test rows and test contracts (Design §8.1 says 4,182 and 102, "confirm on load"); whether `text[answer_start:answer_start+len(answer)] == answer` holds for every label; contract length distribution in characters and tokens; the license text on the source page.
- **Verify:** one finding, `F-0NN-cuad-facts.md`, with the numbers, the command that produced them and the dataset checksum. Any number that differs from the Design is called out.
- **Refs:** Design §5.3, §5.4, §8.1, §10.
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. `scripts/fetch_cuad.py` downloads `data.zip` pinned to a commit and verifies size and sha256 (`make data`); `scripts/cuad_facts.py` reads the zip in memory and prints every requested number. Finding F-008 records them.
  Evidence: `make data` printed `ok: ... sha256 f8161d18bea4...`; `uv run python -I scripts/cuad_facts.py` produced the numbers in F-008 (510 contracts, 41 categories, 20,910 pairs, 67.9% unanswerable, 13,823 spans, 0 offset failures, test 102 contracts / 4,182 rows, contract median 33,143 chars). Ruff, format and pyright clean.
  Files: `scripts/fetch_cuad.py`, `scripts/cuad_facts.py`, `docs/findings/F-008-cuad-facts.md`, `Makefile` (target `data`), `pyproject.toml` (T20 allowed in `scripts/`), `.gitignore` (`data/`), `docs/eval-spec.md` (dated note), `docs/project-plan.md` (findings index).
  Deviations: the Design said "more than a third" unanswerable; measured 67.9%, called out in F-008. Token lengths are not measured (only chars and whitespace words) because the tokenizer is not chosen yet. The license was read from the dataset's own page and the Hugging Face loader string; the GitHub repo has no LICENSE file. The raw zip was inspected, not extracted.
#### 1.8 [x] Write `docs/eval-spec.md`
- **Do:** one document, the single source of truth for what the numbers mean. It must settle:
  1. Primary task: within-document retrieval (Design §5.1).
  2. Relevance rule: the overlap threshold (any overlap or at least 50 percent of the gold span), plus the sensitivity analysis to run (Design §5.2).
  3. Exact metric definitions (Design §8.2), including empty-input behaviour.
  4. Which metrics are computed on answerable queries only; abstention metrics (Design §5.4).
  5. Judge criteria. Design §5.6 lists three (faithfulness, correctness, citation support) but §8.3 makes citation checking deterministic and judges only two. Resolve it. See finding F-001.
  6. The primary metric per kind of change, δ (smallest regression worth blocking) with a rationale, and the three-outcome gate rule (Design §8.5).
  7. Dev, CI-subset and test split policy; test is touched once per frozen configuration (Design §8.1).
  8. The k and token budget values to report, chosen with headroom in mind (finding F-004).
- **Verify:** every section of Design §5 and §8 either appears in the spec or is listed as "deferred to step X". The user has read and approved it (agents do not self-approve a spec).
- **Refs:** Design §5, §8; findings F-001, F-004.
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude; approved by the user the same day. Wrote `docs/eval-spec.md` covering all eight items; Design §5 and §8 coverage is in its section 10, with deferrals tied to named steps.
  Evidence: the user read the spec and approved it after the draft was posted; the coverage table lists every Design §5.x and §8.x section as settled or deferred to a step.
  Files: `docs/eval-spec.md` (new, needs `git add`), findings F-001 and F-004 resolutions.
  Deviations: generator primary metric is the end-to-end correct rate with a faithfulness guard, not faithfulness alone as in Design §8.5 (gameable by abstaining). Dev is all of train rather than a carve-out. Provisional items remain by design: tokenizer (4.9), minimum cluster count (4.2), CI subset size and MDE (4.6), δ final values (4.6, 8.x), calibration set sizes (6.1).

#### 1.9 [x] First ADRs
- **Do:** write ADR 0001 (Postgres with pgvector), 0003 (separate SQLite run store), 0005 (gold labels live in the harness), 0009 (FTS is not BM25) at `docs/adr/`. Use `docs/adr/_template.md`. Short.
- **Verify:** each has context, decision, alternatives, consequences; the plan's ADR index is updated.
- **Refs:** Design §12.
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. ADRs 0001 (Postgres with pgvector), 0003 (separate SQLite run store), 0005 (gold labels live in the harness) and 0009 (FTS is not BM25), each with context, decision, alternatives and consequences; the plan's ADR index is updated.
  Evidence: the four files exist under `docs/adr/` and follow `_template.md`; the ADR index rows read `accepted`.
  Files: `docs/adr/0001-postgres-with-pgvector.md`, `0003-separate-sqlite-run-store.md`, `0005-gold-labels-live-in-the-harness.md`, `0009-postgres-fts-is-not-bm25.md`, `docs/project-plan.md`.
  Deviations: ADR 0001 is a reasoned decision, not a measured one (stated in the ADR). ADR 0009 is accepted for the naming only; the S1 query-construction part is left open for step 3.1 (finding F-002) and marked as such in the ADR.

#### 1.10 [x] `DATA_LICENSES.md`
- **Do:** skeleton listing CUAD (CC BY 4.0, credit The Atticus Project, link the license) and the repo's own MIT code license. QASPER is added in Phase 9 after its license is checked against the primary source.
- **Verify:** the file exists; the CUAD license was checked against the dataset's own page, not from memory.
- **Refs:** Design §10.
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. `DATA_LICENSES.md` with the MIT code license, CUAD (CC BY 4.0, credit, license link, provenance, paper) and a QASPER placeholder for Phase 9.
  Evidence: the CUAD license was read from the dataset's own page (atticusprojectai.org/cuad lists CC BY 4.0) and the Hugging Face loader string; the paper citation was confirmed against arXiv 2103.06268; the CC BY 4.0 URL returns 200.
  Files: `DATA_LICENSES.md`.
  Deviations: the GitHub repo has no LICENSE file, so the license page is the primary source; this is noted in the file. The statement is not legal advice.

#### 1.11 [x] Write the skill's Python-lane references
- **Do:** the skill names `references/python/{architecture,validation-and-config,tooling,testing,database,security}-rules.md`. Write the ones this phase needs (tooling, validation-and-config, architecture, testing) as short checklists derived from Design §9 and the skill's own inline rules. Do not invent rules the project does not use. Remaining files are written in the phase that first needs them.
- **Verify:** each file referenced from SKILL.md exists or is still marked not-yet-written.
- **Refs:** finding F-006.
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. Nothing to write: all nine files under `references/python/` and the three under `references/eval/` already exist (F-006 point 1 was stale when the plan was written). Checked that every `references/...` path in SKILL.md resolves (script, step 0.4) and that the tooling, validation, database and testing rules match what steps 1.2 to 1.6 built (uv, ruff and pyright settings, one Settings module, Alembic, no `create_all`).
  Evidence: path-existence script from 0.4 re-run: 13 of 13 present.
  Files: none.
  Deviations: the rules in the files were written before any code existed and have only been checked against steps 1.2 to 1.6. Later phases amend them when they find a mismatch; the Python-lane testing and architecture rules (import-linter, testcontainers) are untested until Phases 2 and 3.

#### 1.12 [ ] Phase exit check
- **Do:** clone the repo to a scratch directory (outside the project) and run `make up`, `make lint`, `make test`.
- **Verify:** all pass from the clean clone. Record the commands and outcome in the Done note.
