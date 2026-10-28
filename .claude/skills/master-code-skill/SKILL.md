---
name: master-code-skill
description: Use this skill for ANY coding task in the calibrated-RAG-evaluation-lab repo (Python package `ragcalibrate`) — writing, adapting, or reviewing code in the FastAPI RAG service, the eval harness CLI, ingestion/chunkers, the LLM client, the stats module, Alembic migrations, tests, or CI. Combines four layers: (1) Karpathy's anti-overcomplication mindset (think before coding, simplicity first, surgical changes, goal-driven execution), (2) cross-cutting rules for validation (Pydantic only at trust boundaries), dependencies (uv, lockfile, nothing unused) and verification with the real toolchain, (3) a Python backend playbook (layering, async, error handling, security, observability, Postgres/SQLite, testing), and (4) an eval-integrity lane covering what makes this project credible: span-level gold labels that never leak to the system under test, paired document-clustered bootstrap, judge calibration, LLM cache and determinism. Trigger on requests like "add an endpoint", "add a metric", "write a chunker", "change the retriever", "add a judge prompt", "write a migration", "review this PR", "add a test", "add a dependency", "compare two runs", "why is the gate flaky", or any change touching .py, .sql, pyproject.toml, docker-compose.yml, or CI files in this repo. Trigger even for small or one-line edits; the Karpathy mindset and surgical-change rules apply universally.
---

# Master Code Skill — Calibrated RAG Evaluation Lab

A single entry point for all coding work in this repo. Layers:

1. **Karpathy mindset** — applies to *every* change, no exceptions.
2. **Cross-cutting rules** — validation, dependencies, verification.
3. **Routing** — decide which lane you're in.
4. **Mode** — Write / Adapt / Review.
5. **Lane rules** — load the relevant reference file(s) once you know what you're touching.

Keep this file lean. Detailed rules live in `references/`.

> **Provenance**: adapted from the `master-code-skill` in `pivotia-app` (TypeScript monorepo) and `Legalware-app` (Firebase + React). Karpathy layer kept as is; frontend, mobile and i18n lanes dropped (no UI here); backend rules rewritten for Python; eval-integrity lane added. **State (2026-10-28, Phase 3 in progress; current status in `docs/project-plan.md`)**: settings (`config.py`, with `load_settings()` as the only place `Settings` is built), JSON logging (`logs.py`), Alembic migrations, `corpora/`, `ingest/`, `service/` (`/retrieve` with Postgres FTS, dense search and their RRF fusion), the wire models in `ragcalibrate/contract.py`, and `harness/` (retrieval metrics, HTTP adapter, minimal `run`) have code; `llm/`, `stats/` and `report/` are empty placeholders. The layout below comes from `docs/design/project-design.md` §13. If the real tree differs, trust the tree and update this file. Project conventions already settled: ruff line length 100 with Markdown excluded from `ruff format`, pyright strict on `src/`, Python 3.12, Postgres on 127.0.0.1:5433 via Compose.

---

## Repo shape (planned, per `docs/design/project-design.md`)

```
calibrated-RAG-evaluation-lab/
├── src/ragcalibrate/
│   ├── contract.py wire models for /retrieve and /answer: the only module harness and service share
│   ├── corpora/    CUAD / QASPER adapters → documents, queries, gold spans
│   ├── ingest/     versioned chunkers, embedding, bulk load into Postgres
│   ├── service/    FastAPI app (system under test): /retrieve /answer /healthz /readyz
│   ├── llm/        provider interface, content-addressed cache, cost, tracing
│   ├── harness/    runner, SUT adapters (HTTP), metrics, judge, SQLite run store, CLI
│   ├── stats/      bootstrap, kappa, gate decision — PURE functions, no I/O
│   └── report/     Markdown/HTML reports, PR comment rendering
├── migrations/     Alembic (Postgres corpus store only)
├── evalsets/       versioned, hashed queries + gold spans
├── configs/        experiment YAMLs (hash = experiment identity)
├── action/         reusable GitHub Action
├── tests/{unit,property,integration}/
└── pyproject.toml  uv.lock  docker-compose.yml  Makefile
```

