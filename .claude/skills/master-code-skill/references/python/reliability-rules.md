# Backend — Reliability Rules

Timeouts, retries, concurrency, idempotency and shutdown for the service, the ingester and the harness runner.

## REL-CRITICAL-1 — Every outbound call has a timeout

LLM providers, the SUT, dataset downloads, DB acquisition. No timeout = a hung run that CI kills after hours.

```python
client = httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout_s, connect=5.0))
async with asyncio.timeout(settings.query_budget_s):   # Python 3.11+
    result = await run_one_query(q)
```

Set a per-call timeout *and* a per-query/overall budget. Pool acquisition has a timeout too, so an exhausted pool fails fast instead of queueing forever.

## REL-CRITICAL-2 — Bound concurrency (the limit belongs to the fleet)

Provider rate limits and DB connections are shared budgets. The runner uses a bounded semaphore (or `asyncio.TaskGroup` with a worker pool), sized for **all** workers together, not per task.

```python
sem = asyncio.Semaphore(settings.max_concurrency)
async def bounded(q):
    async with sem:
        return await run_one_query(q)
```

Never `asyncio.gather(*[... for q in 50_000_queries])` unbounded. Pool size ≥ concurrency, or acquisition becomes the bottleneck.

## REL-CRITICAL-3 — Retry only what is safe to retry, with backoff and jitter

- Retry: timeouts, connection errors, 429, 5xx. Do **not** retry 4xx (other than 429), validation failures, or non-idempotent writes without an idempotency key.
- Exponential backoff with full jitter and a max attempts/total time. Honor `Retry-After`.
- Retries and the cache interact: a cache hit must short-circuit before the retry loop; record retry counts in the run so cost/latency stay honest.
- Distinguish "provider failed" from "model answered badly" in the stored result; don't silently turn failures into zeros that bias a metric (store the failure, and report the exclusion or count it explicitly).

## REL-CRITICAL-4 — Idempotency: the same input twice has the same effect as once

- **Ingestion** is keyed on the document content hash (`sha256`); re-ingesting is a no-op. Use `INSERT ... ON CONFLICT DO NOTHING/UPDATE` with a unique constraint, not check-then-insert.
- **Runs** are resumable: a restarted run skips (run_id, query_id) pairs already stored. Writes for a query are atomic (one transaction), so a crash leaves no half-written query.
- Bulk loads (`COPY`) happen inside a transaction and are safe to re-run after rollback.
- Verifiable goal: a test that runs the operation twice and asserts identical final state.

## REL-HIGH-1 — Don't block the event loop

CPU-bound work (embedding batches, cross-encoder rerank, bootstrap resampling with 10k+ iterations) must not run on the loop.

- Wrap in `await asyncio.to_thread(fn, ...)` for short blocking calls; use a `ProcessPoolExecutor` for heavy CPU (GIL).
- Vectorize numeric work with `numpy`; no Python loops over 10k bootstrap resamples in the hot path.
- Sync libraries (`sqlite3`, `psycopg` sync, `requests`) inside `async def` are bugs. Use async drivers or `to_thread`.
- Detect with `asyncio` debug mode in tests (`PYTHONASYNCIODEBUG=1`) which warns on slow callbacks.

## REL-HIGH-2 — Health vs readiness; graceful shutdown

- `GET /healthz`: process is up (no dependencies). `GET /readyz`: DB reachable, model loaded, migrations at head.
- Shutdown happens in `lifespan` teardown: stop accepting work, let in-flight requests finish within a deadline, close pools/clients. Handle `SIGTERM` in the harness: flush results for finished queries, mark the run as interrupted, exit non-zero.
- Don't swallow `asyncio.CancelledError` (see `async-error-rules.md`).

## REL-HIGH-3 — Fail loud, partially complete safely

A run that finished 9,800 of 10,000 queries must say so in its manifest and report (`n_attempted`, `n_failed`, failure reasons), and the gate must refuse to decide (or flag) when the failed fraction exceeds a stated threshold. Never compute a metric over "whatever succeeded" without stating the denominator.

## REL-MEDIUM-1 — Determinism where you can have it

Seed every RNG (`random`, `numpy.random.default_rng(seed)`), record seeds in the manifest, avoid iterating `set`s/unordered dicts where order affects results, sort DB results explicitly (`ORDER BY` with a tiebreaker such as `id`). Retrieval ties broken by a stable key, otherwise rank metrics flicker between runs.
