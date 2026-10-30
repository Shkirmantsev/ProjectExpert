## ADDED Requirements

### Requirement: Optional grounded chat connection
The UI SHALL expose clear optional OpenAI-compatible and Anthropic chat provider settings, server-side save, connection test and disable. Secrets SHALL be redacted and stored only in ignored owner-readable runtime state. Enabling context sharing SHALL require explicit operator opt-in. Query SHALL retrieve first and optionally generate an answer from bounded evidence, respecting egress policy; failures SHALL return evidence with an actionable explanation. Deterministic retrieval SHALL never call chat. The Open WebUI adapter SHALL reuse this behavior.

#### Scenario: Operator enables a local chat model
Given an operator saves an OpenAI-compatible model endpoint with context sharing enabled
When a project question is asked
Then the server sends bounded retrieved evidence to the model and returns its answer with evidence.

#### Scenario: Chat provider fails
Given a configured provider times out or denies access
When a user asks a project question
Then the response preserves retrieved evidence and explains the chat failure without exposing credentials.

### Requirement: Effective embedding execution indicator
The UI SHALL display Active mode separately from the requested Auto/CPU/GPU device. It SHALL report CPU, GPU or Hybrid from actual adapter/deployment evidence and show its source/reason. When evidence is unavailable it SHALL show Unknown rather than guess. A managed GPU embedding profile using a CPU projector SHALL report Hybrid and explain that scope.

#### Scenario: Auto selects CPU
Given automatic deployment selection chose the CPU profile
When the UI shows indexing status
Then Active mode is CPU, even when the requested device is Auto.

#### Scenario: GPU backend with CPU projector
Given a managed CUDA or Vulkan profile and a forced CPU projector
When the UI shows indexing status
Then Active mode is Hybrid with the backend and explanation.

## MODIFIED Requirements

### Requirement: Minimal OpenAI-compatible shim
When enabled, the shim SHALL expose retrieval-first project answers, supporting deterministic cited evidence without a chat LLM and generated grounded answers only through explicitly saved optional chat configuration. It SHALL accept non-streaming and finite OpenAI-compatible SSE responses with role, content, finish and DONE events. It SHALL NOT expose upload or administration features through the OpenAI surface.

#### Scenario: chat completion maps to the orchestrator
Given the Open WebUI profile is enabled and optional chat is disabled
When a client posts a chat completion request
Then the query orchestrator returns evidence without an external chat-model call.

#### Scenario: Open WebUI requests streaming search
Given a ready published retrieval generation and optional chat disabled
When a client requests stream=true
Then evidence is returned as text/event-stream ending in [DONE], without an upstream LLM request.

### Requirement: Truthful operator feedback
The frontend SHALL display indexing activity, completion and failure; SHALL offer current embedding bindings without retired aliases; SHALL explain optional chat, agent-delegation limitations and approval requirements; SHALL display readable answers, evidence and Wiki text. Source listings SHALL include the published source inventory. Readiness refusals SHALL preserve the underlying diagnostic.

#### Scenario: Search without chat credentials
Given embedding inference and a published index
When the user searches
Then ranked cited evidence is available without chat credentials and source listings describe the published sources.
