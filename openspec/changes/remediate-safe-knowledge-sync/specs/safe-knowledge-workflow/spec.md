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
