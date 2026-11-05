# F-013: chunker C2 beats C1 at a fixed retrieved budget on CUAD dev, not at fixed k; both its smaller chunks and its cut points contribute

- **Status:** confirmed on dev (provisional: test split not run); the cause was measured in step 3.9 (2026-11-05): size and structure both contribute
- **Date:** 2026-10-28
- **Found by:** Claude, plan step 3.4
- **Evidence level:** measured (commands and output below), including the size-matched control from step 3.9
- **Affects:** 3.4, 3.9, 4.x (which chunker the gate runs on), README step 4; Design §5.2, §7, §16

## Finding
C2 (structure-aware: cut before headings and clause numbers, sections packed up to 256 tokens, C1 inside longer sections) retrieves more gold text per word retrieved than C1 (fixed 256-token windows, 32 overlap), for all three strategies tried and at every budget. Character recall at a 256-word budget on 5,458 answerable dev queries: S1 0.2913 to 0.3203, S2 0.2381 to 0.3211, S3 0.3068 to 0.3711; better on more queries than worse in every case (S2: 1,172 better, 512 worse), and above C1 in 36 of 41 categories for S2 and S3 (29 for S1). At fixed k the picture reverses or flattens (recall@5: S1 0.560 to 0.539, S2 0.488 to 0.489, S3 0.576 to 0.571), as expected: C2's chunks are smaller (197 tokens on average against 254), and recall@k rewards big chunks (Design §5.2). Structurally, 93.7% of dev gold spans lie wholly inside one C2 chunk against 87.0% for C1, although C2 cuts more often. **Answered in step 3.9:** smaller chunks help at a fixed budget on their own, and C2 still wins against a C1 cut to its mean size. At 256 words, size is most of C2's gain (57% for S2, 60% for S3, 78% for S1); at 512 and 1,024 words size and structure are about even. Structure's gain at a matched mean size excludes zero for S2 and S3 at every budget and for S1 at 512 and 1,024 words, not at 256 (section "Size against structure" below).

## Evidence
- **Structure:** `uv run python scripts/measure_chunkers.py structure` (CUAD zip and tokenizer only), all 510 contracts, window 256 tokens, overlap 32; spans are the 11,180 dev gold spans:

  | | chunks | tokens per chunk: mean, median, p5, p95 | dev gold spans wholly inside one chunk |
  | --- | --- | --- | --- |
  | C1 | 24,872 | 254, 256, 255, 256 | 9,728 (87.0%) |
  | C2 | 29,380 | 197, 222, 58, 256 | 10,480 (93.7%) |

  C2 finds a median of 61 headings per contract; 30 contracts have none and get exactly C1's chunks. 477 of 510 contracts have at least one section over 256 tokens, and those sections hold 42.5% of all tokens: almost half of the text is still cut by C1's rule, inside C2.
- **Retrieval at fixed k:** `uv run ragcalibrate run --strategy fts|dense|hybrid` with `--chunker-id c2v1:bge-small-en-v1.5@5c38ec7c405e:size=256:overlap=32` and without (C1). Hybrid uses `rrf_k` 10 and `fusion_depth` 100, chosen on dev with C1 (step 3.2) and not retuned for C2. The C1 runs repeat the committed baselines exactly (identical per query).

  | | recall@5 C1, C2 | MRR@10 C1, C2 |
  | --- | --- | --- |
  | S1 fts | 0.560, 0.539 | 0.455, 0.435 |
  | S2 dense | 0.488, 0.489 | 0.393, 0.405 |
  | S3 hybrid | 0.576, 0.571 | 0.477, 0.481 |

