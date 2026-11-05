# ADR 0004: Span-overlap relevance, and a budget counted in words for comparing chunkers

- **Status:** accepted
- **Date:** 2026-11-05
- **Step:** 4.9. It records the relevance rule and metric definitions fixed in `docs/eval-spec.md` §2 and §3 (approved 2026-10-19, built in step 2.9), and it makes the one choice §3.4 left to this step: the unit of the retrieved budget.

## Context
CUAD's gold labels are character spans in the contract text (13,823 spans, F-008), not chunk ids. Chunk ids belong to one chunker: re-chunking renames every chunk, so labels keyed on chunk ids would have to be redone for each chunker, and two chunkers could never be scored against the same gold. Two questions follow:

1. When does a retrieved chunk count as relevant to a gold span?
2. How are chunkers compared fairly? recall@k rewards big chunks (Design §5.2), and dev shows it: at fixed k, 256-token windows beat 199-token ones on recall@5 (S1 0.560 against 0.530, S3 0.576 against 0.554) while retrieving less gold text per word (F-013).

The spec fixed the rules for question 1 and the metrics for question 2. For the budget it set only the requirements: "one fixed, version-pinned, provider-neutral tokenizer applied identically to every strategy and chunker (not any embedding model's own)". Until now `scripts/measure_chunkers.py` counted the budget in whitespace-separated words as a stand-in, and F-013's numbers were measured that way.

## Decision
1. **Relevance is span overlap in one coordinate system.** Chunks and gold spans are half-open character offsets `[start, end)` into the raw text. Under the primary rule R1, a chunk is relevant if it overlaps a gold span by at least one character. R2 asks for an overlap of at least half the shorter of the span and the chunk, and is a sensitivity check only. A query's gold spans are merged before counting. Duplicate chunk ids are dropped, and the first occurrence keeps its rank. Fewer than k results are scored as returned, never padded. Metrics are computed per query on answerable queries only, then averaged (`harness/metrics/retrieval.py`; eval-spec §2, §3).
2. **Strategies over the same chunks are compared on recall@k, hit@k and MRR@k**, and recall@5 gates (eval-spec §6.1). **Chunkers are compared on character precision and recall at a retrieved budget B** (§3.4).
3. **B is counted in whitespace-separated words**: `word_ends` in `harness/metrics/retrieval.py`, Python's `\S+` on str, so any Unicode whitespace (no-break spaces included) separates words. The budgets are B ∈ {256, 512, 1024, 2048} words. A word is about 1.38 bge tokens on CUAD.

## Measurements
**R1 against R2 for the strategies.** `uv run python scripts/measure_relevance.py 20261104T194821Z-4eb392 20261104T194802Z-31d733 20261104T194807Z-69af36 20261104T194846Z-bce2cd` rescores the stored S1 to S4 dev runs (`docs/results.md`; 5,458 answerable queries, 408 contracts) under both rules. Its R1 values equal the stored ones. Paired differences against S3 are given with 95% document-clustered intervals (seed 20261104):

| recall@5 | S3 | S1 - S3 | S2 - S3 | S4 - S3 | Order |
| --- | --- | --- | --- | --- | --- |
| R1 | 0.5758 | -0.0158 [-0.0265, -0.0054] | -0.0874 [-0.0973, -0.0775] | -0.0152 [-0.0249, -0.0058] | S3 > S4 > S1 > S2 |
| R2 | 0.5528 | -0.0153 [-0.0257, -0.0050] | -0.0902 [-0.1004, -0.0801] | -0.0183 [-0.0279, -0.0085] | S3 > S1 > S4 > S2 |

R2 lowers every strategy by 2.2 to 2.6 points. Every gate outcome against S3 is the same under both rules (each a Fail). Only S1 and S4 swap places, and they are indistinguishable under either rule: S4 - S1 is +0.0005 [-0.0116, +0.0127] under R1 and -0.0029 [-0.0151, +0.0094] under R2. On hit@5 and MRR@10 the order is the same under both rules.

**Words against model tokens for the budget.** Ad hoc count over the 510 CUAD contracts (scratch script, not a command): 4,009,206 words and 5,529,156 bge tokens, so 1.38 tokens per word (median contract 1.34, range 1.18 to 2.53). The longest word is 143 characters; words over 40 characters hold 0.38% of the text, so no long run without spaces distorts a word count. Then the chunker comparison of step 3.9 was rerun with the budget counted in bge WordPiece tokens: `uv run python scripts/measure_chunkers.py budget --unit bge RUN_C1_199 RUN_C1_256 RUN_C2`, with the run ids of the chunker row in `docs/results.md`. Character recall, paired differences, 95% document-clustered intervals:

