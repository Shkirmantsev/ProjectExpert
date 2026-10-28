# 2026-10-12-a2a-adapter Specification

## Purpose
Expose optional A2A communication through isolated, versioned adapters that
translate protocol messages into platform ports and enforce the existing
authentication, capability, policy and audit boundaries. Keep inbound and
outbound transports disabled by default and the core independent of A2A wire
types and third-party protocol libraries.

## Requirements

### Requirement: A2A adapter isolation from the core domain model

The platform MUST expose A2A as a dedicated adapter family under
`pi_platform/adapters/a2a/` whose interface to the platform is
defined by the `A2aAdapterPort`, `AgentCardPort`,
`ReverseDelegationPort` and `ExternalAgentPort` ports under
`pi_platform/ports/a2a/`. The platform `core/` MUST NOT import any
A2A protocol library or wire type. A2A wire types MUST be translated
to port value-types at the adapter boundary, and the adapter MUST NOT
mutate the canonical knowledge or the runtime store except through
the existing ports (`ports/orchestration`, `ports/control`,
`ports/security`, `ports/retrieval`).

#### Scenario: core module does not import an A2A protocol library

Given the platform implementation
When a static analysis scans every Python module under `pi_platform/core/`
Then no module imports an A2A JSON-RPC or wire library.

#### Scenario: wire types are translated at the adapter boundary

Given an inbound A2A `tasks/send` JSON-RPC envelope
When the HTTP transport adapter receives it
Then the adapter translates the envelope to a typed `A2aTask` value
and dispatches it through `A2aAdapterPort`, with no JSON dict passed
past the adapter boundary.

### Requirement: Tracked and advertised A2A spec version

The platform MUST pin the supported A2A protocol version through a
single tracked constant exposed via the capability discovery
descriptor. The capability descriptor MUST list the supported major
version range. When a peer offers an unsupported version the adapter
MUST refuse the handshake with `version-incompatible` and MUST NOT
process the request body.

#### Scenario: capability descriptor advertises the supported version

Given the capability discovery descriptor is queried
When the descriptor is returned
Then it includes the tracked `A2A_SPEC_VERSION` constant under
`protocols.a2a.version`.

#### Scenario: version-incompatible peer is rejected

Given a peer advertises an A2A spec version outside the supported
range
When the adapter receives the handshake
Then the adapter returns `version-incompatible` and does not invoke
any platform operation.

### Requirement: AgentCard served through the same gateway

When the A2A inbound feature flag is enabled, the platform MUST
serve an Agent Card at the documented A2A well-known path through the
same transport that serves the A2A JSON-RPC surface. The Agent Card
MUST be generated from the capability discovery descriptor and MUST
NOT contain secrets, runtime paths or environment values. When the
A2A inbound feature flag is disabled the Agent Card route MUST NOT
be served.

#### Scenario: Agent Card is published when enabled

Given the `a2a-inbound` feature flag is enabled
When a peer requests the documented well-known path
Then the platform returns the Agent Card JSON object derived from the
capability descriptor.

#### Scenario: Agent Card is absent when disabled

Given the `a2a-inbound` feature flag is disabled
When a peer requests the documented well-known path
Then the platform returns 404 and writes no body.

#### Scenario: Agent Card redacts secret-shaped fields

Given the Agent Card generation
When the descriptor contains a value matching the secret reference
shape `secret://...`
Then that value is omitted from the card and replaced with an
opaque reference string.

### Requirement: Inbound A2A requests pass the same security gates as MCP

Every inbound A2A request MUST be authenticated, authorised and
audited through the central policy engine before any platform
operation runs. Required capabilities MUST be enforced. Unknown
policy actions MUST default to DENY. Every accepted request MUST
emit one audit record with the same field shape as the Phase 7 audit
log. The adapter MUST NOT introduce an alternate authorisation
bypass.

#### Scenario: unauthenticated A2A request is refused

Given the inbound A2A feature flag is enabled and a bearer token is
configured
When a peer sends a `tasks/send` request without the token
Then the adapter returns 401 and writes one audit record with
`policyDecision = DENY`.

#### Scenario: A2A request without required capability is refused

Given a peer sends an inbound A2A request
When the request requires a capability the actor does not hold
Then the adapter returns 403 with `policyDecision = DENY`, writes
one audit record and does not call any port method.

#### Scenario: unknown policy action is denied

Given an inbound A2A request for which no policy rule exists
When the request reaches the policy engine
Then the policy engine returns DENY by default and the adapter
responds 403.

