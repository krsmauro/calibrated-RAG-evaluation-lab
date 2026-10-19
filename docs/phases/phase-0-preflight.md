# Phase 0: Pre-flight (before any code)

**Goal:** remove the blockers that only the user can remove, and make the docs safe to build on.
**Design week:** none (do this before Week 1).
**Progress (2026-10-19):** 0.3 and 0.4 done; 0.1 appears done (tree clean, `docs/` tracked); 0.6 done (package `ragcalibrate`); D1 to D5 answered in the plan; 0.5 waits for Phase 5 (D1 deferred).
**Exit criterion:** D1 to D3 answered in `docs/project-plan.md`; `docs/` committed by the user; the skill's doc pointers are correct.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 0.1 [ ] Commit the docs (owner: user)
- **Do:** review `docs/` and commit it. Agents cannot commit (global rule). Until this happens, `docs/` exists only on this disk and a bad edit is unrecoverable.
- **Verify:** `git status` no longer lists `docs/` as untracked.

#### 0.2 [ ] Answer the open decisions D1 to D5 (owner: user)
- **Do:** fill in the "Decisions needed" table in `docs/project-plan.md`. D1 (provider and budget) blocks Phase 5. D2 (hours per week) tells us whether to apply the cut list now. D3 (public timing) decides whether 0.3 is urgent.
- **Verify:** every row has a decision and a date, or an explicit "defer until Phase N".
- **Refs:** Design §17.

#### 0.3 [x] Move career notes out of the public tree
- **Do:** Design §15 contains the private job-postings statistic and résumé material. Move §15 from `docs/design/project-design.md` into `docs/private/career-notes.md` and add `docs/private/` to `.gitignore`. Leave a one-line pointer where it was. Do it now, not in Phase 9, because D3 may make the repo public early.
- **Verify:** `grep -rn "65%" docs/ --include=*.md` finds nothing outside `docs/private/`; `git check-ignore docs/private/career-notes.md` succeeds.
- **Refs:** Design §15 header note.
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. Moved Design §15 verbatim to `docs/private/career-notes.md`, left a one-line pointer in the design, and added a `.gitignore` with `docs/private/` and `.env`.
  Evidence: `git check-ignore -v docs/private/career-notes.md` matches `.gitignore:2`; `grep -rn "65%" . --include='*.md'` now matches only the Verify line of this step (which contains the pattern itself) and nothing in the design or README.
  Files: `docs/design/project-design.md`, `docs/private/career-notes.md` (new, ignored), `.gitignore` (new, needs `git add`).
  Deviations: also ignored `.env` (step 0.5 assumes it is ignored); the original §15 text is still in git history from the earlier commit, so if the repo goes public the history needs rewriting or the repo needs a fresh start (user decision, see D3).

#### 0.4 [x] Fix the master-code-skill's pointers to the docs
- **Do:** `.claude/skills/master-code-skill/SKILL.md` cites `docs/project-plan.md §13` and `plan §5.8`. Those sections now live in `docs/design/project-design.md`. Update the pointers. The skill's Reference Map also lists files under `references/python/` and `references/eval/` that do not exist yet; mark each "not written yet" so an agent does not waste a turn on a missing file. Each phase has a step that writes the reference file for its lane.
- **Verify:** every path named in SKILL.md either exists or is marked not-yet-written.
- **Refs:** finding F-006.
- Claimed: Claude (session 6137b804), 2026-10-19
- **Done:** 2026-10-19, Claude. Replaced the stale `docs/project-plan.md §N` and `plan §N` citations with `docs/design/project-design.md` / `Design §N` in SKILL.md and four reference files; section numbers were already identical.
  Evidence: every `references/...` and `docs/...` path named in SKILL.md exists (checked with a script); `grep -rn "project-plan\|plan §" .claude` returns nothing.
  Files: `.claude/skills/master-code-skill/SKILL.md` and `references/{python/tooling-rules,eval/llm-rules,eval/eval-integrity-rules,eval/stats-rules}.md`.
  Deviations: the step also asked to mark unwritten reference files "not written yet"; all 13 referenced files already exist, so nothing needed marking. F-006 point 1 is therefore already resolved except for the stale citations fixed here.

#### 0.5 [ ] Provider account, keys and a hard spend limit (owner: user; blocked by D1)
- **Do:** create the API key(s) for the generator and the judge. Set a hard monthly spending limit at the provider, not only the harness `--max-cost` guard. Put keys in `.env` (gitignored), never in the repo.
- **Verify:** key works from a one-line script outside the repo; the limit is visible in the provider console.
- **Refs:** `docs/llm-production-best-practices.md` (Observability: "hard spending limit at the provider").

#### 0.6 [x] Check the package name (owner: user or agent; blocked by D5)
- **Do:** check `rageval` on PyPI and GitHub. If taken, pick a new name now. Renaming after Phase 1 touches every import.
- **Verify:** decision recorded in D5.
- **Done:** 2026-10-19, Claude with the user. `rageval` is free on PyPI but has crowded GitHub names (OpenBMB/RAGEval, 244 stars); `raglab` is taken on PyPI; the user chose `ragcalibrate`.
  Evidence: `ragcalibrate` returns 404 on PyPI and npm (also `rag-calibrate`) and the GitHub name search returns 0 repositories.
  Files: all docs and skill files that said `rageval` (17 files), D5 in `docs/project-plan.md`.
  Deviations: none. The check is a snapshot; re-check before the first publish.
