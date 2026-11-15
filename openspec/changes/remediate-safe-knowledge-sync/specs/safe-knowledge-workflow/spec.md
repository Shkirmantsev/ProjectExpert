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
