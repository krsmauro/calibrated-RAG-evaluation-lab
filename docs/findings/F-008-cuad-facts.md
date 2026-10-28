# F-008: CUAD facts measured; two thirds of pairs are unanswerable, and the mix is skewed

- **Status:** confirmed
- **Date:** 2026-10-19
- **Found by:** Claude, plan step 1.7
- **Evidence level:** measured (command and output below)
- **Affects:** 1.8 (eval-spec §2, §7), 2.1 to 2.4, 2.10, 4.6, 6.x; Design §5.4, §8.1, §10; findings F-004, F-003

## Finding
Everything the design claimed about CUAD's shape holds except one number: the share of (contract, category) pairs with no gold span is **67.9%**, not "more than a third". Offsets are clean: all 13,823 labels satisfy `text[start:start+len(answer)] == answer`.

| Quantity | Measured | Design said |
| --- | --- | --- |
| Contracts / categories | 510 / 41 | 510 / 41 |
| Pairs (contract x category) | 20,910 | 20,910 |
| Pairs with no gold span | 14,208 (67.9%) | "more than a third" |
| Answerable pairs | 6,702 | n/a |
| Gold spans in total | 13,823 | "more than 13,000" |
| Gold spans per answerable pair | 1: 4,097; 2: 1,049; 3: 476; 4: 475; 5+: 605; max 55 | n/a |
| Labels failing the offset check | 0 of 13,823 | to be confirmed |
| Test split | 102 contracts, 4,182 rows (41 each) | 102 / 4,182 |
| Test pairs unanswerable | 2,938 of 4,182 (70.3%) | n/a |
| Dev (all train) | 408 contracts, 16,728 pairs, 11,270 unanswerable (67.4%), 5,458 answerable | n/a |
| Contract length, chars | min 645, median 33,143, p95 164,154, max 338,211 | n/a |
| Contract length, whitespace words | median 5,006, p95 25,314, max 47,733 | n/a |
| Gold span length, chars | median 196, p75 365, p95 759, max 3,884; 320 spans of 5 chars or fewer | n/a |

Other facts that the pipeline and the spec depend on:
- **The train file has a different unit.** `train_separate_questions.json` holds 22,450 rows because it has one question per answer span (this is the "train rows" number on Hugging Face). The unit this project uses is the (contract, category) pair from `CUADv1.json`, filtered to the 408 train titles. `test.json` has the standard one-row-per-pair shape.
- **Splits are clean.** Train and test titles do not overlap, their union is all 510 titles, contexts are byte-identical to the full file, and `test.json` labels equal the full file's labels (as sets: 382 questions list the same answers in a different order).
- **The category mix is skewed.** Document Name, Parties, Agreement Date and Governing Law are 28.7% of all answerable pairs (510, 509, 470, 437 of 6,702). Document Name and Parties are answerable for essentially every contract (0% unanswerable), and their gold spans are short (many under 5 characters, such as "Agent") and usually near the start of a contract.
- **Merging gold spans matters.** 264 pairs have gold spans that overlap each other, and 2,605 answerable pairs (38.9%) have two or more spans, so fractional recall is the common case.
- **Spans have no leading or trailing whitespace** (0 of 13,823), so a chunk that overlaps a span's first or last character overlaps a non-whitespace character.
- `answer_start` is stored as a string in `train_separate_questions.json` and as an integer-like value elsewhere; the adapter must convert and validate it.
- **Source moved.** The Atticus Project GitHub org is now `The-Atticus-Project`; the Hugging Face script's old URL only works through a redirect. The download in `scripts/fetch_cuad.py` is pinned to commit `7aad649183846688381a147eeb3601aff590fe4a` (last change to `data.zip`, 2021-03-11).
- **License.** The dataset's own page (atticusprojectai.org/cuad) lists CC BY 4.0, and the Hugging Face loader's license string reads "CUAD is licensed under the Creative Commons Attribution 4.0 (CC BY 4.0) license." The GitHub repo has no LICENSE file (the API returns 404), so the page is the primary source for step 1.10.

## Evidence
`make data` (downloads `data.zip`: 18,309,308 bytes, sha256 `f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a`) then `uv run python -I scripts/cuad_facts.py`, which reads the zip in memory and prints every number above. Run on 2026-10-19.

## Consequence
- **Abstention is the majority case.** Two thirds of queries have the answer "not present", so a system that always abstains scores about 68% presence accuracy. Presence accuracy alone is a weak headline; abstention precision and recall (eval-spec §4) matter more than the design implied. Report the always-abstain baseline next to every presence accuracy.
- **Fewer answerable queries than 20,910 suggests.** Retrieval metrics use 6,702 answerable pairs overall: 5,458 in dev and 1,244 in test. A CI subset of 60 dev contracts has about 60 x 41 x 32.6% = 800 answerable queries. Plan the power study on answerable counts, not on 41 queries per contract.
- **Test is slightly more unanswerable than dev** (70.3% vs 67.4%), so absolute presence and abstention numbers are not directly comparable across the two splits.
- **F-004 gets more concrete.** A quarter or more of the answerable queries are easy by construction (Document Name, Parties, Agreement Date, Governing Law). The mean recall may be high because of them. Step 2.10 must report retrieval metrics per category, and the saturation rule in eval-spec §6.1 should be read together with that breakdown. The spec is not changed by this finding; the rule runs on dev means as written.
  - Note (2026-10-28, measured in step 2.10): for dense retrieval (S2, C1) the opposite holds for three of the four. Recall@5 on dev: Parties 0.151, Document Name 0.208, Agreement Date 0.239 (among the hardest of 41 categories), Governing Law 0.758 (among the easiest); overall 0.489. They are frequent but not easy for S2. Why is a hypothesis, not checked: the templated question matches a clause's wording, not a header of names and dates, and Parties labels often mark several short mentions spread through the contract, so fractional recall is low. A lexical strategy may behave very differently on them (step 3.9).
- **F-003 input.** Dev has 408 clusters; a CI subset of a few dozen contracts is what the coverage study (step 4.2) must test.
- No tokenizer-based claims yet: contract length in tokens is not measured, only characters and whitespace words (chars/4 gives a median of about 8,300 tokens). Measure it once the tokenizer is chosen (ADR 0004, step 4.9).

## Resolution
Facts recorded. The eval-spec carries a dated note (amendment log) pointing here.