**Two databases on purpose** (Design §5.8): Postgres = corpus index (part of the system under test); SQLite = run results (the measuring instrument). The LLM cache is a third, separate SQLite file. Don't merge them.

**Dependency direction is one-way**: `stats` and `report` depend on nothing in `ragcalibrate` that does I/O. `harness` talks to the SUT only over HTTP. `service` never imports `harness` or reads `evalsets/`. import-linter enforces that `harness` and `service` never import each other (`make lint`); the wire models they both need live in `ragcalibrate/contract.py`. See `references/python/architecture-rules.md`.

---

## Layer 1 — Karpathy Mindset (applies to every task)

Full reference: [references/karpathy-mindset.md](references/karpathy-mindset.md).

### 1. Think before coding
- State assumptions explicitly. If uncertain, ask — don't guess silently.
- If multiple interpretations exist, name them.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity first
- Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked. No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested. No plugin systems, no frameworks around the LLM client (plan: "No framework").
- No error handling for impossible scenarios.
- Senior-engineer test: "Would they call this overcomplicated?" If yes, simplify.

### 3. Surgical changes
- Touch only what you must. Clean up only your own mess.
- Don't refactor adjacent code that isn't broken.
- Match existing style even if you'd do it differently.
- Notice unrelated dead code → mention it, don't delete it.
- Every changed line should trace to the user's request.

### 4. Goal-driven execution
- Transform tasks into verifiable goals: "Add a metric" → "Write a test with a hand-computed expected value, then make it pass."
- For multi-step tasks, state a brief plan with a verify check per step.
- In this repo the verify step is concrete: `uv run ruff check . && uv run ruff format --check .`, `uv run pyright`, `uv run pytest tests/unit`, `uv run pytest tests/integration` (needs Docker), `uv run alembic upgrade head` on a scratch DB.

**Tradeoff**: these guidelines bias toward caution over speed. For trivial single-line edits, use judgment.

---

## Layer 2 — Cross-cutting rules

### Validation — Pydantic belongs at trust boundaries
Full details: [references/python/validation-and-config-rules.md](references/python/validation-and-config-rules.md).

**XC-CRITICAL-1 — Validate at trust boundaries, and nowhere else.** The boundaries: HTTP request/response bodies, environment/config, LLM structured output, files read from disk (eval sets, experiment YAML, run manifests), and rows read back from SQLite/Postgres when the schema could have drifted. Between functions you own, type hints plus pyright are the proof; Pydantic there is overhead.

**XC-CRITICAL-2 — A cast is a claim; a parse is a check.** `cast(...)`, `# type: ignore` and bare `dict` access on external data assert to the checker and do nothing at runtime. At a boundary, use `Model.model_validate(...)`.

**XC-CRITICAL-3 — One definition per wire shape.** The `/retrieve` and `/answer` models live in one module imported by both `service` and `harness`' HTTP adapter. Never redeclare one locally; two copies will drift and the harness will silently mis-score.

### Dependencies — keep weight down
Full details: [references/python/tooling-rules.md](references/python/tooling-rules.md).

**XC-CRITICAL-4 — Don't add a dependency until something imports it.** If you can't name the importing file in this change, don't add it.

**XC-CRITICAL-5 — Prefer the stdlib or what's already installed.** Check before adding a wrapper. (`statistics`, `hashlib`, `sqlite3`, `asyncio`, `numpy` already cover most of `stats/`.)

**XC-CRITICAL-6 — Verify with the real toolchain, not by reading.** Pyright passing is not evidence the SQL is valid or the migration applies. Match the check to the claim: a query change needs a run against real Postgres; a stats change needs a known-answer test.