### Requirement: A2A capability handshake participates in capability discovery

The capability discovery descriptor MUST advertise the A2A surface as
a separate `protocols.a2a` entry alongside the existing `mcp`
entry. The descriptor MUST include the supported version, the
inbound feature flag state, the inbound endpoint when bound and the
documented error codes. The descriptor MUST NOT advertise inbound
A2A when the inbound feature flag is disabled.

#### Scenario: descriptor includes protocols.a2a when enabled

Given the `a2a-inbound` feature flag is enabled
When the capability descriptor is queried
Then it includes `protocols.a2a` with `enabled: true`, the tracked
version and the inbound endpoint.

#### Scenario: descriptor omits protocols.a2a when disabled

Given the `a2a-inbound` feature flag is disabled
When the capability descriptor is queried
Then it does not include `protocols.a2a` and the HTTP route is not
served.

### Requirement: A2A failure modes are explicit

The adapter MUST translate every internal failure into one of the
documented A2A wire errors and MUST NOT leak stack traces,
filesystem paths, secret references, or internal exception class
names to the peer. The failure translation table MUST be part of the
test suite.

#### Scenario: policy denial translates to A2A `forbidden`

Given the policy engine returns DENY
When the adapter translates the failure
Then the response uses the documented wire error class
`forbidden` with a redacted message and zero stack trace.

#### Scenario: missing capability translates to A2A `unauthorized`

Given the actor lacks the required capability
When the adapter translates the failure
Then the response uses the documented wire error class
`unauthorized` with the redaction policy applied.

### Requirement: A2A transport uses the Python standard library for v1.0

The default A2A HTTP and stdio transports MUST be implemented using
the Python standard library only. Any future adoption of a third-party
A2A library MUST be recorded in an ADR with an SPDX identifier and a
license-gate verdict before the dependency may ship.

#### Scenario: no third-party A2A library is imported

Given the adapter module graph
When a dependency analysis is run
Then no third-party A2A library appears under `pi_platform/adapters/a2a/`.

### Requirement: A2A inbound endpoint binds loopback by default

The default deployment MUST bind the A2A HTTP transport to the
loopback interface on a documented port. A non-loopback bind MUST
require an explicit, documented operator override and MUST be
recorded in the audit log on each startup.

#### Scenario: default bind is loopback

Given no operator override
When the adapter starts
Then the bind address is `127.0.0.1` (or `::1`) on the documented
port.

#### Scenario: non-loopback bind is logged

Given an operator override binds the adapter to a non-loopback
address
When the adapter starts
Then one audit record with `operation = "a2a.bind.non-loopback"`
is written before the listener accepts traffic.

### Requirement: A2A feature flag matrix is documented and enforced

The platform MUST document and enforce an A2A feature flag matrix
covering the `a2a-inbound`, `a2a-outbound`, `a2a-stdio-transport`
and `a2a-streaming` flags. Each flag MUST default to a safe state.
Disabling a flag MUST remove the corresponding routes, transports and
capability entries.

#### Scenario: every flag defaults to its safe state

Given a fresh configuration
When the feature flag evaluation runs
Then `a2a-inbound` defaults to `false`, `a2a-outbound` defaults to
`false`, `a2a-stdio-transport` defaults to `false` and
`a2a-streaming` defaults to `not-supported`.

#### Scenario: disabling a flag removes the route

Given `a2a-inbound` is disabled
When the platform starts
Then the A2A HTTP route is not served and the Agent Card returns 404.

### Requirement: A2A dependency research dispatch
When inbound A2A research is enabled and authorized, an advertised dependency research task SHALL dispatch to the same application operations as MCP and return research artifacts with equivalent provenance and limits. An acknowledgement alone SHALL NOT count as completed research. Disabled, unsupported, denied and timed-out requests SHALL be distinguishable.

#### Scenario: Transport parity
- **GIVEN** the same actor permissions, repository snapshot and research arguments
- **WHEN** equivalent MCP and A2A research requests run
- **THEN** semantic graph/code evidence and policy outcomes agree

#### Scenario: Disabled research
- **GIVEN** A2A inbound is disabled
- **WHEN** a research task is submitted
- **THEN** it fails explicitly and no research or acquisition occurs

#### Scenario: Unsupported operation
- **GIVEN** an unrecognized research action
- **WHEN** the request is submitted
- **THEN** it returns unsupported instead of a completed acknowledgement
