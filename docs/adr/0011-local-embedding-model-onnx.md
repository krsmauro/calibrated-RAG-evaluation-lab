# ADR 0011: Local embedding model bge-small-en-v1.5, run with ONNX Runtime

- **Status:** accepted
- **Date:** 2026-10-28
- **Step:** 2.5 (choose and wrap the local embedding model)

## Context
S2 (dense retrieval) needs a local embedding model so retrieval evals are free, deterministic and run in CI with no API keys (Design §7). The step's criteria: a license that permits the use, fits CPU in CI, context at least the chunk size, runtime per chunk. The user chose `BAAI/bge-small-en-v1.5` on 2026-10-28, with C1 chunks of 256 tokens and 32 overlap (step 2.4).

Facts, read from the model repo at commit `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` on 2026-10-28: MIT license; 384 dimensions; 512-token context (including `[CLS]` and `[SEP]`); pooling is the `[CLS]` token followed by L2 normalization (`1_Pooling/config.json`, `modules.json`); BERT WordPiece tokenizer with lowercasing; the repo ships an official ONNX export (`onnx/model.onnx`, 133,093,490 bytes, sha256 `828e1496...cf35`).

## Decision
Use `BAAI/bge-small-en-v1.5` pinned to commit `5c38ec7c4...`, run with ONNX Runtime (CPU) and the `tokenizers` library, not sentence-transformers. `make models` downloads `tokenizer.json` and `onnx/model.onnx` from that commit and checks size and sha256. The embedder id `bge-small-en-v1.5@5c38ec7c405e` is recorded with every embedding. Questions are embedded as is, without BGE's optional query instruction (the model card says v1.5 works without it; adding it is a possible dev-only ablation).

## Evidence
All on an Apple M5 (10 cores, 24 GB), macOS, onnxruntime 1.31.1, tokenizers 0.23.3.

- **Same vectors as the reference implementation.** 241 texts (200 random C1 chunks from 10 CUAD contracts plus the 41 distinct CUAD questions) embedded with sentence-transformers 6.2.0 (torch 2.14.1, transformers 5.21.0, same commit, run once in an isolated environment) and with this code: minimum cosine 0.9999998, maximum absolute difference 3.6e-7 per dimension, and for every one of the 41 questions the top-10 ranking of the 200 chunks is identical. `tests/unit/test_embedding.py` pins six reference values so CI keeps checking this without torch.
- **Determinism.** The same texts embedded twice are bitwise identical. A text embedded alone versus inside a padded batch differs by at most 9.7e-8 (50 chunks), so ingest batching cannot change a ranking except for exact ties.
- **Throughput.** 2,000 random C1 chunks: 59 chunks/s at batch 16, 53 at batch 32 and 64. All of CUAD with C1 (24,872 chunks) takes about 7 minutes. One question alone: 4.4 ms.
- **Context.** C1 chunks re-tokenize to at most 256 tokens on all 510 contracts (step 2.4), half the model's context.

## Alternatives considered
- **sentence-transformers with PyTorch.** The usual way to run this model, and the reference above. Lost on weight: PyTorch from PyPI on Linux pulls CUDA libraries (gigabytes) unless the project configures a CPU-only index, which slows every CI run and adds install failures (skill DEP-CRITICAL-1). The vectors are the same, so nothing is gained for that cost.
- **fastembed.** Light and ONNX-based, but as far as its documentation shows it serves models from its own converted copies rather than the model author's repo, which is one more party to trust and pin. Not checked in detail, since the author's repo already ships an ONNX export.
- **A longer-context model (for example nomic-embed-text-v1.5, 8,192 tokens).** Not needed: chunks are 256 tokens. Several such models need `trust_remote_code`, which runs code from the model repo.
- **all-MiniLM-L6-v2.** Smaller and older; a 256-token limit leaves no headroom over the chunk size.
- **A hosted embedding API.** Costs money, needs keys in CI, and breaks "retrieval evals are free and keyless". Kept as a possible extra strategy for comparison (see Consequences).

## Consequences
- No PyTorch in the project. The cross-encoder for S4 (step 3.3) follows the same pattern: an ONNX export pinned by commit and sha256, checked once against its reference implementation. If no trustworthy export exists, revisit this ADR there.
- The ONNX path is about 30 lines this project owns (tokenize, run, take `[CLS]`, normalize). The reference test is what makes that safe; keep it.
- `embed` is synchronous and CPU-bound: the service must call it through `asyncio.to_thread`, and load it once in the lifespan.
- Comparing embedding models later (a second dense strategy) is cheap if chunks stay fixed and embeddings are stored per embedder id, not as one fixed-dimension column on `chunks`. Step 2.6 should store embeddings in a table keyed by `(chunk_id, embedder_id)`, so a second model is an extra ingest pass, not a migration rewrite.
- The model files (134 MB) are downloaded in CI's test job on every run. Add a cache if that becomes slow.
