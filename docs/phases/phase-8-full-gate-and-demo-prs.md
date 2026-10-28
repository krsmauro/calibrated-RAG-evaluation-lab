# Phase 8: Full gate, PR comment, demo PRs, latency (Design Week 8)

**Goal:** the Action gates judge metrics too, behaves safely on forks, and has two demo PRs that prove it.
**Entry:** Phase 7 done.
**Exit criterion:** both demo PRs behave as expected on a fresh fork.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

Agents prepare branches and commits-ready changes only. They never push or open PRs; the user does (global rule). Steps that need a push are marked blocked-on-user until the user confirms.

---

#### 8.1 [ ] Extend the gate to judge metrics
- **Do:** one primary metric per kind of change (recall for retrieval changes, judge faithfulness pass rate for prompt or generator changes), others non-gating. If several must gate, apply Holm-Bonferroni. Incorporate any run-to-run variance decision from step 7.6.
- **Verify:** unit tests of the selection rule; a no-op prompt change does not fail in the A/A-derived simulation.
- **Refs:** Design §8.5.

#### 8.2 [ ] Baseline management for LLM metrics
- **Do:** reuse a stored baseline run from `main`; print its age in the report. Decide where it is stored (workflow artifact, release asset, cache) given that the SQLite run store is a single file. Update ADR 0010.
- **Verify:** the report shows the baseline age; an expired or missing baseline gives a clear message, not a crash.
- **Refs:** Design §8.5.

#### 8.3 [ ] Sticky PR comment, complete
- **Do:** baseline, candidate, delta, 95 percent CI and outcome per metric; cost of the run; links to the report artifact and Langfuse traces when enabled. Updated in place on each push.
- **Verify:** golden-file test of the rendered Markdown; live check on a test PR.
- **Refs:** Design §8.5 (PR comment).

#### 8.4 [ ] Fork PR handling
- **Do:** workflows from forks have no secrets. LLM stages must skip cleanly and fall back to the retrieval-only gate with a clear note in the comment. Do not use `pull_request_target` to run PR code with secrets.
- **Verify:** a real fork PR (user opens it) produces a retrieval-only result and green infrastructure. Security-review the workflow file.
- **Refs:** Design §8.5 (fork PRs).

#### 8.5 [ ] Demo PR A: realistic seeded regression
- **Do:** a tidy-looking change a reviewer would approve, such as switching the FTS text-search config from `english` to `simple`. **First check it actually moves the metric** on the CI subset; if it does not, pick another realistic regression and record why in a finding (a demo that does not fail is a bad demo). Prepare it on a local branch.
- **Verify:** gate returns Fail with the CI shown in the comment (after the user pushes and opens the PR).
- **Refs:** Design §11 (demo PR idea).
- Note (2026-10-28, from 3.1): the configuration lives in two places that must change together: a new migration that rebuilds the generated column `chunks.tsv` (migration 0003 builds it with `english`) and `FTS_CONFIG` in `service/retrieval.py`. The integration test `test_fts_parses_queries_with_the_configuration_the_column_was_built_with` fails if only one changes. S1 relies on exact terms (finding F-011), so the change is likely to move its metric, but measure it.
- Note (2026-10-28, from 3.3): another candidate, perhaps a better story: switching the served strategy from hybrid (S3) to rerank (S4), "add a cross-encoder reranker". Reviewers expect a reranker to help, and on CUAD dev with the templated question it lowers recall@5 (finding F-012, numbers in `docs/results.md`). Measure the drop on the CI subset first, as above; if decision D7 changes the question text, S4 is likely to help instead and stops being a regression.

#### 8.6 [ ] Demo PR B: benign change
- **Do:** a harmless change (for example refactor, comment, or an equivalent-behaviour tweak) that must Pass.
- **Verify:** gate returns Pass. If it returns Inconclusive, the CI subset is too small for δ; record it and revisit step 4.5.
- **Refs:** Design §8.5.

#### 8.7 [ ] Latency load test
- **Do:** k6 or Locust at fixed concurrency against the Compose stack, cold and warm, on stated hardware. Report `/retrieve` p50/p95/p99 per strategy, `/answer` end to end, and reranking's latency cost separately from LLM time.
- **Verify:** script and raw output in the repo; table in `docs/results.md` with hardware stated.
- **Refs:** Design §8.6.

#### 8.8 [ ] Fill the cost targets
- **Do:** replace the blank budgets in Design §8.6 with measured values for the CI run and the full CUAD test run (cold and warm).
- **Verify:** values in `docs/results.md` link to run manifests.
