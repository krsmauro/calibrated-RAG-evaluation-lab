# Karpathy Mindset

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

**Tradeoff**: these guidelines bias toward caution over speed. For trivial single-line tasks, use judgment — the principles still apply but don't need ceremony.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

**Why this matters**: LLMs default to confident-sounding output even when the task is ambiguous. A two-sentence clarification up front saves a full rewrite later.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: _"Would a senior engineer say this is overcomplicated?"_ If yes, simplify.

**Why this matters**: every speculative abstraction becomes a maintenance burden. The cost of YAGNI ("you aren't gonna need it") is real — and you usually weren't gonna need it. If a change is voluminous but can truly add value or prevent future issues mention it.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that _your_ changes made unused.
- Don't remove pre-existing dead code unless asked, or ask for permission.

**The test**: every changed line should trace directly to the user's request. If a reviewer asks "why did you touch this line?", you should have a one-sentence answer that ties it back to the task.

**Why this matters**: scope creep destroys PR review quality and bloats blast radius. A clean diff is a reviewable diff.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass."
- "Fix the bug" → "Write a test that reproduces it, then make it pass."
- "Refactor X" → "Ensure tests pass before and after."

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**Why this matters**: without a verifiable target, "done" becomes subjective and tasks drift. A concrete check ("the test passes", "the page renders without console errors") collapses the ambiguity.

---

## How this interacts with the lane-specific rules

The Karpathy mindset is the _foundation_. The backend and eval rule sets are _specific applications_ of these principles:

- "Create pools and clients once in lifespan" (BE) is **Simplicity First** (don't rebuild a connection pool or reload a model per request).
- "Pydantic only at trust boundaries" is **Simplicity First** (the type checker already proves internal calls).
- "Idempotent ingestion" is **Goal-Driven Execution** (the verifiable goal is "ingesting twice leaves the same state as once").
- "Known-answer tests for every metric" is **Goal-Driven Execution** (a hand-computed value is the success criterion).
- "No framework around the LLM client" is **Simplicity First**.
- "Surgical changes" maps directly to PR hygiene, and to the eval lane: a drive-by change to a metric silently invalidates every stored run.

When a lane-specific rule and the Karpathy mindset seem to conflict, prefer the mindset, but check whether you've actually understood the rule. They almost never truly conflict.
