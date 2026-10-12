# human-interface-web-ui Specification delta

## Purpose

Expose the §57 human interface as a stable UI-facing REST surface served by the
core deployment, ship a lightweight no-build frontend that needs no coding
harness and no Node.js runtime, and provide the optional Open WebUI profile
behind a feature flag.

## ADDED Requirements

### Requirement: UI API operation set

The platform MUST expose exactly these ten UI API operations (§44.3):

```text
query
retrieve
sources
graph
wiki
project-version
indexing-status
knowledge-status
materialize
agent-delegation
```

The operation set MUST be discoverable at runtime without an LLM.

#### Scenario: capability discovery lists the UI operations

Given the running platform
When a client queries capability discovery
Then the response lists all ten UI operations and their availability.

### Requirement: REST is a replaceable adapter

The REST surface MUST be implemented as an adapter. The domain model MUST NOT
import the REST adapter, and replacing the frontend MUST NOT require changing
core behaviour.

#### Scenario: core imports no HTTP transport

Given the platform core packages
When their import graph is inspected
Then no core package imports the HTTP adapter module.

### Requirement: No coding harness required

Every UI operation MUST work without Claude Code, Codex, OpenCode, Hermes or any
IDE agent. Retrieval plus the context assembler MUST be sufficient for simple
questions.

#### Scenario: UI answers without an external agent

Given a hydrated project and no configured external agent
When the UI issues a query
Then the query completes from retrieval and context assembly alone.

### Requirement: Loopback-only default binding

The HTTP server MUST bind to the loopback interface by default. A non-loopback
bind MUST require an explicit operator opt-in.

#### Scenario: default bind is loopback

Given no bind override is configured
When the server starts
Then it listens on a loopback address only.

### Requirement: Bearer token authentication

When a UI access token is configured, every API request MUST present it as an
HTTP bearer token. A missing or invalid token MUST be rejected before any
operation executes.

#### Scenario: missing token is rejected

Given a configured UI access token
When a request arrives without a bearer token
Then the server returns HTTP 401 and performs no operation.

### Requirement: Policy engine authorisation

Every UI operation MUST be authorised through the central policy engine against a
named action. Unknown actions MUST be denied.

#### Scenario: unknown action is denied

Given a request that maps to no known policy action
When the policy engine decides
Then the decision is DENY and the operation does not execute.

### Requirement: Materialisation remains approval-controlled

`materialize` MUST fail closed. It MUST require a valid approval token issued by
the trusted approval boundary before any canonical knowledge is written, and MUST
write nothing when approval is absent or invalid.

#### Scenario: materialise without approval writes nothing

Given no valid approval token
When a client calls the materialize operation
Then the response is HTTP 403 and no canonical file is written.

### Requirement: Agent delegation is egress-governed

`agent-delegation` MUST obtain an egress decision from the enterprise security
boundary before any outbound call leaves the platform. A DENY decision MUST stop
the delegation.

#### Scenario: denied egress blocks delegation

Given an egress policy that denies the target
When a client requests agent delegation
Then the request is refused and no outbound call is made.

### Requirement: Static frontend without a Node.js runtime

The default frontend MUST be served as static assets by the core deployment and
MUST NOT require Node.js or any frontend build toolchain at runtime.

#### Scenario: static assets are served from the core server

Given the platform is running
When a browser requests the root path
Then the server returns the frontend HTML and its static assets.

### Requirement: Replaceable frontend implementations

A different frontend implementation MUST be able to reuse the same core platform
without core changes.

#### Scenario: alternative frontend uses the same operations

Given an alternative frontend client
When it calls the documented UI API operations
Then it receives the same response contracts as the default frontend.

### Requirement: Optional Open WebUI profile behind a feature flag

The Open WebUI integration MUST be disabled by default, MUST be enabled only by
an explicit feature flag, and MUST be validated against the dependency license
gate before it may ship.

#### Scenario: integration is disabled by default

Given no feature flag is enabled
When the Open WebUI adapter endpoints are requested
Then they are not served.

#### Scenario: license gate must pass before shipping

Given a build that bundles the Open WebUI profile
When the license gate runs
Then the pinned component version must have a recorded SPDX identifier and an
allow or approval verdict.

### Requirement: Minimal OpenAI-compatible shim

When the Open WebUI profile is enabled, the platform MUST expose a minimal
non-streaming OpenAI-compatible surface backed by the query orchestrator, and
MUST NOT expose streaming, file upload or administration features.

#### Scenario: chat completion maps to the orchestrator

Given the Open WebUI profile is enabled
When a client posts a chat completion request
Then the request is answered from the query orchestrator without external calls.