**XC-HIGH-1 — Comment load-bearing oddities.** A deliberate decision that looks like a mistake will be "fixed" by the next reader (e.g. exact search instead of an HNSW index, `simple` vs `english` FTS config, cache bypassed in A/A runs). Write the *why*.

---

## Layer 3 — Routing

| If the file lives in… | Lane | Primary references |
|---|---|---|
| `src/ragcalibrate/service/`, `ingest/`, `corpora/`, `migrations/` | **Backend** | `references/python/*.md` |
| `src/ragcalibrate/llm/` | **Backend + Eval** | `python/reliability-rules.md`, `eval/llm-rules.md` |
| `src/ragcalibrate/harness/`, `stats/`, `report/`, `evalsets/`, `configs/`, `action/` | **Eval integrity** | `references/eval/*.md` (start with `eval-integrity-rules.md`) |
| `tests/` | **Testing** | `python/testing-rules.md` (+ `eval/stats-rules.md` for stats tests) |
| `pyproject.toml`, `docker-compose.yml`, `Makefile`, `.github/`, `action/` | **Tooling** | `python/tooling-rules.md` |

The eval lane is **additive**: harness code is also Python backend code, so async, error and security rules still apply.

---

## Layer 4 — Mode (Write / Adapt / Review)

| Task | Mode |
|---|---|
| New module, endpoint, metric, or feature from scratch | **Write** |
| Adding to or modifying existing code | **Adapt** |
| Auditing a PR, doing cleanup, or improving existing code | **Review** |

When uncertain, default to **Review** first to understand the existing code, then **Adapt**.

### Write mode
- Plan data flow first. If the change crosses the HTTP boundary, **define the Pydantic model first**, then the route and the harness adapter follow from it.
- If it's a metric or a statistic, write the known-answer test first (hand-computed value), then the function.
- Apply CRITICAL rules from the lane's references as you write, then HIGH, then MEDIUM.
- Run the Quick Wins Checklist before finishing.

### Adapt mode
- Read the file in full before touching it. Understand existing patterns.
- Match surrounding conventions. Only refactor when a CRITICAL rule is violated.
- New code passes the same checklist as Write mode.

### Review mode
- Run the Quick Wins Checklist top-to-bottom.
- Flag every CRITICAL violation as blocking; suggest fixes for HIGH; note MEDIUM/LOW as follow-ups.
- Cite rule IDs (`SEC-CRITICAL-1`, `EVAL-CRITICAL-3`) so the author can look them up.

---

## Backend lane — Critical rules inline

Full details in `references/python/`.

### BE-CRITICAL-1 — All env access goes through one `pydantic-settings` module
```python
# NEVER — unvalidated, scattered, silently None
port = os.environ.get("PORT")

# ALWAYS — ragcalibrate/config.py, one Settings class, validated at startup
settings = Settings()   # fails at boot with a readable error
```
`grep -rn "os.environ\|os.getenv" src/` outside `config.py` should return nothing. Experiment parameters are *not* env: they live in versioned YAML whose hash identifies the run.

### BE-CRITICAL-2 — Never block the event loop; bound every outbound call
FastAPI handlers and the harness runner are async. A blocking call (sync `requests`, `time.sleep`, CPU-bound embedding/rerank inference, sync DB driver) inside `async def` stalls every concurrent request. Run CPU/blocking work with `asyncio.to_thread` or a process pool, and give every network call an explicit timeout and bounded concurrency (`asyncio.Semaphore`). See `python/reliability-rules.md`.

### BE-CRITICAL-3 — Create pools and clients once, in the app lifespan
DB pools, `httpx.AsyncClient`, the embedding model and the reranker are loaded once in the FastAPI `lifespan` (or the harness entrypoint) and injected. Constructing them per request exhausts connections or reloads a model on every call.

### BE-CRITICAL-4 — Raise typed errors; never build error responses by hand
Raise a domain exception (`RagError` subclasses); one registered exception handler turns it into the response. Never `except Exception: pass`. Never swallow `asyncio.CancelledError`. See `python/async-error-rules.md`.

