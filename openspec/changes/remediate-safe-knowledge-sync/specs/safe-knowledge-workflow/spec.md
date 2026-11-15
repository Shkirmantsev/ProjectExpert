## ADDED Requirements

### Requirement: Restore without expensive source processing
The platform SHALL expose restore as an administrative operation that imports
compatible Git knowledge without source parsing, OCR or new embeddings.

#### Scenario: Missing vectors
- **WHEN** a verified snapshot lacks required compatible vectors
- **THEN** restore reports requires-reindex and preserves the prior active generation

### Requirement: Export safe complete sources independently
The platform SHALL export fully eligible source results while keeping restricted,
unknown or tainted sources and their derivatives local. Export SHALL declare its
scope without claiming all local sources are represented.

#### Scenario: Mixed repository
- **WHEN** an indexed repository contains a safe document and a secret document
- **THEN** export stages the complete safe document and no secret-derived record

### Requirement: Three independent administrator actions
The UI SHALL offer Restore, Reindex and Export with private project preferences,
default-off post-reindex export and trusted publication. Local indexing success
SHALL remain independent of export success. No action SHALL stage, commit or push Git.

#### Scenario: Export is denied
- **WHEN** publication authorization is unavailable
- **THEN** the proposal remains pending and local query generation remains usable


### Requirement: Honest styled delivery and hardware controls
The UI SHALL retain responsive themed controls, distinguish a static preview from
a live application, expose its asset build identity, and prevent stale caching.
Every knowledge action SHALL display readable progress in its own unique target.
Remote device selection SHALL require an available managed runtime controller.

#### Scenario: Opening the source HTML directly
- **WHEN** the page is loaded from a file URL
- **THEN** styles resolve, controls are disabled and no API requests are sent

#### Scenario: External runtime without a controller
- **WHEN** the selected Gemma runtime has no managed controller
- **THEN** the device selector is disabled with an actionable deployment explanation


### Requirement: Preserve valid newer Python source evidence
When the container AST cannot parse source syntax, the installed production Python
grammar MAY validate the complete bounded source without executing it. Successful
validation SHALL preserve full source text and disclose missing AST symbol analysis.
Invalid syntax or an unavailable grammar SHALL still fail explicitly.

#### Scenario: Python 3.12 f-string in a Python 3.11 container
- **WHEN** the newer grammar validates the complete file rejected by the interpreter AST
- **THEN** source text is indexed with analysis limits and no fabricated function symbols


### Requirement: Optional token for trusted local ownership
The UI SHALL allow the local owner to review sources and authorize signed exports
without configuring or repeatedly entering PI_UI_TOKEN. A configured token SHALL
remain required. Tokenless ownership SHALL require a loopback Host, trusted local
peer and same-origin browser context. A public deployment binding SHALL NOT enable
this mode. A loopback-published managed container MAY trust its exact host gateway.

#### Scenario: Local owner without configured token
- **WHEN** the local UI requests source review or publication from its own origin
- **THEN** local owner authorization permits the operation and token entry is hidden

#### Scenario: Foreign browser origin or public binding
- **WHEN** tokenless knowledge administration is requested from a foreign origin,
  unrelated peer, non-loopback Host or public deployment binding
- **THEN** the server refuses the request before creating publication authorization

### Requirement: Project-wide checked export and complete local context
One export policy SHALL apply automatically to all discovered files. The UI SHALL
NOT require per-path settings or individual source review. Local search and MCP
SHALL retain full confidential context; outward filtering SHALL NOT mutate it.
Checked independent text MAY be exported from mixed sources as separate context
projections. Such projections SHALL NOT satisfy complete source-cache membership.
Declared restricted sources, unknown provenance and protected dependencies SHALL
remain excluded; opaque image/figure vectors SHALL remain local unless existing
exact-byte review evidence authorizes them. No automatic OCR/model work is permitted
inside export. Existing safe complete sources remain exactly reusable.

#### Scenario: Source contains public facts and credential-bearing context
- **WHEN** export checks persisted source results
- **THEN** independently safe fragments can be shared, credential context and
  unsafe derivatives stay local, and local/MCP retrieval still returns complete data

#### Scenario: Safe projection imported on another checkout
- **WHEN** a snapshot contains checked context projections
- **THEN** verification binds exact text/hash/provenance and allows safe search
  evidence without claiming the original source was completely restored
