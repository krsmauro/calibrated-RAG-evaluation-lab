# F-001: Judge criteria are listed inconsistently in the design

- **Status:** resolved
- **Date:** 2026-10-19
- **Found by:** Claude, while writing the plan
- **Evidence level:** read from a source (`docs/design/project-design.md`)
- **Affects:** 1.8, 6.1, 6.2, 7.2; Design §5.6, §8.3

## Finding
Design §5.6 says the judge returns binary verdicts for three criteria: faithfulness, correctness and citation support. Design §8.3 makes citation precision and recall deterministic (span overlap, no LLM) and lists only faithfulness and correctness as judge metrics. Both cannot be the spec.

## Evidence
`docs/design/project-design.md` lines for §5.6 and §8.3.

## Consequence
Step 1.8 must pick one. Recommendation: judge faithfulness and correctness only, keep citation checking deterministic. A judged "citation support" criterion would partly duplicate a free, exact check and add a noisier number. The exception is whether a citation *semantically supports* the claim, which the span-overlap check does not measure; decide that explicitly, since it is what the citation-trust bias test probes.

## Resolution
Proposed in `docs/eval-spec.md` §5 (draft, 2026-10-19): two judged criteria, faithfulness (against cited chunks only) and correctness; citation overlap stays deterministic; semantic citation support is covered by faithfulness. Approved by the user 2026-10-19.
