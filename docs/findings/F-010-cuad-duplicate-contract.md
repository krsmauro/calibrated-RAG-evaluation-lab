# F-010: one CUAD contract appears twice, and its two copies are labeled differently

- **Status:** confirmed
- **Date:** 2026-10-28
- **Found by:** Claude, plan step 2.6
- **Evidence level:** measured (command and output below)
- **Affects:** 2.6 (document identity), 4.1 and 4.2 (document clusters), 5.8 and 7.x (presence and abstention metrics); Design §5.4, §16; findings F-008, F-005

## Finding
CUAD's 510 contracts have 509 distinct texts. `ADUROBIOTECH,INC_06_02_2020-EX-10.7-CONSULTING AGREEMENT` and the same title with `(1)` appended are byte-identical (12,020 characters). Both are in dev, so dev and test do not share a contract. Their gold labels agree in 39 of 41 categories. In the other two, the `(1)` copy labels a clause that the first copy marks as absent: Anti-Assignment ("This Agreement shall not be assignable by Consultant.", characters 11,550 to 11,603) and Exclusivity (characters 8,854 to 9,244). So the first copy's "no answer" label is wrong for two categories: CUAD's unanswerable labels contain at least some missed clauses.

## Evidence
After `make ingest`: `SELECT count(*), count(DISTINCT sha256) FROM documents` returns `510|509`. Grouping the loaded CUAD documents by sha256 and comparing the two copies' gold spans per category (a scratch script over `load_cuad`) gives: both split `dev`; 9 vs 11 answerable categories; categories whose spans differ: `['Anti-Assignment', 'Exclusivity']`, empty in the first copy.

## Consequence
- **Document identity (2.6):** documents are identified by `(corpus, external_id)`, with sha256 kept as a changed-text check and deliberately not unique (migration 0001). This is why: keying on the content hash would have merged the two copies, and their two label sets with them.
- **Clusters (4.1, 4.2):** the document-clustered bootstrap treats the two copies as two independent clusters, but they get identical retrievals (same text, same 41 questions). That is 1 of 408 dev clusters, so the effect on CI width is negligible. Recommendation: keep both and mention it in the eval spec's limitations, rather than special-casing one contract. Decide in 4.1.
- **Label noise (5.8, 7.x):** a system that finds the anti-assignment clause in the first copy is scored as a false presence claim. This is direct evidence for the "gold misses relevant clauses" risk. It is one contract, so it says nothing about the overall miss rate; it does mean abstention precision is measured against imperfect gold and should be reported as such.
