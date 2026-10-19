# Results ledger

The only place measured headline numbers are recorded. A number belongs here only if one command regenerates it. A number that cannot be reproduced is deleted, not softened. Do not copy a number into the README, a résumé or a pitch until its row is `final`.

Mirrors Design §14. Status: `empty` (nothing yet), `provisional` (dev data or pre-freeze config), `final` (frozen config, reproduced from a clean checkout).

| Result | Status | Value (with 95% CI and n) | Command | Run id / manifest | Date | Step |
| --- | --- | --- | --- | --- | --- | --- |
| recall@k and MRR per strategy S1 to S4, CUAD dev | empty | | | | | 2.10, 3.9 |
| recall@k and MRR per strategy S1 to S4, CUAD test | empty | | | | | 4.8, 9.4 |
| Character precision/recall at a token budget, per chunker | empty | | | | | 3.9 |
| Rerank latency cost vs quality gain | empty | | | | | 3.3 |
| Presence accuracy, abstention precision and recall, citation precision | empty | | | | | 5.8 |
| Judge κ vs blind human labels, per criterion | empty | | | | | 7.2 |
| Judge intra-rater (human) κ and judge repeat consistency | empty | | | | | 7.2 |
| Bias effects: position flip rate, verbosity shift, citation trust | empty | | | | | 7.4 |
| One mitigation, before and after | empty | | | | | 7.5 |
| Gate false-alarm rate, retrieval (subsampling): query-level vs cluster-level | empty | | | | | 4.6 |
| Gate false-alarm rate, LLM stages (A/A, cache off) | empty | | | | | 7.6 |
| Minimum detectable recall drop at 80% power on the CI subset | empty | | | | | 4.6 |
| Cost per full run (cold and warm) and per CI run | empty | | | | | 5.8, 8.8 |
| p95 latency: `/retrieve` per strategy, `/answer` end to end | empty | | | | | 8.7 |
| Headline table repeated on QASPER | empty | | | | | 9.3 |
