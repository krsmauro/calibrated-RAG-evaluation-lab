# Backend — Observability Rules

Structured logging, tracing and run metadata. Logging uses the **stdlib `logging` module only** (no structlog/loguru): the project keeps external dependencies to a minimum.

## OBS-CRITICAL-1 — Structured logs with fields, not formatted strings; no `print`

```python
logger = logging.getLogger(__name__)   # one per module

# NEVER
print(f"retrieved {n} chunks for {query}")
logger.info(f"query {qid} done in {ms}ms")

# ALWAYS — stable event name as the message, data in `extra` (searchable, redactable)
logger.info("retrieve.completed", extra={"query_id": qid, "strategy": strategy, "k": k, "latency_ms": ms})
```

- Configure logging once, in the entrypoint (app factory / CLI), never at import time. Library modules only call `logging.getLogger(__name__)`.
- A small `logging.Formatter` subclass (~15 lines, in one module) emits one JSON object per line: timestamp, level, logger, message, plus the `extra` fields. Don't build a logging framework beyond that.
- Don't use `extra` keys that collide with `LogRecord` attributes (`name`, `message`, `args`, `module`, ...): stdlib raises `KeyError`. Prefix or pick distinct names (`query_id`, `latency_ms`).
- Use lazy `%s` args only for human-text messages; for events, the message is a constant name.
- Log exceptions with `logger.exception("event.name", extra={...})` (inside `except`) so the traceback is kept.
- Event names are `noun.verb` and stable (`retrieve.completed`, `judge.invalid_output`); alert on names, not message text.
- Lint `print` out of `src/` (ruff `T20`). The CLI's user-facing output goes through one reporting function, not scattered prints.
- Levels: `ERROR` = needs attention; `WARNING` = degraded but handled (retry, fallback); `INFO` = lifecycle and run milestones; `DEBUG` = detail, off by default.
- In async code, stdlib handlers are synchronous but cheap for stdout/stderr; if file or network handlers are added, use `logging.handlers.QueueHandler` so logging never blocks the event loop.

## OBS-CRITICAL-2 — Never log secrets, full prompts or document text at INFO

Redact API keys and auth headers. Documents are contract text: log IDs, hashes, offsets and lengths, not content. Full prompts and responses go to the **trace** (Langfuse, access-controlled) or the content-addressed cache, not the application log.

## OBS-HIGH-1 — Correlation: one ID joins everything

Every decision carries IDs that join across logs, traces and the run store: `run_id`, `query_id`, `request_id` (service), `trace_id`. The harness sends a request ID header to the SUT and records it, so a bad result can be traced to a server log line. "Log the decision, then the outcome" — without a join key you can't debug or learn.

## OBS-HIGH-2 — One Langfuse trace per query

Spans: `retrieve` (strategy, k, latency), `rerank`, `generate` (model, tokens, cost), `judge` (criterion, verdict). Tracing must be optional and failure-tolerant: if Langfuse is down or unconfigured, the run continues (no-op tracer), and tracing errors never fail a query.

## OBS-HIGH-3 — Stamp versions on every result

Each stored result links to what produced it: git SHA (+ dirty flag), config hash, evalset hash, chunker ID, strategy, generator/judge model IDs (snapshot, not alias), judge prompt hash, embedding model + revision, seeds. A regression you can't attribute to a version is a regression you can't fix.

## OBS-HIGH-4 — Cost and latency are first-class outputs

Record input/output tokens and USD per call, latency per stage, retries and cache hit/miss. Report p50/p95/p99, and separate retrieval latency (our code) from LLM latency (the provider's). A cache hit costs ~$0 and must be labelled as a hit so cost figures aren't mistaken for fresh-run cost.

## OBS-MEDIUM-1 — Metrics worth alerting on (when deployed)

Error rate by `code`, p95 latency by endpoint, queue/semaphore wait, DB pool saturation, provider 429 rate, cost per run vs budget, invalid-LLM-output rate (a spike usually means a prompt or model change). Set a cost ceiling per run and abort when exceeded.
