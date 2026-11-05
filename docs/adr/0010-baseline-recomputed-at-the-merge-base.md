# ADR 0010: Baseline management in CI: recompute retrieval at the merge base, cache only the index

- **Status:** accepted for retrieval metrics. The LLM-metric part is planned and will be amended in step 8.2.
- **Date:** 2026-11-05
- **Step:** 4.9. It records the choices built in steps 4.7a (`scripts/gate.py`, `make gate`) and 4.7b (`action/`, `.github/workflows/gate.yml`). The Action has not yet run on GitHub: 4.7b waits on the user's test pull request, so the CI timings below are local measurements.

## Context
A gate compares a candidate with a baseline, and the baseline has to be the right one. It must differ from the candidate by exactly the pull request's changes, be measured on the same eval set and index, and not drift. Design §8.5 proposes: for retrieval, recompute the baseline at the merge base in the same job, because it is cheap and immune to drift; for LLM metrics, reuse a stored baseline from `main` and print its age, because hosted models can change underneath.

Facts at the time:
- Retrieval is deterministic (step 3.8), so a recomputed baseline equals any earlier run of the same commit.
- The gate runs on all 408 dev contracts (D9). One S3 run on dev takes about 20 s on an Apple M5, and the whole local gate about 45 s.
- CI has no index. Building it (all 510 contracts) takes about 7 minutes locally and longer on a GitHub runner.
- A `pg_dump` of the full local index is 193 MB, written in 15 s and restored into a fresh container in 8 s, every row intact. A no-op ingest over a restored index takes 5.3 s.

## Decision
1. **The retrieval baseline is recomputed at the merge base, in the same job, every time.** `scripts/gate.py` checks out the merge base of the base ref and HEAD in a temporary git worktree. It runs the config there with that commit's own service (port 8101) and harness, and runs the candidate from the working tree with its own (port 8102). Both runs go into the run store and are compared by `report.compare`.
   - In CI the checkout is GitHub's merge commit of the PR into the base branch, so the merge base with `origin/<base>` is the base commit the PR was merged onto.
   - Locally (`make gate`) the candidate is the working tree and the merge base is where the branch left `main`.
   - Either way, the two sides differ by exactly the PR's changes.
2. **No stored baseline is reused,** even when the run store already holds a clean run of the same config at the merge base. CI starts with an empty store anyway.
3. **What CI caches is the index, not a result.** The Postgres index is saved as a `pg_dump` keyed on git's blob ids of everything that shapes it: `ingest/`, `corpora/`, the migrations, `alembic.ini`, the ingest and fetch scripts, the Makefile, `docker-compose.yml` and `uv.lock`. The cache is scoped to the PR, and it is saved before the gate runs, so a Fail still keeps it for the next push.
4. **LLM metrics (step 8.2, not built):** reuse a stored baseline run from `main` and print its age in the report, as Design §8.5 says. This ADR is amended when that is built.

## Alternatives considered
- **A stored baseline from `main`** (a workflow on each push to `main` uploads its runs, and PRs download them). Loses for retrieval:
  - it needs a second workflow and artifact retention;
  - it goes stale as soon as `main` moves, and a baseline from a different commit than the merge base mixes other people's changes into the PR's delta;
  - its index was built in another job, so the two sides would no longer read one index.
  Recomputing costs about 20 s locally.
- **Reuse a clean stored run at the merge base when the local store has one.** Not done: it saves about 20 s locally and nothing in CI, and it adds a question of whether that run read the same index. Recorded as deviation (3) of step 4.7a.
- **Run the baseline in a parallel job.** Loses: each job would need its own Postgres and its own index, doubling the slow part, and the two sides would no longer read one index.
- **Baseline at the branch's fork point in CI** (the merge base of the PR head and the base branch). Loses: it ignores everything merged to the base since the branch started, so the candidate is not what would land. GitHub's merge commit is.
- **Cache the embeddings instead of the database.** Loses: a restore would still have to chunk and insert every row. A dump restores everything in seconds, the generated full-text column included.
- **One index cache shared by every PR,** by running the ingest on pushes to `main`. Not done (step 4.7b, deviation 4): each PR's first run builds the index once. Revisit if those first runs are too slow.

## Consequences
- Drift cannot enter the baseline. Both sides run in one job, on one index and one eval set, minutes apart, and an eval-set difference is refused by `compare`.
- **Both sides read the index the PR's own code built.** A PR that changes a chunker id or the corpus text leaves the baseline without the chunks or text it expects, so the gate cannot run (exit 2) or reports no outcome. A chunker change is therefore gated locally after loading both chunkers, not in CI. That matters for D8 and for a chunker demo PR (Phase 8).
- **Each side is measured with its own harness.** A PR that edits a metric's code measures the baseline with the old code and the candidate with the new, so the delta mixes the two. Such a PR needs its own review, for example both runs re-scored with one harness.
- Every push costs two dev runs. A PR's first push also builds the index, which later pushes restore. How long both take on a GitHub runner is unknown until the test PR runs (step 4.7b).
- The gate needs no secrets, so a fork PR gets the same check. Its token cannot comment, so it gets the report in the job summary only.
- Revisit:
  - in step 8.2, for the LLM baseline;
  - if PRs' first runs are too slow (share the index cache from `main`);
  - when D8 lands, since chunker PRs cannot be gated in CI as built.
