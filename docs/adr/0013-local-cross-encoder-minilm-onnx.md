# ADR 0013: Local cross-encoder ms-marco-MiniLM-L6-v2 for S4, run with ONNX Runtime

- **Status:** accepted
- **Date:** 2026-10-28
- **Step:** 3.3 (S4: cross-encoder rerank)

## Context
S4 reranks S3's top N with a local cross-encoder (Design §7), so retrieval evals stay free, deterministic and runnable in CI without keys. ADR 0011 set the pattern for local models: the model author's own ONNX export, pinned to a commit and checked by sha256, run with ONNX Runtime and `tokenizers` (no PyTorch), checked once against the reference implementation. A cross-encoder scores every (question, chunk) pair with a full transformer pass, so unlike the embedder its cost is paid per query, N times, and it is the latency S4 must report.

Facts, read from the model repo at commit `233902d25c440f23af6f7d6e94d2946bac0bee0a` on 2026-10-28: Apache 2.0; BERT, 6 layers, hidden size 384 (MiniLM); one output logit; the configured activation is the identity (`sbert_ce_default_activation_function`), so the score is the raw logit; 512-token context for the pair; `onnx/model.onnx` is 91,011,230 bytes, sha256 `5d3e70fd...4d4a`. Its `tokenizer.json` is byte-identical to bge-small-en-v1.5's (sha256 `d241a60d...5c66`, BERT uncased WordPiece). Trained on MS MARCO passage ranking: short web-search queries against web passages.

## Decision
Use `cross-encoder/ms-marco-MiniLM-L6-v2` pinned to commit `233902d2...`, run with ONNX Runtime (CPU) and `tokenizers`, as `service/rerank.py`. The pair is encoded as `[CLS] question [SEP] chunk [SEP]` and cut longest side first past 512 tokens, as sentence-transformers does. The reranker id `ms-marco-MiniLM-L6-v2@233902d25c44` comes back in every reranked response and is recorded with the run. One `Reranker` is loaded in the service's lifespan and called through `asyncio.to_thread`. The question is sent as is, CUAD template included, for the same reason as for S1 and S2 (README, step 6): the service must not know the eval set's template.

On CUAD dev, with the question as sent, it lowers recall (finding F-012), and so do the two larger cross-encoders tried below. It is chosen anyway because it is the fastest by a factor of 3 to 6 and no worse than the others, and because the template, not the model, is the main cause: on all of dev the same model given only the question's specific part (after "Details:") raises recall@5 by 8.6 points at the top 20, where with the whole question it loses 1.9. Whether the eval set's question should change is decision D7 for the user, not something the service may do on its own.

## Evidence
All on an Apple M5 (10 cores, 24 GB), macOS 27, onnxruntime 1.31.1, tokenizers 0.23.3.

- **Same scores as the reference implementation.** 197 (question, chunk) pairs from CUAD dev (S3's top 10 for 10 random queries, plus 10 questions against 10 random chunks each) scored with sentence-transformers 6.2.0 `CrossEncoder` (torch 2.15.0, transformers 5.21.0, same commit, run once in a throwaway environment outside the project) and with this code: maximum absolute difference 1.05e-5 on logits between -11.0 and -2.0, and the same order in all 20 groups. `tests/unit/test_rerank.py` pins three reference values so CI keeps checking this without torch.
- **Determinism.** The same pairs scored twice are bitwise identical. A pair scored alone versus inside a padded batch differs by at most 2.4e-6.
- **Length.** CUAD question plus C1 chunk: median 310 tokens, maximum 330 on the 197 pairs, so nothing is cut.
- **Cost.** About 11 ms per pair, flat across batch sizes 8 to 64 (86 to 90 pairs per second): reranking the top 10 takes about 0.11 s per query, the top 20 about 0.23 s, the top 100 about 1.1 s. Through the service, one request at a time on 500 dev queries, S4 at depth 10 takes 114 ms at the median against S3's 10 ms (`docs/results.md`).

## Alternatives considered
Each was piloted on the same 300 random answerable dev queries (seed 33, 216 contracts), reranking S3's top 10 and top 20 and scoring the top 10; S3 alone scores recall@5 0.587 on this sample. Recall@5, and the change against S3:

| Model | Size | ms per pair | Top 10 | Top 20 |
| --- | --- | --- | --- | --- |
| `cross-encoder/ms-marco-MiniLM-L6-v2` (chosen) | 91 MB, 6 × 384 | 11.9 | 0.563 (-2.5) | 0.563 (-2.4) |
| `mixedbread-ai/mxbai-rerank-xsmall-v1` (Apache 2.0, DeBERTa-v3) | 284 MB, 12 × 384 | 39.1 | 0.568 (-2.0) | 0.553 (-3.4) |
| `BAAI/bge-reranker-base` (MIT, XLM-RoBERTa) | 1.1 GB, 12 × 768 | 70.1 | 0.521 (-6.7) | 0.499 (-8.8) |

- **mxbai-rerank-xsmall-v1.** Half a point above MiniLM at the top 10 (on 300 queries, well within noise) and still 2.0 below S3, worse than MiniLM at the top 20, and 3.3 times slower.
- **bge-reranker-base.** The largest of the three and the worst: 6.7 points below S3 at the top 10, 8.8 at the top 20, at 5.9 times MiniLM's cost per pair (a top-20 rerank would take about 1.4 s per query) and a 1.1 GB download in every CI job. Its XLM-RoBERTa tokenizer also turns the same pair into more tokens (up to 499 on the first query, against 312).
- **sentence-transformers with PyTorch.** Rejected for the embedder in ADR 0011 (install weight, CUDA wheels in CI); the scores are the same, so nothing is gained here either.
- **Larger or LLM-based rerankers (bge-reranker-v2-m3, 568M parameters; listwise LLM reranking).** Several times slower again on CPU, or not local. Not tried.
- **Quantized ONNX variants in the same repo (`model_qint8_arm64.onnx` and others).** Faster, but platform-specific, so CI (x86) and a Mac would score differently. Not used.

## Consequences
- S4 exists and is measured, but on CUAD dev, with CUAD's templated questions, it is a regression, not the quality ceiling Design §7 expected (F-012). The quality-against-latency numbers are in `docs/results.md`.
- `make models` downloads 91 MB more; CI's test and integration jobs download it on every run, as they do the embedder.
- Swapping the cross-encoder needs no re-ingest: it reads chunk text at query time. Another model is a new model id and a new results row, compared with the same run command. Fine-tuning one on legal clauses is out of scope (Design §4).
- If the user changes the eval set's question text (D7), this model is the first thing to re-measure. The diagnostic put it 8.6 points above S3 as S3 stands today, but S1 to S3 would move with the new text too, so that gap is not a prediction.
