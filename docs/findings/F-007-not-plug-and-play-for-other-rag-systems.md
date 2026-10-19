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
Not a blocker for v0.1 if the README claim stays modest (README section 7 does this). If portability is meant to be a selling point, add steps in Phase 8 or 9: publish the contract as OpenAPI plus prose, add a `rageval check-contract <url>` conformance command, define and document the eval-set format (it is already versioned JSONL, so this is mostly writing), and decide whether to support the text-matching fallback. This is a scope decision for the user (D-style), not an agent's call.

## Resolution
