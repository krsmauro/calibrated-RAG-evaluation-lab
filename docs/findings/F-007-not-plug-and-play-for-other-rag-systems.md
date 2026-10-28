# F-007: The plan does not yet make the harness usable on another team's RAG system

- **Status:** open
- **Date:** 2026-10-19
- **Found by:** Claude, answering the user's portability question
- **Evidence level:** read from a source (Design §1, §6, §9, §10 and the phase files)
- **Affects:** 2.7, 3.7, 4.7, 8.x, 9.5; README section 7

## Finding
Design §1 says the harness "can evaluate any RAG service that implements the same small contract". The plan builds the pieces (HTTP adapter, a contract test against a fake system under test per Design §9, a reusable Action) but not what an outsider would need:
1. No written contract specification for `/retrieve` and `/answer`, including that chunk offsets must refer to the exact document text the gold labels use.
2. No conformance check a third party can run against their own service.
3. No documented eval-set file format or importer for bringing their own corpus, queries and character-level gold spans. Creating gold spans is the expensive part of using the tool on a new domain.
4. No fallback for services that cannot return offsets (locating returned text inside the document, with a match-rate report).
5. Judge calibration does not transfer across domains; users need their own blind labels. The `calibrate` command can already run on any label file, but this is not documented.

## Evidence
Absence of these items from `docs/phases/`. Step 2.7 defines the wire models and a contract test, which is the natural base for items 1 and 2.

## Consequence
Not a blocker for v0.1 if the README claim stays modest (README section 7 does this). If portability is meant to be a selling point, add steps in Phase 8 or 9: publish the contract as OpenAPI plus prose, add a `ragcalibrate check-contract <url>` conformance command, define and document the eval-set format (it is already versioned JSONL, so this is mostly writing), and decide whether to support the text-matching fallback. This is a scope decision for the user (D-style), not an agent's call.

## Resolution
2026-10-28, step 2.7 (partial, a base for item 1 only): the wire models exist in one module, `ragcalibrate/contract.py`; the service publishes them as OpenAPI at `/docs`, with every error as RFC 9457 problem details; `RetrievedChunk` documents its offsets as half-open character offsets into the raw text. Items 1 (a prose spec, including that offsets must refer to the exact text the gold labels use) to 5 are still missing. Status unchanged: open, and the scope decision is still the user's.

2026-10-28, after step 3.2: the harness now calls `GET /readyz` once before a run and stops with one readable line if the service is unreachable or answers with an error (`HttpSut.check_ready`). An outside service must therefore also answer `GET /readyz` with a 2xx when it can take queries; a prose contract spec (item 1) should list it. Status unchanged.

2026-10-28, step 3.3: `RetrieveResponse` gained a required, nullable `reranker_id` (the cross-encoder the service used for `rerank`, null otherwise), so the run records the model as it records `embedder_id`. An outside service must send `"reranker_id": null` in every response, or the harness's strict parsing rejects it; a prose spec (item 1) should say which response fields are required even when null. Status unchanged.
