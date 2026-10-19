# Backend — Testing Rules

pytest, Hypothesis, testcontainers. The test pyramid here is `tests/{unit,property,integration}/`.

## TEST-CRITICAL-1 — Every metric and statistic has a known-answer test

Compute the expected value **by hand** (or from a published worked example) and assert it. Cover: empty input (no gold span, zero results), single item, ties, duplicates, and a case where the answer is easy to get subtly wrong (off-by-one on half-open spans, rank starting at 1 vs 0, k larger than the result count). A test that re-implements the function to get the expected value proves nothing.

## TEST-CRITICAL-2 — Property-test invariants with Hypothesis

Good targets: chunk offsets (`text[start:end] == chunk.text`, chunks cover/overlap as designed, no negative/inverted spans), RRF (permutation of equal inputs → stable result; ties; duplicates; adding a never-ranked doc doesn't change relative order), span overlap symmetry, bootstrap invariants (CI contains the point estimate for symmetric data; a zero-delta paired input gives a CI containing 0). Pin Hypothesis `derandomize`/seed in CI or store failing examples so failures reproduce.

## TEST-CRITICAL-3 — Test stats by simulation, not by hope

The gate's claims (nominal coverage, false-alarm rate, power) are testable properties: simulate data with a known true delta, run the procedure many times with seeded RNG, assert empirical coverage/false-alarm lands inside a stated tolerance. Keep a fast version in unit tests and the full study as a separate, documented command. See `eval/stats-rules.md`.

## TEST-HIGH-1 — Integration tests use real Postgres

Mocking `asyncpg` proves your mock works. Use testcontainers (pgvector image) for: migrations apply, FTS and dense queries return expected rows, idempotent ingestion, unique constraints, offset round-trips. One container per session; isolate tests with transactions or per-test schemas/databases, not shared mutable state.

Mock only things you don't own and can't run cheaply: the LLM provider and Langfuse. Even then, prefer a **fake with the real interface** (returns canned, schema-valid structured output, deterministic) over `unittest.mock` patching internals.

## TEST-HIGH-2 — Test the app through its interface

Build the app via the factory and call it with `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")` — no socket. Override dependencies with `app.dependency_overrides`. Assert on status, error `code`, and validated response model, not on log text. Run lifespan (use `asgi-lifespan` `LifespanManager` or the framework's test helper) when the test depends on pools/models.

## TEST-HIGH-3 — Async tests

Use `pytest-asyncio` (set `asyncio_mode = "auto"`) or `anyio`'s pytest plugin; pick one. Fixtures that hold event-loop-bound resources must share the loop scope. Never call `asyncio.run` inside a test. Treat un-awaited coroutine warnings as errors (`filterwarnings = ["error::RuntimeWarning"]`).

## TEST-HIGH-4 — Determinism and isolation

Tests don't touch the network, the real LLM, or the wall clock (inject a clock or freeze time). Seed RNGs. Use `tmp_path` for files and SQLite stores. No test depends on another's side effects or on execution order (consider `pytest-randomly`). Mark tests needing Docker (`@pytest.mark.integration`) so `pytest -m "not integration"` is fast.

## TEST-MEDIUM-1 — Regression discipline

A bug fix starts with a failing test that reproduces it. A change to a metric, chunker or prompt that alters stored numbers needs a test showing the intended difference, and an explicit note that old runs are not comparable (new version ID).

## TEST-MEDIUM-2 — What not to test

Don't test the framework (FastAPI routing, Pydantic basics) or pure pass-throughs. Don't assert exact LLM prose. Don't chase coverage numbers: cover branches that carry risk (error paths, empty inputs, boundary conditions). Keep test files near the 300-line target; name tests for behavior (`test_abstention_recall_is_nan_when_no_unanswerable_queries`).
