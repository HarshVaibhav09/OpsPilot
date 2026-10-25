# OpsPilot Retrieval Evaluation

50-query hand-labelled gold set over five logistics documents (SOP, rate card, vendor contract, incident log, invoice statement). 50 queries resolved against the live index and scored at k=5.

Recall@5 asks whether a relevant chunk appeared in the top 5, which is the number that matters most: a chunk that is never retrieved cannot be recovered by better prompting. MRR asks where it landed, since rank 5 is worth less than rank 1 under a fixed context budget.

## Headline

| Configuration | Recall@5 | MRR | p50 latency |
|---|---|---|---|
| Dense only | 0.74 | 0.639 | 10.1 ms |
| Hybrid (dense + BM25, RRF) | 0.86 | 0.711 | 15.8 ms |
| **Delta** | **+0.120** | **+0.072** | |

## By query style

This breakdown explains the headline. Hybrid should win clearly on identifier queries and roughly tie on paraphrase queries. If it wins uniformly across every style by a similar margin, suspect a labelling artifact rather than a real gain.

| Query style | n | Dense recall@5 | Hybrid recall@5 | Delta | Dense MRR | Hybrid MRR |
|---|---|---|---|---|---|---|
| identifier | 17 | 0.529 | 0.765 | +0.236 | 0.417 | 0.632 |
| multi_hop | 5 | 0.8 | 0.8 | +0.000 | 0.8 | 0.7 |
| paraphrase | 17 | 0.824 | 0.882 | +0.058 | 0.755 | 0.634 |
| table_lookup | 11 | 0.909 | 1.0 | +0.091 | 0.73 | 0.955 |

## By document type

| Document type | n | Dense recall@5 | Hybrid recall@5 | Delta |
|---|---|---|---|---|
| contract | 11 | 0.909 | 1.0 | +0.091 |
| data_log | 10 | 0.4 | 0.6 | +0.200 |
| invoice | 8 | 0.75 | 0.875 | +0.125 |
| rate_card | 10 | 0.7 | 0.8 | +0.100 |
| sop | 11 | 0.909 | 1.0 | +0.091 |

## Queries where hybrid regressed

None.

## Known limitations

- 50 queries over 5 documents is a regression guard, not a benchmark. It reliably catches a chunking change that made retrieval worse; it does not support a precise claim about absolute quality.
- Dense mode retrieves top_k_retrieval candidates; hybrid retrieves twice that before fusing. Part of the gain therefore comes from the wider candidate pool rather than from BM25 alone. This mirrors production behaviour, so it is the right thing to measure, but it does not isolate the fusion step.
- Labels anchor to passages containing the answer. On queries spanning many records (all incidents for one truck), recall@5 is partial by construction, since only some matching rows can fit in the top results.
- Aggregation and absence queries (largest cargo damage, records missing a truck id) are included deliberately and are expected to score poorly. Retrieval is the wrong tool for them; they belong in a structured query path, which is not built yet.