| Budget | Effect | S1 words | S1 bge | S2 words | S2 bge | S3 words | S3 bge |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 256 | size | +0.0225 [+0.0136, +0.0313] | +0.0170 [+0.0077, +0.0261] | +0.0472 [+0.0370, +0.0577] | +0.0343 [+0.0241, +0.0449] | +0.0386 [+0.0290, +0.0484] | +0.0287 [+0.0190, +0.0383] |
| 256 | structure | +0.0065 [-0.0026, +0.0159] | +0.0040 [-0.0053, +0.0134] | +0.0357 [+0.0248, +0.0469] | +0.0453 [+0.0340, +0.0564] | +0.0257 [+0.0160, +0.0356] | +0.0272 [+0.0172, +0.0372] |
| 512 | size | +0.0089 [-0.0002, +0.0177] | +0.0160 [+0.0067, +0.0252] | +0.0329 [+0.0227, +0.0430] | +0.0360 [+0.0267, +0.0456] | +0.0238 [+0.0146, +0.0334] | +0.0287 [+0.0190, +0.0383] |
| 512 | structure | +0.0127 [+0.0039, +0.0217] | +0.0034 [-0.0056, +0.0125] | +0.0349 [+0.0244, +0.0453] | +0.0353 [+0.0248, +0.0456] | +0.0223 [+0.0129, +0.0315] | +0.0172 [+0.0075, +0.0266] |
| 1,024 | size | +0.0092 [+0.0005, +0.0179] | +0.0098 [+0.0011, +0.0186] | +0.0316 [+0.0219, +0.0413] | +0.0289 [+0.0188, +0.0392] | +0.0163 [+0.0073, +0.0251] | +0.0176 [+0.0086, +0.0267] |
| 1,024 | structure | +0.0153 [+0.0068, +0.0240] | +0.0168 [+0.0081, +0.0255] | +0.0289 [+0.0187, +0.0389] | +0.0293 [+0.0191, +0.0394] | +0.0219 [+0.0134, +0.0305] | +0.0250 [+0.0158, +0.0343] |

"Size" is C1 at 199 minus C1 at 256 (the script prints the opposite sign); "structure" is C2 minus C1 at 199. 5,458 queries and 408 contracts; seed 20261104; not corrected for the 36 comparisons; values as the script prints them. The word columns are the numbers already in `docs/results.md`, reproduced exactly by the same command without `--unit`. S3's size effect in tokens is the same to four decimals at 256 and 512; it differs at the fifth (-0.028686 and -0.028679), a coincidence, checked.

What holds in both units: for S2 and S3, smaller windows and C2's heading cuts each raise character recall at every budget, with intervals above zero. What depends on the unit: (1) F-013 said size has the larger share at the smallest budget. In tokens, structure is the larger share for S2 (+0.0453 against +0.0343) and about even for S3 (+0.0272 against +0.0287). (2) S1's structure effect is small in both units. Its interval clears zero at 512 and 1,024 words but only at 1,024 tokens. (3) S1's size effect at 512 clears zero in tokens but not in words.

## Alternatives considered
- **Chunk-id relevance** (label which chunks answer each query). Loses: every chunker would need its own labels, chunkers could not be compared on one gold set, and CUAD ships spans, not chunk labels.
- **"At least 50% of the gold span" as the rule** (the design's second option, §5.2). Loses: a span longer than two chunks can never be reached by one chunk. R2's `min(span, chunk)` form fixes that and is kept as the sensitivity check. R1 needs no parameter.
- **recall@k for comparing chunkers.** Loses: it rewards bigger chunks (the fixed-k numbers above).
- **Budget in the bge model's WordPiece tokens** (already installed, used above as the sensitivity check). Loses on the spec's rule, for a reason the table makes concrete. C1's windows are counted in these tokens, so a budget in the same unit lines up with C1's window edges: at B = 256 a 256-token C1 fills the budget with one whole chunk, and every other chunker is cut. The unit would also be tied to a model the project swaps (step 4.10 compares embedders).
- **An LLM provider's tokenizer** (for example OpenAI's `o200k_base` through `tiktoken`). Loses: not provider-neutral, and the generator's provider is not chosen yet (D1). It adds a dependency whose vocabulary files are downloaded on first use, and its counts describe one vendor's models. When a budget has to mean "what fits in the generator's prompt" (Phase 5), the generator's own token counts are what matter, and they are measured there.
- **Characters.** Not measured. Neutral and simpler still, but a budget cut at a character boundary splits words. The spec states B in tokens, and words are the coarsest unit that still behaves like one.

## Consequences
- One gold set serves every chunker, and a chunker change needs no relabeling.
- R1 is generous: one shared character makes a hit, and big chunks hit more often. That is why chunkers are compared on the budget metrics. The R2 check is one command (`scripts/measure_relevance.py`) and its result is in `docs/results.md`. The gate uses R1 only.
- Budget results are stated in words. 256 words are about 350 bge tokens on CUAD. Another tokenizer's count differs, so do not mix them with Phase 5's prompt budgets, which will be counted in the generator's tokens.
- The chunker conclusions that hold in both units are the ones F-013 states without qualification. The size-versus-structure split at the smallest budget, and S1's small effects, are reported as depending on the unit (note in F-013).
- `ragcalibrate run` does not store character metrics: only `scripts/measure_chunkers.py` computes them. If decision D8 makes character recall@512 gate a chunker change, the runner must store it, counted with `word_ends`.
- Revisit for a corpus whose text does not separate words with spaces, such as Chinese or Japanese, where a "word" is undefined. QASPER (Phase 9) is English, so nothing changes there.
