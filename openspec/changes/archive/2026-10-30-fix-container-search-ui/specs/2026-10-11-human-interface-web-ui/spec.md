## MODIFIED Requirements

### Requirement: Minimal OpenAI-compatible shim
When enabled, the shim SHALL return deterministic retrieved evidence with source citations without requiring a chat LLM. It SHALL accept non-streaming requests and streaming requests using finite OpenAI-compatible SSE framing, with role, content, finish and DONE events. It SHALL NOT expose upload or admin features.

#### Scenario: chat completion maps to the orchestrator
Given the Open WebUI profile is enabled
When a client posts a chat completion request
Then the request is answered from the query orchestrator without external calls.

#### Scenario: Open WebUI requests streaming search
Given a ready published retrieval generation
When a client requests stream=true
Then evidence is returned as text/event-stream ending in [DONE], without an upstream LLM request.

## ADDED Requirements

### Requirement: Truthful operator feedback
The frontend SHALL display indexing activity, completion and failure; SHALL offer current embedding bindings without retired aliases; SHALL explain unsupported chat/delegation and approval requirements; SHALL display readable evidence and Wiki text. Source listings SHALL include the published source inventory. Readiness refusals SHALL preserve the underlying diagnostic.

#### Scenario: Search without chat credentials
Given embedding inference and a published index
When the user searches
Then ranked cited evidence is available without chat credentials and source listings describe the published sources.
