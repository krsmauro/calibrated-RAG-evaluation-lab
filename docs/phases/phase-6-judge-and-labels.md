# Phase 6: Judge prompts and the labeled calibration set (Design Week 6)

**Goal:** a frozen judge v1 and a calibration set with blind human labels, perturbation labels and derived labels.
**Entry:** Phase 5 done (stored answers exist).
**Exit criterion:** labels were made blind; the rubric is in the repo.

Step format and update rules: see "Agent protocol" in `docs/project-plan.md`.

**Do not skip or fake step 6.5.** Human labels must come from the user. An agent must never label items itself or pre-fill labels, because the point is agreement with an independent human.

---

#### 6.1 [ ] Written rubric
- **Do:** `docs/judge-rubric.md` with a precise pass/fail definition per criterion (faithfulness, correctness, and any criterion step 1.8 kept), borderline examples, and rules for abstentions. Written before labeling and not changed afterwards without bumping a version and relabeling.
- **Verify:** the user approves it. Each criterion has at least two worked pass and two worked fail examples.
- **Refs:** Design §5.5, §5.6; finding F-001.

#### 6.2 [ ] Judge prompts v1
- **Do:** one prompt per criterion, binary verdict plus a short rationale, structured output validated by Pydantic. Version and hash recorded. The judge sees only what the criterion needs (for faithfulness: the answer and the cited text). Judge model is a pinned snapshot, ideally a different family from the generator.
- **Verify:** hash is in the manifest and the cache key; a prompt edit changes the hash.
- **Refs:** Design §5.6, §8.4.

#### 6.3 [ ] Calibration item set
- **Do:** sample answers from stored runs (stratified: answerable and unanswerable, several strategies, mixed quality). Each item stores the **answer text, its hash, the question, the cited chunk text and the gold context**, frozen in a file, so labels attach to the item and not to a run that may later change (F-005). Target 200 to 300 items; compute the needed n at the observed class prevalence before labeling.
- **Verify:** file is hashed; re-generating it from the same seed gives the same items; no judge verdict is stored in the file shown to the labeler.
- **Refs:** Design §5.5, §8.4 (step 5); finding F-005.

#### 6.4 [ ] Perturbation generator
- **Do:** deterministic, seeded transformations of known-good answers with known correct verdicts: cite a different clause, negate a key term, add an unsupported claim, point a citation at a wrong chunk, pad with true but irrelevant text (for the verbosity test), swap citations (for the citation-trust test). Each perturbation records its type.
- **Verify:** unit tests per perturbation; the expected verdict per perturbation type is written down and reviewed by the user, since this is the ground truth for those items.
- **Refs:** Design §5.5, §8.4.

#### 6.5 [ ] Blind human labeling (owner: user)
- **Do:** the user labels the items against the rubric, **without seeing the judge's verdict**. Provide the simplest workable tool: a terminal loop or a spreadsheet export that hides everything except what the rubric allows. No web UI. Re-label a random 10 to 20 percent after at least a few days to measure the user's own consistency (intra-rater κ).
- **Verify:** label file has timestamps; intra-rater κ is computed in Phase 7. Budget about 1 to 2 minutes per item (5 to 10 hours for 300 items).
- **Refs:** Design §5.5, §16 (labeling risk, "never cut").

#### 6.6 [ ] Derived labels
- **Do:** compute deterministic labels from CUAD spans: does the answer's presence claim match gold, do its citations overlap the gold span. Tag the source as `derived`.
- **Verify:** unit-tested; every label in the combined file carries its source (`human`, `perturbation`, `derived`).
- **Refs:** Design §5.5.

#### 6.7 [ ] Judge runs for calibration
- **Do:** run judge v1 over the calibration set three times with the cache **off** to measure the judge's own consistency. Store with `repeat_idx`.
- **Verify:** three complete repeats stored; cost recorded; the max-cost guard was used.
- **Refs:** Design §8.4 (step 3); skill EVAL-CRITICAL-5.
