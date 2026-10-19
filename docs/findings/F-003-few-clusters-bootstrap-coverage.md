# F-003: Cluster bootstrap on a small CI subset may under-cover

- **Status:** open
- **Date:** 2026-10-19
- **Found by:** Claude, while writing the plan
- **Evidence level:** hypothesis (not checked)
- **Affects:** 4.2, 4.5, 4.6; Design §8.5

## Finding
The gate resamples contracts. A CI subset sized for speed may hold only a few dozen contracts, and a percentile bootstrap over few clusters is known to produce intervals that are too narrow. That would raise the real false-fail rate above the nominal figure, the opposite of what the gate is supposed to guarantee. Design §8.5 plans a coverage test but does not say it must include small cluster counts.

## Evidence
Not checked. Step 4.2 runs the coverage simulation across cluster counts (about 20 to 40 up to the full dev set). Step 4.6 then measures the real false-alarm rate on dev subsets.

## Consequence
If coverage is poor at the cluster counts the CI subset allows, options are a larger subset, BCa or studentized intervals, or a different decision margin. The chosen subset size must come from this evidence, not from a run-time budget alone.

## Resolution