### BE-CRITICAL-5 — Parameterize SQL; never log secrets
Every query uses bound parameters — never f-strings or `%` into SQL, including `ORDER BY` and table names (allow-list those). Use stdlib `logging` with `extra={...}` fields, not `print`. Never log API keys, prompts containing user documents at INFO, or full LLM responses. See `python/security-rules.md`, `python/observability-rules.md`.

---

## Eval-integrity lane — Critical rules inline

This is what the project *is*. Full details in `references/eval/`. A bug here doesn't crash; it produces a plausible, wrong number.

### EVAL-CRITICAL-1 — Gold labels never reach the system under test
Queries and gold spans live in `evalsets/` (versioned, hashed). The Postgres corpus holds documents and chunks only. `service/` must not import from `harness/` or read `evalsets/`; the harness sends queries over HTTP and nothing else. If a field named `gold`, `answerable` or `expected` appears in a request body or a service table, that is a leak.

### EVAL-CRITICAL-2 — Retrieval relevance is span overlap, not chunk ID
A chunk is relevant if its `[start_char, end_char)` overlaps a gold span in the same document. Offsets are half-open character offsets into the original document text and must satisfy `text[start:end] == chunk.text` (property-tested). Metrics on answerable queries only; unanswerable queries get abstention precision/recall.

### EVAL-CRITICAL-3 — Compare runs with a paired, document-clustered bootstrap
Join per-query metrics on `query_id`, resample **documents** (clusters), not queries, and report the delta with a CI. Never gate on a point-estimate difference. `stats/` is pure functions with a seeded RNG, so every result is reproducible and exhaustively testable.

### EVAL-CRITICAL-4 — Every number is regenerable from a manifest
A run records git SHA, dirty flag, config hash, evalset hash, model IDs, judge prompt hash. Config and prompt changes change a hash. Results are append-only; never edit a stored run. A figure in a report or README must come from one command.

### EVAL-CRITICAL-5 — The cache must not hide noise
The content-addressed LLM cache key includes provider, model snapshot, params, prompt hash and rendered input; modes are `read-write`, `read-only`, `off`. A/A run-to-run studies run with the cache mode `off`; otherwise the false-alarm rate is 0% by construction and proves nothing. See `eval/llm-rules.md`.

---

## Quick Wins Checklist

Run before finishing any task. `[!]` blocking, `[~]` must justify, `[ ]` informational.

### Always (Karpathy)
- `[!]` Every changed line traces to the user's request — no scope creep, no adjacent refactors.
- `[!]` No speculative abstractions, configurability, or error handling for impossible scenarios.
- `[~]` Assumptions were stated up front if the task was ambiguous.
- `[ ]` Success criteria are verifiable (a passing test, a type check, a migration applying cleanly).

### Always (types & contracts)
- `[!]` `uv run pyright` passes (strict on `src/`).
- `[!]` No `Any` leaking from a boundary; no unjustified `# type: ignore` or `cast`.
- `[!]` Pydantic appears only at a trust boundary — not on every internal call.
- `[!]` HTTP wire shapes are imported from the single shared models module, not redeclared.
- `[~]` Public functions have type hints; mutable default arguments are absent.

### Backend (only if you touched `service/`, `ingest/`, `llm/`, `harness/`)
- `[!]` No `os.environ` outside `config.py`; new settings are in the schema and `.env.example`.
- `[!]` No blocking call inside `async def`; every outbound call has a timeout.
- `[!]` SQL is parameterized; no secret, key or prompt-with-document is logged.
- `[!]` Pools/clients created in lifespan, not per request.
- `[~]` Ingestion and any retryable endpoint is idempotent (same input twice = same state).
- `[~]` Schema change has an Alembic migration (never `create_all` at startup) and was applied on a real Postgres.

