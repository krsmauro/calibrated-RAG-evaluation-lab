# F-013: chunker C2 beats C1 at a fixed retrieved budget on CUAD dev, not at fixed k; size and structure are not yet separated

- **Status:** confirmed on dev (provisional: no confidence interval yet, test split not run); the cause is open
- **Date:** 2026-10-28
- **Found by:** Claude, plan step 3.4
- **Evidence level:** measured (commands and output below); the size-versus-structure question is a hypothesis
- **Affects:** 3.4, 3.9, 4.x (which chunker the gate runs on), README step 4; Design §5.2, §7, §16

## Finding
C2 (structure-aware: cut before headings and clause numbers, sections packed up to 256 tokens, C1 inside longer sections) retrieves more gold text per word retrieved than C1 (fixed 256-token windows, 32 overlap), for all three strategies tried and at every budget. Character recall at a 256-word budget on 5,458 answerable dev queries: S1 0.2913 to 0.3203, S2 0.2381 to 0.3211, S3 0.3068 to 0.3711; better on more queries than worse in every case (S2: 1,172 better, 512 worse), and above C1 in 36 of 41 categories for S2 and S3 (29 for S1). At fixed k the picture reverses or flattens (recall@5: S1 0.560 to 0.539, S2 0.488 to 0.489, S3 0.576 to 0.571), as expected: C2's chunks are smaller (197 tokens on average against 254), and recall@k rewards big chunks (Design §5.2). Structurally, 93.7% of dev gold spans lie wholly inside one C2 chunk against 87.0% for C1, although C2 cuts more often. **Open:** smaller chunks may help at a fixed budget on their own (retrieval can pick more selectively), so part of the gain may be size rather than structure; a C1 with windows near C2's mean size would separate the two.

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
- **What would settle the open question:** ingest a C1 with windows of about 200 tokens (C2's mean is 197) and compare it with C2 at the same budgets. If C2 still wins, the gain is structure; if not, it is size. Needs a size parameter on `scripts/ingest.py` (fixed at 256 now).

## Consequence
- Step 3.4 says to report if C2 does not help; it does help on dev at a fixed budget, the comparison the spec requires for chunkers. Not yet claimed as a structure effect.
- Step 3.9 (C1 versus C2): run the size-matched C1 control above; report char precision and recall at a budget, not recall@k, with the tokenizer from 4.9 once it exists; consider retuning S3's fusion parameters for C2. Strategy comparisons stay at C1 until 3.9 decides which chunker the gate runs on.
- The heading rules were written by reading contract text (all 510 contracts, no labels and no retrieval scores); every retrieval number above is dev only.

## Resolution
