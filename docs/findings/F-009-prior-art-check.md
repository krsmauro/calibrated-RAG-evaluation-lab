# F-009: Prior-art check: three differentiators hold, the judge-agreement one must be narrowed

- **Status:** confirmed (user decision pending on the Design §3 wording)
- **Date:** 2026-10-19
- **Found by:** Claude, plan step 1.1 (three research agents; key claims re-checked by Claude, see Evidence)
- **Evidence level:** read from sources (official docs, registries, two papers, one code repo), each dated below; absence of a feature in docs is not proof of absence in code
- **Affects:** 1.1; Design §3 (differentiator and prior-art table), README "Why not just use Ragas?"; 4.x, 7.x, 9.5

## Finding
The four things this project claims to add were checked against each tool's current public docs. **Gate by paired, document-clustered bootstrap CI (2), measured false-alarm rate and power (3), and character-offset span gold with overlap relevance (4) were not found in any of the tools or papers checked.** The first one, as the design words it, is **not unique**: TruLens and Langfuse already compute Cohen's kappa between a judge and human labels. What none of the sources show is a bootstrap confidence interval on that kappa or a blind-labeling protocol. Design §3's one-line differentiator ("existing tools compute scores; this one tells you how much to trust a score, and whether the difference between two scores is real") still holds for the gate and the statistics, but the judge half must say "kappa with bootstrap CIs on blind human labels", not "judge agreement".

