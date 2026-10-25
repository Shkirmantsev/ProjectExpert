# Context impact — the LLM Wiki as the curated knowledge layer

## Specs

| Spec | Action |
|---|---|
| `llm-wiki-curated-knowledge` | add — new capability |
| `2026-10-07-mcp-server` | add — the LLM Wiki tool surface and the approval boundary |

## Wiki

| Node | Action |
|---|---|
| `modules.llm-wiki` | create — the curated knowledge layer |
| `adr.0030-llm-wiki-as-curated-knowledge` | create — the decision to separate derived and curated knowledge |
| `interfaces.one-command-ux` | review — the initialised project now receives the Wiki scaffold |

## Not affected

The canonical knowledge schema, the ingestion pipeline, the embedding
profiles and the vector namespaces are unchanged. The curated Wiki is
Markdown in the repository, read by the existing source discovery.
