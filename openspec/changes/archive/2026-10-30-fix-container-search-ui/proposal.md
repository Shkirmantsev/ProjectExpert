# Repair container search and operator feedback

## Why
The deployed UI advertises retired models and a nonexistent chat integration, hides indexing jobs, reports an empty source catalog despite a published search generation, and omits the accepted local inbox from automatic indexing. A transient refresh refusal hides its actual reason.

## What changes
Expose current embedding bindings and active settings, job progress and actionable failures; index the configured local inbox with LOCAL_ONLY provenance; show published sources; render Wiki pages and search evidence readably. Support OpenAI SSE framing of deterministic search results so Open WebUI can work without a chat LLM. Keep approval and egress boundaries closed and describe unavailable features honestly.

## Impact
UI adapter, discovery/indexing and deployment documentation. No chat provider, automatic knowledge promotion or target-project edits are introduced.
