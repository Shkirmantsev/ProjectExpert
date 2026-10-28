# Specification delta

Proposed; not adopted current behavior.

## ADDED Requirements

### Requirement: Dependency insight enrichment and reuse
The caller workflow SHALL search existing curated knowledge before new dependency research, enrich a matching page rather than duplicate it, and persist each new reusable insight with package identity, version/hash, repository context, evidence references and fact/inference labels. Raw artifacts and transient failures SHALL remain outside curated knowledge. Page writes SHALL retain OKF validation, audit and path safety, and require no new operator approval for normal curation.

#### Scenario: Repeat question
- **GIVEN** a fresh page already answers the dependency question
- **WHEN** a caller asks it again
- **THEN** the workflow reuses its cited context without reacquiring or decompiling unchanged artifacts

#### Scenario: New insight on existing page
- **GIVEN** research adds a verified behavior fact to an existing package page
- **WHEN** the caller curates the result
- **THEN** the page is enriched without duplicating the fact or replacing unrelated content

### Requirement: Freshness and conflict-safe research curation
Dependency evidence changes SHALL mark affected insight evidence stale without silently deleting human explanation. Enrichment SHALL detect concurrent page changes and return a conflict rather than lose edits. A successful write SHALL distinguish stored content from indexed visibility and provide a retry path for refresh failure.

#### Scenario: Dependency upgrade
- **GIVEN** a page cites an older artifact hash
- **WHEN** the dependency version or hash changes
- **THEN** the previous insight is marked stale and renewed research is requested before presenting it as current

#### Scenario: Concurrent edits
- **GIVEN** two callers read the same page revision
- **WHEN** both attempt different enrichments
- **THEN** the first may succeed and the second receives conflict information rather than overwriting unseen content

#### Scenario: Index failure after write
- **GIVEN** a valid enriched page is stored and index refresh fails
- **WHEN** the caller receives the write result
- **THEN** it reports stored but indexing pending or failed; retry makes the page searchable without duplicating it