- **Retrieval at a fixed budget:** `uv run python scripts/measure_chunkers.py budget runs/c1-<strategy>-dev-3.4.json runs/c2-<strategy>-dev-3.4.json`. Character precision and recall at B words of the ranked list (docs/eval-spec.md §3.4). The budget is counted in whitespace-separated words, a stand-in until step 4.9 fixes the tokenizer; it is the same for both chunkers. Values as printed (four decimals); better and worse are per query on character recall:

  | | B | char recall C1, C2 | change | better, worse | char precision C1, C2 |
  | --- | --- | --- | --- | --- | --- |
  | S1 fts | 256 | 0.2913, 0.3203 | +0.0290 | 907, 636 | 0.0769, 0.0845 |
  | | 512 | 0.4173, 0.4389 | +0.0216 | 889, 692 | 0.0577, 0.0602 |
  | | 1024 | 0.5479, 0.5723 | +0.0244 | 835, 662 | 0.0406, 0.0410 |
  | S2 dense | 256 | 0.2381, 0.3211 | +0.0830 | 1,172, 512 | 0.0685, 0.0898 |
  | | 512 | 0.3538, 0.4216 | +0.0678 | 1,124, 551 | 0.0524, 0.0622 |
  | | 1024 | 0.4764, 0.5368 | +0.0605 | 1,015, 560 | 0.0375, 0.0409 |
  | S3 hybrid | 256 | 0.3068, 0.3711 | +0.0643 | 1,164, 599 | 0.0857, 0.1036 |
  | | 512 | 0.4381, 0.4843 | +0.0461 | 1,008, 623 | 0.0645, 0.0693 |
  | | 1024 | 0.5668, 0.6050 | +0.0382 | 894, 606 | 0.0438, 0.0452 |

  Runs keep their top 10 chunks; at 1,024 words the top 10 holds fewer words than the budget for 140 to 298 queries per run, more often for C2 (smaller chunks), which if anything understates C2 there. Eval-spec §8's 2,048 is beyond what a top 10 holds.