| Source (date checked 2026-10-19) | Judge vs human agreement | Statistical gate | Gate false-alarm / power | Span-offset retrieval gold |
| --- | --- | --- | --- | --- |
| Ragas 0.4.3 (released 2026-01-13, Apache-2.0) | Partly: `judge_alignment` metric, raw percent agreement (75.6% to 86.9% in its guide); no kappa, no CI | No: CI guide asserts fixed thresholds (e.g. context_recall >= 0.95) | Not found | No: LLM, string or ID based context precision/recall |
| DeepEval 4.3.1 (2026-10-16, Apache-2.0) | Not found (G-Eval, DAG, custom metrics; compare to humans yourself) | No: per-metric `threshold`, pytest `assert_test`; run comparison appears to be a hosted-platform feature (not opened) | Not found | No: LLM-judged contextual precision/recall |
| promptfoo 0.124.1 (2026-10-08, MIT) | Partly: calibration workflow in its judge guide, raw agreement (">90%"), 30 to 50 examples; no kappa, no CI | No: pass-rate thresholds, `repeat`/`repeat-min-pass` | Not found | No: model-graded context metrics |
| TruLens 2.16.0 (PyPI 2026-10-19, MIT) | **Yes for kappa**: `GroundTruthAggregator.cohens_kappa`, plus Brier, ECE, Spearman and others; guide with golden splits; no bootstrap or CI found; one permutation test for rubric A/B | No: pass/fail is user code | Not found | No: chunk-level `ndcg_at_k`, `precision_at_k`, `recall_at_k`; relevance determination undocumented |
| Langfuse server v4.63.0 / SDK 5.0.2 (2026-10-16, MIT except `ee`) | **Yes for kappa**: Score Analytics lists Cohen's Kappa, F1 and overall agreement for human vs AI scores; example kappa 0.85 as a point estimate; no CI | No, but the closest: `experiment-action` with per-case regression policies ("no approved passing case may regress"); its docs say an aggregate threshold can miss a newly failing case | Not found | No: retrieval evals delegated to Ragas or LLM judges |
| ARES (arXiv:2311.09476 v2, 2024-03-31) | Judges are trained classifiers validated on a human set of about 150 to 300 labels; PPI gives a 95% interval **per system** on each criterion's success rate; interval coverage above 95% reported for real systems | Ranks systems by interval midpoints (Kendall's tau); no test on a difference, no decision rule | Not found (coverage and width of the interval are measured, not a decision rule's error rates) | Passage-level gold only |
| LegalBench-RAG (arXiv:2408.10343 v1, 2024-08-19) | No generation or judge at all | No CIs, no tests; single point estimates | No | Yes: **character-level** precision and recall over spans (confirmed in the code, not defined in the paper); corpus-wide retrieval, not per-document |

Other points worth knowing:
- **Ragas moved** to the `vibrantlabsai` org and has had no release in about nine months; **DeepEval** releases several times a month and recently added a probability-calibrated "Jev" judge model that was not examined in detail. Recheck before publishing any comparison.
- **ARES** uses the same human set to stop judge training and as the PPI rectifier (Sec. 3.2 and 3.3); the paper does not discuss this reuse. Its main ranking experiment uses mock systems with synthetic success rates. PPI is stated at a conceptual level; no estimator formula is given, so any later implementation must come from the PPI paper, not from ARES.
- **LegalBench-RAG** builds its mini benchmark by sorting queries by document so that few documents are ingested; its own code comment says this prevents p-values from being computed. Its code computes precision as retrieved characters inside gold divided by total retrieved characters (retrieved spans are summed, so overlapping retrieved spans would double count; this project counts the union, eval-spec §3.4) and returns 0 when nothing is retrieved, the same convention as eval-spec §3.4. The repository has moved to `zeroentropy-ai/legalbenchrag` and is MIT-licensed.
- **LegalBench-RAG table errors, verified by Claude.** In the arXiv HTML of v1, Table 4's "ALL" row does not equal the mean of its four dataset rows (P@1 prints 2.40 against a recomputed 9.23; R@1 3.37 against 8.48; R@64 76.39 against 63.49), while Tables 5 and 7 do match. Table 6 ("Naive with Cohere reranker") matches Table 5 ("Recursive splitter") almost cell for cell for the ContractNLI, MAUD and CUAD rows (largest difference 1.0, mostly 0.01; the PrivacyQA row was not parsed). The paper's conclusion that the recursive splitter beats the naive chunker rests on the inconsistent row, so that ranking should not be quoted. This is a reading of the HTML rendering, not a cross-check against the PDF or the authors.

## Evidence
- Three research agents read the official docs and papers and returned URLs for every claim; the raw reports are in this session only. Their fetches were partly summaries by a small model, so claims that decide something were re-checked by Claude directly:
  - PyPI/npm: Ragas 0.4.3 (2026-01-13), DeepEval 4.3.1 (2026-10-16), TruLens 2.16.0 (2026-10-19), Langfuse SDK 5.0.2 (2026-10-16), promptfoo 0.124.1 (MIT).
  - Ragas judge-alignment page: contains `judge_alignment`; zero occurrences of kappa, confidence interval, bootstrap. Ragas CI guide: asserts fixed thresholds.
  - TruLens reference page lists `cohens_kappa`; its alignment guide has zero occurrences of bootstrap or confidence interval.
  - Langfuse Score Analytics page lists Cohen's Kappa (6 mentions) and has zero occurrences of bootstrap or confidence interval.
  - ARES text (saved copy): no hypothesis test or false-alarm/power measurement; PPI 95% interval; about 150 human labels.
  - LegalBench-RAG: Table 4 recomputation above; code in `run_benchmark.py` for the character-level metric.
- Not verified: code of any tool (docs only), hosted or paid features, the Ragas blog on judge alignment, the content of TruLens 2.9.0 CI/CD examples, whether TruLens/Langfuse human labels are blind, ARES's PPI estimator and unlabeled-set size, ARES and LegalBench-RAG dataset licenses.

## Consequence
- **User decision needed:** Design §3's table and the README's "Why not just use Ragas?" must not claim judge-human agreement as unique. Suggested wording: "Existing tools can compute judge-human agreement (TruLens and Langfuse report Cohen's kappa); none of those we checked reports a bootstrap CI on it, gates on a paired document-clustered interval, or measures the gate's false-alarm rate and power." I have not edited the design or the README; both stay as written until you decide.
- Cite **Langfuse's `experiment-action`** and **TruLens's `cohens_kappa`** as nearest prior art; reviewers will cite them. The honest framing is that Langfuse treats regression deterministically per case and says averages mislead, which is a different answer to the same problem.
- Cite **LegalBench-RAG** for character-level span metrics and say this project differs by per-document retrieval, a statistical gate and judge calibration. Do not quote its chunker ranking.
- ARES's idea (PPI) stays a stretch goal (Design §8.4); the implementation must follow the PPI paper's estimator, not ARES's description.
- These conclusions are about public documentation on 2026-10-19; DeepEval and Langfuse move fast, so the step that writes the README (9.x) repeats this check.

## Resolution
Open until the user decides the Design §3 and README wording.
