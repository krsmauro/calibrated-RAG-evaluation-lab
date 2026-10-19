# Phase 1: Eval spec and repo skeleton (Design Week 1)

**Goal:** write down every decision that would otherwise produce an indefensible number, and get a repo where `make up` works from a clean clone.
**Entry:** Phase 0 done, or at least D5 (package name, answered) in the plan.
**Exit criterion:** `make up` works from a clean clone; CI green on the empty app; `docs/eval-spec.md` written; first ADRs written.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 1.1 [ ] Read the prior art and verify the comparison table
- **Do:** read ARES (Saad-Falcon et al., 2023), LegalBench-RAG (Pipitone and Alami, 2024) and the current Ragas, DeepEval, promptfoo and TruLens docs. For each row of the prior-art table, mark it verified or corrected, with the date checked.
- **Verify:** a finding (`docs/findings/`) lists, per tool, what was checked and what changed. Anything that changes the differentiator in Design §3 is flagged to the user.
- **Refs:** Design §3, §8.4 (PPI).

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
#### 1.3 [ ] Docker Compose with Postgres and pgvector
- **Do:** `docker-compose.yml` with a pgvector-enabled Postgres, image pinned to an explicit tag (not `latest`), a healthcheck, a named volume. Makefile targets: `up`, `down`, `test`, `lint`. `.env.example` lists every setting.
- **Verify:** `make up` then `psql -c "select extversion from pg_extension where extname='vector'"` after step 1.4 returns a version. Record the pgvector version in the manifest notes.
- **Refs:** Design §9, §6 (data model).

#### 1.4 [ ] Settings module and Alembic baseline
- **Do:** one `pydantic-settings` class in `ragcalibrate/config.py` (no other `os.environ` use). Alembic initialised; first migration creates the `vector` extension, `documents` and `chunks` per Design §6 data model (no `tsv` or HNSW index yet; those arrive in Phases 2 and 3 with the evidence behind them). No `create_all` anywhere.
- **Verify:** `uv run alembic upgrade head` on an empty database succeeds, then `downgrade base` then `upgrade head` again. `grep -rn "os.environ\|os.getenv" src/` returns only `config.py`.
- **Refs:** skill BE-CRITICAL-1; Design §9 (Database).

#### 1.5 [ ] CI workflow
- **Do:** GitHub Actions workflow running lint, pyright and unit tests on every PR, with a Postgres service for integration tests later. Least-privilege `permissions:`. Never `pull_request_target`.
- **Verify:** workflow file passes `actionlint` if available; first run is green on the empty app. (Needs the user to push; the agent cannot. Mark `[!]` blocked-on-user until the user confirms the run is green.)
- **Refs:** Design §8.5 (fork PRs), §9.

#### 1.6 [ ] Structured logging skeleton
- **Do:** JSON logs with `run_id` and `query_id` fields available via contextvars. No `print`.
- **Verify:** a unit test captures one log line and asserts the fields.
- **Refs:** Design §9 (Logging).

#### 1.7 [ ] Measure the CUAD facts the spec depends on
- **Do:** download CUAD with a checksum (script lives in `scripts/`, no new dependency beyond what step 1.2 installed unless justified). Compute and record: number of contracts and categories; total pairs (510 x 41 = 20,910 claimed); share of pairs with no gold span (Design §5.4 says "more than a third"); number of gold spans per answerable pair (distribution); number of test rows and test contracts (Design §8.1 says 4,182 and 102, "confirm on load"); whether `text[answer_start:answer_start+len(answer)] == answer` holds for every label; contract length distribution in characters and tokens; the license text on the source page.
- **Verify:** one finding, `F-0NN-cuad-facts.md`, with the numbers, the command that produced them and the dataset checksum. Any number that differs from the Design is called out.
- **Refs:** Design §5.3, §5.4, §8.1, §10.

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

#### 1.9 [ ] First ADRs
- **Do:** write ADR 0001 (Postgres with pgvector), 0003 (separate SQLite run store), 0005 (gold labels live in the harness), 0009 (FTS is not BM25) at `docs/adr/`. Use `docs/adr/_template.md`. Short.
- **Verify:** each has context, decision, alternatives, consequences; the plan's ADR index is updated.
- **Refs:** Design §12.

#### 1.10 [ ] `DATA_LICENSES.md`
- **Do:** skeleton listing CUAD (CC BY 4.0, credit The Atticus Project, link the license) and the repo's own MIT code license. QASPER is added in Phase 9 after its license is checked against the primary source.
- **Verify:** the file exists; the CUAD license was checked against the dataset's own page, not from memory.
- **Refs:** Design §10.

#### 1.11 [ ] Write the skill's Python-lane references
- **Do:** the skill names `references/python/{architecture,validation-and-config,tooling,testing,database,security}-rules.md`. Write the ones this phase needs (tooling, validation-and-config, architecture, testing) as short checklists derived from Design §9 and the skill's own inline rules. Do not invent rules the project does not use. Remaining files are written in the phase that first needs them.
- **Verify:** each file referenced from SKILL.md exists or is still marked not-yet-written.
- **Refs:** finding F-006.

#### 1.12 [ ] Phase exit check
- **Do:** clone the repo to a scratch directory (outside the project) and run `make up`, `make lint`, `make test`.
- **Verify:** all pass from the clean clone. Record the commands and outcome in the Done note.