- **Overlap is not the explanation:** C1's chunks overlap by 32 tokens, so two neighbours retrieved together spend budget on the same words twice; C2's packed chunks do not overlap. Measured on the same runs (session scratchpad script, not committed): the share of the budget spent on words already counted is, at 256 / 512 / 1,024 words, 1.3% / 2.2% / 4.0% for C1 dense against 0.3% / 0.6% / 1.1% for C2 (hybrid: 1.3% / 2.1% / 3.8% against 0.3% / 0.5% / 1.0%), far below the recall gaps.
- **Per category** (char recall at 256 words, C2 minus C1; session scratchpad script, not committed): S2 above C1 in 36 of 41 categories, largest gains Renewal Term +0.271 (n = 150), Uncapped Liability +0.256 (n = 98), Cap On Liability +0.194 (n = 231); S3 above in 36, below most on Revenue/Profit Sharing -0.074 (n = 131); S1 above in 29, below in 11, most on Non-Disparagement -0.068 (n = 31). The front-matter categories move little (Parties and Document Name by at most 0.008 for S2 and S3; Agreement Date +0.013 and +0.018, Effective Date +0.038 and +0.070), as expected: a contract's opening is usually one long section, which C2 hands to C1.
- **What would settle the open question:** ingest a C1 with windows of about 200 tokens (C2's mean is 197) and compare it with C2 at the same budgets. If C2 still wins, the gain is structure; if not, it is size. Needs a size parameter on `scripts/ingest.py` (fixed at 256 now). Done in step 3.9, below.

## Size against structure (step 3.9, 2026-11-05)
- **Setup:** a third chunking, C1 with 199-token windows (overlap 32), the window whose mean chunk size (197.6 tokens) is closest to C2's (197.2). It matches C2's mean, not its spread: C1 at 199 runs from 198 tokens (p5) to 199 (p95), C2 from 58 to 256. So "structure" below means where C2 cuts plus the uneven lengths that follows from it. 82.8% of dev gold spans lie wholly inside one C1-at-199 chunk, against 93.7% for C2 and 87.0% for C1 at 256 (`scripts/measure_chunkers.py structure --c1-size 199`).
- **Runs:** S1 to S3 on each of the three chunkings, on a clean checkout of 42c2c9f, through `uv run ragcalibrate run configs/<s>-c1-199.yaml`, `configs/<s>.yaml` and `configs/<s>-c2.yaml`; run ids in `docs/results.md`. The C1-at-256 runs are identical per query to the step 3.9 part 1 runs, and C1 at 256 and C2 give exactly the values in the tables above, which were measured on an uncommitted tree.
- **Fixed budget:** `uv run python scripts/measure_chunkers.py budget RUN_C1_199 RUN_C1_256 RUN_C2`, per strategy, pairs both other runs with C1 at 199. Character recall; 95% intervals from the paired document-clustered bootstrap (408 contracts, 10,000 resamples, seed 20261104); better and worse are queries. The script prints C1 at 256 minus C1 at 199; the size column flips that sign so that both columns read as gains:

  | | B | char recall C1 256, C1 199, C2 | size: C1 199 minus C1 256 (better, worse) | structure: C2 minus C1 199 (better, worse) | char precision C1 256, C1 199, C2 |
  | --- | --- | --- | --- | --- | --- |
  | S1 fts | 256 | 0.2913, 0.3138, 0.3203 | +0.0225 [+0.0136, +0.0313] (924, 816) | +0.0065 [-0.0026, +0.0159] (892, 727) | 0.0769, 0.0814, 0.0845 |
  | | 512 | 0.4173, 0.4262, 0.4389 | +0.0089 [-0.0002, +0.0177] (861, 828) | +0.0127 [+0.0039, +0.0217] (900, 715) | 0.0577, 0.0592, 0.0602 |
  | | 1024 | 0.5479, 0.5570, 0.5723 | +0.0092 [+0.0005, +0.0179] (786, 786) | +0.0153 [+0.0068, +0.0240] (843, 674) | 0.0406, 0.0415, 0.0410 |
  | S2 dense | 256 | 0.2381, 0.2853, 0.3211 | +0.0472 [+0.0370, +0.0577] (1,104, 757) | +0.0357 [+0.0248, +0.0469] (1,114, 713) | 0.0685, 0.0785, 0.0898 |
  | | 512 | 0.3538, 0.3866, 0.4216 | +0.0329 [+0.0227, +0.0430] (1,031, 751) | +0.0349 [+0.0244, +0.0453] (1,046, 659) | 0.0524, 0.0575, 0.0622 |
  | | 1024 | 0.4764, 0.5079, 0.5368 | +0.0316 [+0.0219, +0.0413] (957, 738) | +0.0289 [+0.0187, +0.0389] (988, 661) | 0.0375, 0.0393, 0.0409 |
  | S3 hybrid | 256 | 0.3068, 0.3454, 0.3711 | +0.0386 [+0.0290, +0.0484] (1,093, 862) | +0.0257 [+0.0160, +0.0356] (1,100, 754) | 0.0857, 0.0948, 0.1036 |
  | | 512 | 0.4381, 0.4620, 0.4843 | +0.0238 [+0.0146, +0.0334] (982, 795) | +0.0223 [+0.0129, +0.0315] (982, 720) | 0.0645, 0.0675, 0.0693 |
  | | 1024 | 0.5668, 0.5831, 0.6050 | +0.0163 [+0.0073, +0.0251] (832, 728) | +0.0219 [+0.0134, +0.0305] (865, 640) | 0.0438, 0.0453, 0.0452 |

  The two columns add up to C2's gain over C1 at 256 (S2 at 256 words: 0.0472 + 0.0357 = 0.0830). Size's share of that gain at 256 / 512 / 1,024 words: S1 78% / 41% / 38%, S2 57% / 49% / 52%, S3 60% / 52% / 43%. The 18 intervals are not corrected for multiplicity; 8 of the 9 structure intervals exclude zero, all on the positive side, which chance alone would not produce.
- **Fixed k, for contrast:** recall@5 C1 256, C1 199, C2: S1 0.560, 0.530, 0.539; S2 0.488, 0.483, 0.489; S3 0.576, 0.554, 0.571 (exact means in the 3.9 Done note). Paired intervals, computed ad hoc with `stats.bootstrap.paired_cluster_bootstrap` over `RunStore.queries` (same seed; `ragcalibrate compare`, step 4.4, makes this a command): bigger windows (C1 256 minus C1 199) S1 +0.030 [+0.022, +0.039], S2 +0.005 [-0.005, +0.016], S3 +0.022 [+0.012, +0.031]; structure (C2 minus C1 199) S1 +0.009 [+0.0004, +0.018], S2 +0.006 [-0.005, +0.016], S3 +0.017 [+0.007, +0.027]. So at fixed k, bigger chunks help full-text and hybrid search but not dense search, and at a matched size C2 is also ahead at fixed k for S1 (barely) and S3.
- **Caveats:** dev only; S3's fusion parameters were tuned on C1 at 256 and not retuned (if anything this favours C1 at 256); the budget is in whitespace words, the unit step 4.9 fixed (ADR 0004; see the note on the unit below); C2's heading rules were written by reading the text of all 510 contracts (no labels, no scores).

## Consequence
- Step 3.4 says to report if C2 does not help; it does help on dev at a fixed budget, the comparison the spec requires for chunkers. Not yet claimed as a structure effect.
- Step 3.9 (C1 versus C2): run the size-matched C1 control above; report char precision and recall at a budget, not recall@k, with the tokenizer from 4.9 once it exists; consider retuning S3's fusion parameters for C2. Strategy comparisons stay at C1 until 3.9 decides which chunker the gate runs on.
- Decided in step 3.9 (2026-11-05): **the strategies and the retrieval gate stay on C1 at 256.** Every baseline, step 4.10's design and the gate's primary metric (recall@5, eval-spec §6.1) are on it, and at fixed k it is level with or above C2. C2 is the better chunker when retrieved text is spent against a budget, which is what a generator does with its context: worth considering when Phase 5 fixes what `/answer` retrieves, and a natural candidate change for a gate demo.
- A chunker change sent through the gate as eval-spec §6.1 stands would be judged on recall@5, which §3.4 says not to use for chunkers: a chunker going from 256 to 199 tokens would fail on S1 and S3 on all of dev (recall@5 intervals [-0.039, -0.022] and [-0.031, -0.012], both entirely below zero and reaching past δ = 0.02, §6.4) while retrieving more gold text per word. Raised for the user as decision D8 in the plan.
- The heading rules were written by reading contract text (all 510 contracts, no labels and no retrieval scores); every retrieval number above is dev only.

## Resolution
2026-11-05, step 3.9: the open question (size or structure) is answered by the size-matched control: both, size the larger share at 256 words and about even at 512 and 1,024 (section above). The finding itself, C2 ahead of C1 at a fixed budget, stands on dev; the test split has not been run. What it means for the gate is decision D8.

Note (2026-11-05, step 4.9, ADR 0004): the budget unit is fixed as whitespace-separated words, so the tables above stand as measured. As a sensitivity check, the same runs were scored with the budget counted in bge WordPiece tokens (`uv run python scripts/measure_chunkers.py budget --unit bge RUN_C1_199 RUN_C1_256 RUN_C2`; full table in ADR 0004). **Holds in both units:** for S2 and S3, smaller windows and C2's cut points each raise character recall at every budget, with intervals above zero. **Depends on the unit:** (1) "size the larger share at 256 words" is a word-count result. At 256 bge tokens structure is the larger share for S2 (+0.0453 against +0.0343) and about even for S3 (+0.0272 against +0.0287). (2) S1's structure effect is small either way. Its interval clears zero at 512 and 1,024 words, but only at 1,024 tokens. (3) S1's size effect at 512 clears zero in tokens (+0.0160 [+0.0067, +0.0252]), not in words. State the size-against-structure split as unit-dependent; the claim that both contribute for S2 and S3 does not depend on the unit.