### Eval integrity (only if you touched `harness/`, `stats/`, `report/`, `evalsets/`, `configs/`)
- `[!]` No gold label, query category, or `answerable` flag reaches the service or its DB.
- `[!]` New metric has a hand-computed known-answer test and handles empty input (no gold span, no results).
- `[!]` Comparisons are paired by `query_id` and clustered by document; randomness is seeded and the seed is recorded.
- `[!]` Hashes (evalset, config, judge prompt) are part of the run manifest and the cache key where relevant.
- `[~]` Any statistic reported has its CI/denominator `n`; any κ states its label source (derived / perturbation / human).
- `[~]` "BM25" is not used to name Postgres FTS.
- `[ ]` Report numbers regenerate from one command.

### Always (toolchain hygiene)
- `[~]` `uv run ruff check .` and `ruff format --check .` pass.
- `[~]` Relevant tests pass; new behavior has new tests; integration tests used real Postgres, not mocks of it.
- `[!]` No secrets committed (gitleaks/pre-commit); `uv.lock` updated if dependencies changed.
- `[ ]` Anything non-obvious a reader might "fix" has a comment explaining why not (and, for big decisions, an ADR in `docs/adr/`).

---

## Reference Map

### Cross-cutting
| File | Read when |
|---|---|
| [references/karpathy-mindset.md](references/karpathy-mindset.md) | Before any non-trivial change. It's short — re-read it. |
| [references/python/validation-and-config-rules.md](references/python/validation-and-config-rules.md) | Adding a model, touching an API/LLM/file boundary, adding a setting |
| [references/python/tooling-rules.md](references/python/tooling-rules.md) | Adding/removing a dependency, editing pyproject/CI/Docker/Makefile, before claiming a change works |

### Backend (`src/ragcalibrate/service`, `ingest`, `corpora`, `llm`, `migrations`)
| File | Priority focus | Read when |
|---|---|---|
| [architecture-rules.md](references/python/architecture-rules.md) | Layering, module boundaries, DI, file size | Adding routes/modules, refactoring |
| [security-rules.md](references/python/security-rules.md) | Secrets, SQL injection, SSRF, deps, untrusted LLM output | Config, endpoints, SQL, outbound HTTP |
| [reliability-rules.md](references/python/reliability-rules.md) | Timeouts, retries, concurrency, idempotency, shutdown | External calls, runner, ingestion |
| [async-error-rules.md](references/python/async-error-rules.md) | asyncio pitfalls, error hierarchy | Any async code, custom exceptions |
| [observability-rules.md](references/python/observability-rules.md) | Structured logs, Langfuse spans, cost/latency | Logging, tracing, run metadata |
| [database-rules.md](references/python/database-rules.md) | Postgres/pgvector/FTS, SQLite run store, Alembic | Any SQL, schema, index, migration |
| [testing-rules.md](references/python/testing-rules.md) | pytest, testcontainers, Hypothesis, async tests | Adding or changing tests |

### Eval integrity (`harness`, `stats`, `report`, `evalsets`, `configs`)
| File | Priority focus | Read when |
|---|---|---|
| [eval-integrity-rules.md](references/eval/eval-integrity-rules.md) | Leakage, ground truth, metrics, manifests, abstention | **First read in this lane**; any metric or eval-set change |
| [stats-rules.md](references/eval/stats-rules.md) | Clustered bootstrap, κ, gate rule, power/false-alarm studies | Anything in `stats/`, gate or compare code |
| [llm-rules.md](references/eval/llm-rules.md) | Cache, determinism, judge prompts, structured output, cost | `llm/`, judge, generator, prompts |

> **Source attributions**: Karpathy mindset adapted from [Andrej Karpathy's observations on LLM coding pitfalls](https://x.com/karpathy/status/2015883857489522876). Layering/validation/dependency philosophy carried over from the sibling `pivotia-app` skill. Eval and LLM rules grounded in `docs/design/project-design.md` and `docs/llm-production-best-practices.md`. Python rules follow common FastAPI/asyncio/OWASP guidance; verify version-specific behavior against current docs before relying on it.
