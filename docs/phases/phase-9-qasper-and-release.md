# Phase 9: QASPER, README and v0.1 release (Design Week 9)

**Goal:** the domain-agnostic claim is proven on a second corpus, and a stranger can reproduce the headline table from the README alone.
**Entry:** Phase 8 done.
**Exit criterion:** someone other than the author reproduces the headline table from the README alone.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 9.1 [ ] Verify the QASPER license and format (before writing the adapter)
- **Do:** check the license against the primary source (not only a dataset card) and the data format; update `DATA_LICENSES.md`. Confirm D4 still stands.
- **Verify:** the primary-source URL and date are recorded in `DATA_LICENSES.md`.
- **Refs:** Design §10.

#### 9.2 [ ] QASPER adapter
- **Do:** `corpora/qasper.py` producing the same `Document`, `Query`, `GoldSpan` shapes. Evidence is paragraph text, not offsets: locate each evidence paragraph in the full text. Report the match rate; unmatched evidence is excluded and counted, never silently dropped. Unanswerable questions kept as `answerable = false`.
- **Verify:** property check that every located span satisfies `text[start:end] == paragraph` (or the documented normalized match); the exclusion count is in a finding. If QASPER is too big, shrink to a fixed subset and say so.
- **Refs:** Design §10, §11 (cut list item 4).

#### 9.3 [ ] Run the headline experiments on QASPER
- **Do:** same strategies, same metrics, same gate machinery, via `ragcalibrate run --corpus qasper`. Reuse the harness unchanged; if it needs changes, that is a finding about the corpus interface.
- **Verify:** results in `docs/results.md` with run IDs.
- **Refs:** Design §14.

#### 9.4 [ ] Final CUAD test runs
- **Do:** for each frozen configuration, a test-split run (once per config, per Design §8.1) and the full results table.
- **Verify:** every row in `docs/results.md` has a value, a regenerating command, a run ID and a date. Any row that cannot be reproduced is deleted, not softened.
- **Refs:** Design §14.

#### 9.5 [ ] README
- **Do:** lead with the problem and the numbers. Include the architecture diagram, results table (each number linked to its command), a 90-second demo, the quick start, an honest limitations and threats-to-validity section (templated queries, single human labeler, per-document retrieval scope, judge model dependence), and a verified prior-art comparison. Do not include the private job-postings statistic or résumé text.
- **Verify:** README reviewed by the user; every claim traces to `docs/results.md` or a finding.
- **Refs:** Design §3, §14, §15 (private).

#### 9.6 [ ] Remaining ADRs
- **Do:** write any ADR from Design §12 not yet written, short. Pick the five most interesting to feature in the README.
- **Verify:** ADR index in the plan has no `planned` rows left, except consciously dropped ones with a reason.

#### 9.7 [ ] Reproduction test by someone else
- **Do:** ask a person who did not build it (or at least a clean machine and a fresh clone) to follow only the README to the headline table.
- **Verify:** outcome and every point of friction recorded in a finding and fixed.
- **Refs:** Design §11 (Week 9 exit).

#### 9.8 [ ] Pre-publication audit (owner: user decides; agent prepares the checklist)
- **Do:** secret scan over the full history; confirm `docs/private/` is untracked; confirm raw datasets are not committed; licenses and attributions present; package name decision applied; `docs/` content appropriate for a public audience (the plan, findings and phase files will be visible).
- **Verify:** checklist ticked by the user. Tagging v0.1 and publishing are the user's actions.
- **Refs:** Design §10, §15.
