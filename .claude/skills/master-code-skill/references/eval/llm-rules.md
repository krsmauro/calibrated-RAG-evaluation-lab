# Eval — LLM Rules

For `src/rageval/llm/`, the generator, the judge and anything that builds prompts. Sources: `docs/project-plan.md` §5.6–5.7, §8.3, §8.6 and `docs/llm-production-best-practices.md`.

## LLM-CRITICAL-1 — One thin provider interface, no framework

The generator and the judge use the same small interface (`complete(request) -> response` with tokens, cost, stop reason). No LangChain/LlamaIndex. The interface is what makes a fake provider possible in tests and a second provider cheap to add. Don't build an abstraction layer beyond what the two callers need.

## LLM-CRITICAL-2 — Model output is untrusted input

For every call:
1. Check the **stop reason**. Truncated (`max_tokens`/length) is a failure, not an answer.
2. Parse into a Pydantic model (`extra="forbid"`).
3. Validate semantics: every cited `chunk_id` was in the retrieved set; `present=False` ⇒ no citations; `present=True` ⇒ ≥ 1 citation.
4. On invalid output: bounded retry (once or twice), then **record the failure** in the run as its own outcome with the reason. Never coerce a bad parse into a pass/fail/abstain.

Use the provider's structured-output / schema-constrained mode where available, but still validate: constrained decoding doesn't guarantee semantic correctness.

## LLM-CRITICAL-3 — The cache key covers everything that changes the answer

Key = hash of: provider, **model snapshot** (dated ID, not an alias), parameters (temperature, max tokens, seed if supported), prompt template hash, and the fully rendered input. Missing any of these produces stale hits that look like stable results. The cache is a **separate SQLite file** (`llm_cache`), content-addressed, with token counts stored so a cache hit can still report the cost of the original call.

Modes (plan §8.6):

| Mode | Use |
|---|---|
| `read-write` | local development |
| `read-only` | CI baselines |
| `off` | A/A reruns and judge-consistency runs |

**EVAL-CRITICAL-5 applies**: caching makes identical reruns identical, so a false-alarm study with the cache on is 0% by construction and proves nothing. Any study measuring run-to-run noise must run with the cache `off` and say so in its manifest. Hosted models are not deterministic even at temperature 0.

## LLM-HIGH-1 — Judge prompts: binary, per criterion, versioned

- Pass/fail per criterion (faithfulness, correctness, citation support) with a short rationale, **not** a 1–10 score. Binary verdicts are more consistent across runs, make κ well-defined, and map to a gate.
- One criterion per call (or clearly separated fields), so one failure mode doesn't mask another.
- The judge prompt is a versioned file; its **hash** is in the cache key and the run manifest. Editing the prompt text changes the hash and invalidates comparability; never edit a frozen judge in place after calibration: create `judge_v2`.
- The judge sees only what it needs (e.g. cited text, not the whole context), which is also a bias mitigation.
- Treat the answer under evaluation as attacker-controlled text (prompt injection from the judge's side).

## LLM-HIGH-2 — Calibration protocol is part of the code

Freeze prompt + model snapshot → assemble labeled set (derived, perturbation, blind human) → run the judge **3×, cache off** to measure the judge's own consistency → report κ with CI, confusion matrix, prevalence, fail-class precision/recall per criterion and label source. Perturbations (cite a different clause, negate a key term, add an unsupported claim, point a citation at the wrong chunk) each carry a known correct verdict and double as bias-test material. Blind human labels must be made **without seeing the judge's verdict**; the harness must not display it in the labeling tool.

## LLM-HIGH-3 — Generation and judging use different model families where possible

Self-preference is a known judge bias; the default is a judge from a different family than the generator. If they must match, say so in the report and run the self-preference test.

## LLM-HIGH-4 — Cost is metered and capped

Tokens × prices from a **dated, versioned price file** (prices change). Estimate spend up front and abort if it would exceed `--max-cost`. Report cost per run and per query, labelled with cache-hit vs fresh. Never read the API key from anywhere except `Settings`; never log prompts/responses at INFO (they contain contract text).

## LLM-MEDIUM-1 — Prompts are code

Prompt templates live in files under version control, are reviewed in PRs, rendered by a tested function (no ad-hoc f-strings scattered in handlers), and delimit retrieved text as data (see `SEC-CRITICAL-3`). A prompt change is one change at a time: don't ship it alongside a retriever or model change, or you can't attribute the effect.

## LLM-MEDIUM-2 — Fakes for tests

Provide a deterministic fake provider that returns schema-valid canned output (and can be told to return truncated/invalid/slow responses) so retry, failure-recording and cache-mode behavior are testable without the network or money.
