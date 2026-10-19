# F-002: A full templated question may match almost nothing under websearch_to_tsquery

- **Status:** open
- **Date:** 2026-10-19
- **Found by:** Claude, while writing the plan
- **Evidence level:** hypothesis (not checked)
- **Affects:** 3.1, 3.9; Design §7 (S1), §5.9

## Finding
Design §7 specifies S1 as `websearch_to_tsquery` with `ts_rank_cd`. As I understand Postgres, `websearch_to_tsquery` combines unquoted words with AND, and CUAD queries are long templated sentences ("Highlight the parts (if any) of this contract related to ..."). An AND over all of those terms could return few or no chunks, which would make S1 look much worse than lexical retrieval really is and distort every comparison with S2 to S4.

## Evidence
Not checked. To settle it: in step 3.1, run S1 on dev and count queries that return fewer than k rows, for the plain approach and for alternatives (OR semantics, stripping the template boilerplate, using only the category name and key terms).

## Consequence
If confirmed, S1's query construction becomes a documented decision (ADR 0009) and part of what "S1" means in the results table. Whatever is chosen must be tuned on dev only, and must not use gold information.

## Resolution
