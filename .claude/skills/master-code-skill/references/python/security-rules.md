# Backend — Security Rules

For the FastAPI service, the harness, and CI. Grounded in OWASP guidance; verify version-specific advice against current docs.

## SEC-CRITICAL-1 — No secrets in the repo, the image, or the logs

- Keys (LLM provider, Langfuse) come from environment via `Settings` (`SecretStr`), `.env` is gitignored, `.env.example` has placeholders only.
- gitleaks (pre-commit and CI) must stay green. A leaked key is rotated, not just removed from history.
- Never log `settings`, request headers containing auth, or raw provider responses. Redact before logging.
- CI secrets: do not expose them to fork PRs. The gate must handle fork PRs without secrets (plan Week 8): retrieval-only evals need no keys.

## SEC-CRITICAL-2 — Parameterized SQL, always

```python
# NEVER
await conn.fetch(f"SELECT * FROM chunks WHERE document_id = {doc_id}")
await conn.fetch("... ORDER BY " + user_sort)

# ALWAYS — bound parameters; allow-list identifiers
await conn.fetch("SELECT id, start_char, end_char FROM chunks WHERE document_id = $1 AND chunker_id = $2", doc_id, chunker_id)
SORTS = {"score": "score DESC", "id": "id ASC"}
order = SORTS[sort]   # KeyError on unknown, not injection
```

Applies to SQLite too (`?` placeholders). Table/column/identifier names can't be parameterized: map from an allow-list. `websearch_to_tsquery($1)` takes the user's text as a parameter — never interpolate it.

## SEC-CRITICAL-3 — Model output and corpus text are untrusted

Corpus documents and retrieved chunks can contain prompt-injection ("ignore previous instructions…"). Therefore:
- Put retrieved text in clearly delimited, labelled sections of the prompt, and instruct the model to treat it as data.
- The model has **no tools** that act on the world in this project; keep it that way unless a rule is added here.
- Never `eval`/`exec`/`subprocess` anything derived from model output. Never build file paths, SQL or shell commands from it.
- Judge prompts get the same treatment: the answer under evaluation is attacker-controlled text from the judge's point of view.

## SEC-HIGH-1 — Outbound HTTP (SSRF and downloads)

- Dataset downloads (CUAD, QASPER) use pinned URLs and **verify a checksum** before use; fail if it doesn't match.
- The harness adapter calls a user-supplied SUT URL: allow only `http(s)`, apply timeouts, and don't follow redirects blindly. Don't let a request to a user-supplied URL be driven by LLM output.
- Extract archives safely (no path traversal: resolve and check each member stays under the target dir).

## SEC-HIGH-2 — Service hardening

- The service is an eval target, not a public product, but treat it as exposed: bind to `127.0.0.1`/Compose network by default, not `0.0.0.0` on a host.
- Request size limits and a max `k`; reject unbounded inputs (`k`, query length, document count).
- No stack traces in responses; the exception handler returns a stable `code` and a safe message, logs the detail.
- CORS: not enabled unless needed; if enabled, explicit origins, never `*` with credentials.
- If authentication is added later, authenticate at the router/dependency level so a new route can't forget it, and keep authn separate from authz.

## SEC-HIGH-3 — Dependencies and supply chain

- Lockfile (`uv.lock`) committed; CI installs with `--frozen`.
- Run `pip-audit` (or `uv` equivalent) in CI; triage findings, don't blanket-ignore. Record any accepted advisory with a reason and expiry.
- Pin GitHub Actions to a commit SHA for third-party actions; give workflows least-privilege `permissions:`.
- Don't `pickle.load` / `torch.load` untrusted files; prefer safe formats (`safetensors`, JSON). Pin model names and revisions for embedding/reranker downloads.

## SEC-MEDIUM-1 — Data and licensing

- CUAD is CC BY 4.0: keep attribution. Don't commit raw dataset dumps if licensing or size is a problem; commit the generation script and the hashes.
- Documents may contain personal/commercial info: don't send them to a third-party API without it being intended, and never log them at INFO.
- Docker: run as a non-root user, no secrets in image layers or build args, minimal base image.
