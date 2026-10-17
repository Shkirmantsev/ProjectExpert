# Tier-3 chunk-size sweep

- **Schema**: `tier-3-chunk-size-sweep/1` v1
- **Scope**: `tier-3-chunk-size-sweep`
- **Golden queries**: `evals/corpus/golden_queries.yaml`
- **Budgets**: 512, 768, 900, 1200
- **Selected default**: **512** tokens

## Per-budget metrics

| Context budget | Recall | Recall@5 | MRR | NDCG@10 | Context coverage | Avg context tokens |
|---:|---:|---:|---:|---:|---:|---:|
| 512 | 0.7333 | 0.6667 | 0.9333 | 0.7438 | 0.9333 | 581 |
| 768 | 0.7333 | 0.6667 | 0.9333 | 0.7438 | 0.9333 | 581 |
| 900 | 0.7333 | 0.6667 | 0.9333 | 0.7438 | 0.9333 | 581 |
| 1200 | 0.7333 | 0.6667 | 0.9333 | 0.7438 | 0.9333 | 581 |

## Selection rule

Plan §28.4: evaluate the `512 / 768 / 900 / 1200` token budgets (including the `900`-token initial candidate) and pick the budget that maximises the mean of `[recall, context_coverage]`, breaking ties on the smaller budget so context token cost is minimised when recall and coverage are equal.

## Notes

- Tier-1 default (`minimal` profile) keeps the existing context_budget = 2000 setting for backwards compatibility.
- The selected default is cross-referenced from the embedding ADR (`.ai/wiki/adr/0026-embedding-profile-identity-and-vector-namespace.md`) and from `evals/baselines/pre_change.json`.
