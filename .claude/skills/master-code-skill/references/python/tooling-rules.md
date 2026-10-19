# Cross-cutting — Tooling & Dependency Rules

uv, ruff, pyright, pre-commit, Docker Compose, GitHub Actions. Planned in `docs/design/project-design.md` §9–§10; adjust if the repo diverges.

## DEP-CRITICAL-1 — Don't add a dependency until something imports it

Adding a package "because we'll need it" is the dependency form of a speculative abstraction. Before adding: **which file imports this, in this change?** No answer, no dependency. Heavy ML dependencies (torch, sentence-transformers) are real costs: image size, CI time, install failures; confirm they're needed by the code you're writing now.

## DEP-CRITICAL-2 — Prefer stdlib / already-installed over a new package

`statistics`, `hashlib`, `json`, `sqlite3`, `asyncio`, `pathlib`, `argparse`/`typer` (already chosen?) before adding another. The plan says **no LLM framework** (no LangChain/LlamaIndex): the thin provider interface is the point. Don't add an eval library (Ragas, DeepEval) as a dependency of the harness; they're comparison targets, not building blocks.

## DEP-CRITICAL-3 — uv with a committed lockfile; reproducible installs

- `pyproject.toml` declares ranges; `uv.lock` is committed and CI uses `uv sync --frozen`.
- Dev/test/optional extras are separated (dependency groups) so the harness can be installed without the service's ML stack, and vice versa.
- Pin the Python version (`requires-python`, `.python-version`). Use features (e.g. `asyncio.TaskGroup`, `asyncio.timeout`) consistent with it.
- Verify versions from the source of truth (`uv pip show`, `uv tree`, the package's changelog/PyPI), not memory. Check peer/transitive conflicts by actually running `uv sync` and the tests.

## DEP-CRITICAL-4 — Verify with the real toolchain, not by reading

| Claim | Real check |
|---|---|
| "Types are fine" | `uv run pyright` |
| "Style is fine" | `uv run ruff check .` and `uv run ruff format --check .` |
| "Logic works" | `uv run pytest tests/unit tests/property` |
| "SQL/migration works" | integration tests on real Postgres + `alembic upgrade head` on empty DB |
| "Stack starts" | `docker compose up` / `make up`, then `curl /readyz` |
| "Action works" | run it on a real PR / fork, not just locally |
| "Number is right" | known-answer test or independent calculation |

Every genuine incompatibility is found by running something. "Looks right" is not evidence.

## DEP-HIGH-1 — Prereleases and unpinned model downloads

No `rc`/`alpha`/`dev` packages in the main dependency set without a comment and an issue to remove. Embedding/reranker models are downloaded by name: pin model ID **and revision/commit**; a silently updated model changes every retrieval result.

## DEP-HIGH-2 — ruff + pyright configuration

- ruff: lint + format. Enable at least `E,F,I,B,UP,ASYNC,S,T20,RUF` (async misuse, bandit-style security, no `print`); justify per-file ignores in the config with a comment.
- pyright (or mypy) **strict** on `src/`; looser on `tests/`. Don't blanket-disable rules; fix or locally ignore with a reason.
- pre-commit runs ruff, format check, gitleaks, and trailing-whitespace/EOF checks. CI runs the same checks (don't rely on contributors having hooks installed).

## DEP-HIGH-3 — CI shape

- Jobs: lint+format, type check, unit+property tests, integration tests (Docker service/testcontainers), and (when it exists) the eval gate. Cache the uv cache, not the venv.
- Least-privilege `permissions:`; pin third-party actions by SHA; secrets unavailable to fork PRs (see `SEC-CRITICAL-1`).
- A gate that posts a PR comment must update one sticky comment, not add a new one per push, and set the exit code explicitly.
- Compose services have health checks and `depends_on: condition: service_healthy`; the Makefile targets (`up`, `data`, `ingest`, `eval`) are the documented entry points: keep README commands in sync with them.

## DEP-MEDIUM-1 — Comment load-bearing oddities

A deliberate decision that looks like a mistake will be reverted. Write the *why*, not the *what*: why exact search not HNSW, why a separate SQLite file, why the cache is bypassed in A/A runs, why this model revision is pinned. Big decisions get a short ADR in `docs/adr/` at the moment they're made (context, decision, alternatives, consequences), not after the fact.

## DEP-MEDIUM-2 — Name hygiene

`ragcalibrate` is the package name (decision D5, 2026-10-19; free on PyPI, npm and GitHub when chosen). Still keep it in one `pyproject` field and the `src/` directory, and use package-relative imports where reasonable, so a later rename stays cheap.
