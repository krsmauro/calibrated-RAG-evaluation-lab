# Backend — Async & Error Rules

asyncio pitfalls and the error hierarchy.

## ERR-CRITICAL-1 — Never swallow errors, never catch bare `Exception` and move on

```python
# NEVER
try:
    result = await call_llm(prompt)
except Exception:
    pass

# ALWAYS — catch the specific failure, handle or re-raise, record it
try:
    result = await call_llm(prompt)
except LLMTimeout as exc:
    raise RetrievalFailed("llm timeout", query_id=qid) from exc
```

- Use `raise ... from exc` to keep the cause chain.
- A broad `except Exception` is allowed only at a true top boundary (CLI entrypoint, task wrapper, HTTP exception handler) that logs with traceback and converts to a defined outcome.
- Never `except:` (bare); it catches `KeyboardInterrupt`/`SystemExit`.

## ERR-CRITICAL-2 — Never swallow `asyncio.CancelledError`

`CancelledError` derives from `BaseException`. If you catch it (or use bare `except`), cancellation and timeouts (`asyncio.timeout`, task groups) stop working. Clean up in `finally`, then let it propagate.

```python
try:
    await work()
except asyncio.CancelledError:
    await cleanup()
    raise              # always re-raise
```

## ERR-CRITICAL-3 — Don't leave tasks dangling

- `asyncio.create_task(...)` without keeping a reference can be garbage-collected mid-flight and loses its exception. Prefer `asyncio.TaskGroup` (3.11+): children are awaited, and a failure cancels siblings.
- Fire-and-forget needs an owner, a stored reference, and a done-callback that logs exceptions.
- `await` every coroutine. A coroutine that's never awaited is a silent no-op (enable `-W error::RuntimeWarning` in tests).

## ERR-HIGH-1 — A small, typed error hierarchy

```python
class RagError(Exception):
    code = "internal"          # stable, machine-readable
    status = 500
    def __init__(self, message: str, **context): super().__init__(message); self.context = context

class InvalidRequest(RagError): code, status = "invalid_request", 422
class NotFound(RagError):       code, status = "not_found", 404
class UpstreamTimeout(RagError):code, status = "upstream_timeout", 504
class LLMOutputInvalid(RagError):code, status = "llm_output_invalid", 502
```

- One registered exception handler converts `RagError` → `{ "code", "message" }` JSON with the right status. Routes `raise`, they don't build error responses.
- The `code` is the contract (the harness adapter branches on it); the `message` is for humans and logs.
- Unknown exceptions → 500 with a generic message; details go to the log, not the client.
- Distinguish **operational** errors (timeout, bad input, provider 5xx: handle) from **programmer** errors (`TypeError`, assertion: crash loudly, fix the code).

## ERR-HIGH-2 — Validate early, return early

Guard clauses at the top (`if not chunks: raise ...`), happy path unindented. Don't use exceptions for ordinary control flow in hot loops (per-query metrics): return a `None`/sentinel and let the caller decide.

## ASYNC-HIGH-1 — Parallelize independent awaits

```python
# Sequential: two round trips back to back
sparse = await fts_search(q); dense = await dense_search(q)

# Parallel: FTS and dense are independent
async with asyncio.TaskGroup() as tg:
    t_sparse = tg.create_task(fts_search(q))
    t_dense = tg.create_task(dense_search(q))
sparse, dense = t_sparse.result(), t_dense.result()
```

Hybrid retrieval's two legs should run concurrently; the fusion waits for both. Start independent I/O first, await later.

## ASYNC-HIGH-2 — One event loop, no nested `asyncio.run`

`asyncio.run` once per CLI entrypoint. Never call it from inside a running loop or from library code. In sync test code use `pytest-asyncio`/`anyio` (see `testing-rules.md`).

## ASYNC-MEDIUM-1 — Context managers for resources

Use `async with` for pools, connections, transactions, clients and timeouts so cleanup runs on every path. Don't hold a DB connection across an LLM call: acquire, query, release, then call the model.
