# Context impact — rerank decision propagation

## Specs

| Spec | Action |
|---|---|
| `2026-10-04-reranker-port` | modify — the reranker must carry its decision; the policy; the modality behaviour |
| `2026-10-16-retrieval-candidate-selection` | modify — the selection orders by the rerank decision and traces it |
| `2026-10-04-multi-stage-retrieval` | modify — a failing reranker never fails the retrieval in any path |
| `2026-10-07-mcp-server` | add — the caller may control reranking per query |

## Wiki

| Node | Action |
|---|---|
| `modules.platform-core` | review — the reranker core now carries the policy and the modality behaviour |
| `interfaces.one-command-ux` | update — reranking is active by default and operator-controllable |

## ADR

No new ADR: the change keeps the existing decisions (ADR 0025
"rerank DIRECT before graph expansion" and ADR 0004 "ports and adapters
extension style") and only repairs the score handover.

## Not affected

The embedding profiles, the vector namespaces, the retrieval architecture
and the MCP protocol surface are unchanged.
