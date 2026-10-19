# F-005: Calibration labels must attach to frozen answer text, and there is one labeler

- **Status:** open
- **Date:** 2026-10-19
- **Found by:** Claude, while writing the plan
- **Evidence level:** read from a source (design reasoning); consequences not yet measured
- **Affects:** 6.3, 6.5, 7.2, 9.5; Design §5.5, §8.4

## Finding
Two issues the design does not spell out.
1. Human labels describe a specific answer. If they are keyed to `(run_id, query_id)`, any later regeneration (new prompt, new model snapshot, cache off) silently invalidates them. They must key on a hash of the frozen answer text plus its context.
2. The only human labeler is the project author, who also wrote the rubric. Intra-rater consistency (re-labeling after a few days) measures stability, not independence. κ against one person's labels is evidence about agreement with that person.

## Evidence
Design §5.5 and §8.4 describe the labeling but not the keying, and mention re-labeling only for consistency.

## Consequence
Step 6.3 stores self-contained, hashed items. The README's threats-to-validity section (9.5) must state the single-labeler limitation plainly. If a second labeler is available for even a subset (50 items), report inter-rater κ; that would strengthen the headline claim a lot.

## Resolution
