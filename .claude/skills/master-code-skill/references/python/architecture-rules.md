# Backend — Architecture Rules

Layering, module boundaries, DI and file structure for `src/ragcalibrate/`.

## File Organization

| Artifact | Soft limit | Hard limit | When to split |
|---|---:|---:|---|
| `service/app.py` (app factory, middleware, router mounts) | 80 lines | 150 lines | Move handlers into `service/routes/` |
| Route module | 150 lines | 250 lines | Extract logic to a service/strategy module |
| Strategy / domain module | 200 lines | 350 lines | Split by domain concept (one retrieval strategy per module), not by technical layer |
| Single function | 40 lines | 75 lines | Extract helpers; one reason to change |
| Test file | 300 lines | 500 lines | Mirror the module under test; one test class or section per public function |

Suggested shape inside `service/` (adjust to the real tree):

```
service/
├── app.py          create_app(): lifespan, middleware, exception handlers, include_router. No handler bodies.
├── deps.py         FastAPI dependencies (db pool, models, settings) — the DI seam
├── routes/         Thin: validate (Pydantic), call one function, shape the response
├── retrieval/      strategies (fts, dense, rrf, rerank) — plain async functions/classes, no FastAPI imports
└── answering/      prompt building, generator call, citation mapping
```

The wire models shared with the harness adapter (single definition) live outside `service/`, in `ragcalibrate/contract.py`: the import-linter contract forbids `harness` from importing anything in `service`.

## ARCH-CRITICAL-1 — `app.py` is a manifest, not a monolith

`create_app()` builds the app, registers the lifespan, middleware, exception handlers and routers. No handler bodies. A factory lets tests build an app with fakes and call it through `httpx.ASGITransport` with no socket.

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_exception_handler(RagError, rag_error_handler)
    app.include_router(health.router)
    app.include_router(retrieve.router)
    app.include_router(answer.router)
    return app
```

## ARCH-CRITICAL-2 — Route → logic → data, and logic imports no framework

- **Route**: parses the Pydantic request, calls one function, returns the response model. No SQL, no business logic.
- **Logic** (`retrieval/`, `answering/`, `stats/`, metrics): plain functions over plain data. **Imports no FastAPI, no `httpx.Request`.** Receives the pool/client/model as parameters.
- **Data access**: SQL lives in one place per store (a `repo` module or a small class). Not scattered through route files.

A strategy that imports `fastapi` cannot be unit-tested without faking a request, and cannot be reused by the harness or an offline script.

## ARCH-CRITICAL-3 — Module dependency direction is enforced

```
stats, report  ──▶  (nothing that does I/O)
harness        ──▶  llm, stats, report, HTTP only to the SUT
service        ──▶  llm, ingest-shared models, db      (NEVER harness, NEVER evalsets)
ingest         ──▶  corpora, db
corpora        ──▶  (files, network for download + checksum)
```

`service` importing `harness` (or reading `evalsets/`) breaks the no-leakage guarantee (`EVAL-CRITICAL-1`). If you need a shared type, put it in a neutral `models` module both sides import. Enforce with `import-linter` or a simple test that greps imports once the tree exists.

## ARCH-HIGH-1 — Dependency injection via FastAPI `Depends` and function parameters, not globals

```python
# NEVER — hidden global, untestable, import-time side effects
pool = asyncpg.create_pool(DSN)

# ALWAYS — created in lifespan, stored on app.state, handed out by a dependency
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pool(settings.database_url)
    app.state.embedder = load_embedder(settings.embed_model)   # load once
    yield
    await app.state.pool.close()
```

No work at import time (no network, no DB, no model load). `import ragcalibrate.service` must be cheap and side-effect free.

## ARCH-HIGH-2 — Pure core, thin shell

Put decisions in pure functions (`stats/`, metric computation, RRF, chunk offset math, gate rule) and I/O at the edges (runner, store, CLI). Pure code is where Hypothesis and known-answer tests pay off; mixed code needs mocks.

## ARCH-HIGH-3 — Versioned things carry an ID

Chunkers, retrieval strategies, judge prompts and eval sets each have a stable ID/version (`chunker_id`, prompt hash, evalset hash). Behavior changes mean a new version, not an in-place edit; old runs must still be explainable.

## ARCH-MEDIUM-1 — Naming and style

- Package/module/function: `snake_case`; classes: `PascalCase`; constants: `UPPER_SNAKE`.
- No `utils.py` / `helpers.py` dumping grounds; name the module for what it does (`offsets.py`, `rrf.py`).
- Absolute imports from `ragcalibrate.*`; no wildcard imports; no circular imports (a cycle means a boundary is wrong).
- Prefer `dataclass(frozen=True, slots=True)` for internal value objects, Pydantic for boundaries (see `validation-and-config-rules.md`).
- `pathlib.Path`, not string paths; `datetime` always timezone-aware UTC.
