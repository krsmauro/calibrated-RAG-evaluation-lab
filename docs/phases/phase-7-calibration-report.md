# Phase 7: Calibration report, bias tests, A/A reruns (Design Week 7)

**Goal:** the judge ships with a known error rate: κ against gold with CIs, measured biases, one mitigation measured before and after, and the LLM stages' own run-to-run noise.
**Entry:** Phase 6 done (human labels exist).
**Exit criterion:** every number in the report regenerates from one command.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

---

#### 7.1 [ ] κ, AC1 and confusion-matrix functions
- **Do:** `stats/agreement.py`: Cohen's κ, Gwet's AC1, confusion matrix, precision and recall of the fail class, bootstrap CI for κ. Pure functions, seeded.
- **Verify:** known-answer tests with hand-computed κ (including a high-agreement, low-κ imbalanced example that demonstrates the kappa paradox). Empty and single-class inputs have defined behaviour.
- **Refs:** Design §8.4.

#### 7.2 [ ] `rageval calibrate`
- **Do:** per criterion and per label source (human, perturbation, derived): κ with 95 percent CI, raw agreement, confusion matrix, class prevalence, fail-class precision and recall, and the judge's repeat-to-repeat consistency from 6.7. The "judge says pass, gold says fail" cell is highlighted. The report states the label source next to every κ and says plainly that derived-label κ is partly circular. Include the user's intra-rater κ.
- **Verify:** report generated from stored data with one command; n is shown with every number.
- **Refs:** Design §5.5, §8.4.

#### 7.3 [ ] Recheck sample size
- **Do:** recompute the CI width for κ at the real prevalence and agreement. If too wide to support a claim, flag it to the user before reporting.
- **Verify:** a finding records the computation and the decision.
- **Refs:** Design §8.4 (step 5).

#### 7.4 [ ] Bias tests
- **Do:** position (pairwise judge prompt run in both orders; flip rate), verbosity (padded or restated answers, same correctness; change in pass rate), citation trust (swapped citations; share still passed on faithfulness). Each reported with a CI. Self-preference is on the cut list: do it only if D1 gave two model families and budget remains.
- **Verify:** each test has a stated expected verdict per item; effects reported with CI; costs logged.
- **Refs:** Design §8.4 (bias table).

#### 7.5 [ ] One mitigation, before and after
- **Do:** pick the largest measured bias and apply a mitigation (evaluate both orders and require agreement, cap length, show only cited text, or change judge family). Re-run the same test.
- **Verify:** before and after numbers with CIs in `docs/results.md`; a finding states whether the mitigation helped and what it cost.
- **Refs:** Design §8.4.

#### 7.6 [ ] LLM A/A reruns
- **Do:** 10 to 20 repeats of the same configuration on the CI subset, cache **off**, then apply the gate to pairs of repeats. If the false-fail rate exceeds nominal, decide how to build run-to-run variance into the gate (average k repeats per run, or add a variance component) and record it.
- **Verify:** false-fail rate with an interval is in `docs/results.md`; a finding records any gate change this forces; cost recorded.
- **Refs:** Design §5.7, §8.5 (validating the gate, item 2); skill EVAL-CRITICAL-5.

#### 7.7 [ ] One-command regeneration
- **Do:** a Make target that regenerates the calibration report and bias tables from stored data.
- **Verify:** run it on a clean checkout with the data files; numbers identical to the committed report.
- **Refs:** Design §14.

#### 7.8 [ ] ADRs
- **Do:** ADR 0006 (binary per-criterion verdicts), 0008 (cache and determinism strategy).
- **Verify:** ADR index updated.

#### 7.9 [ ] (Cut list) PPI stretch goal
- **Do:** only if ahead of schedule and the user asks: prediction-powered inference using the human labels. Skip otherwise.
- **Refs:** Design §8.4 stretch goal, §11 cut list.
