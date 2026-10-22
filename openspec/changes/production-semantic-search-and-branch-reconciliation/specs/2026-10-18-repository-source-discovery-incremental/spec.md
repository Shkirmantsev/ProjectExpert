# repository-source-discovery-incremental Specification delta

Covers plan §43, §44 (PR 9 of §79).

## Purpose

Define the automatic, incremental source discovery service that lets
a user mount a target repository and start the platform without
manually listing files. The service MUST produce a stable source
inventory with content fingerprints, MUST skip non-source directories
and intermediate build artefacts, and MUST remember unchanged files
across runs to avoid re-parsing.

## ADDED Requirements

### Requirement: default include and exclude rules

The discovery service MUST apply a documented default include list
covering common source files (Java, Kotlin, Python, JavaScript,
TypeScript, Gradle, Maven POM, OpenSpec, Markdown, HTML, supported
API / spec files) and a documented default exclude list covering
`.git/`, the runtime cache, `target/`, `build/`, `node_modules/`,
generated vendor directories and binary build outputs except
selected JAR inputs. The defaults MUST be overridable by the
project configuration.

#### Scenario: project configuration overrides defaults (verifies: default include and exclude rules)

Given the project configuration declares additional include patterns
When the discovery service runs
Then the additional patterns are honoured
And sources outside the union of default and project patterns are not ingested

### Requirement: content-fingerprinted inventory

For every discovered source the service MUST record its path, source
family, content hash, parser version and last effective retrieval
text hash. The inventory MUST be persisted in the runtime cache and
MUST be comparable across runs.

#### Scenario: inventory persists path, hash and parser version (verifies: content-fingerprinted inventory)

Given the discovery service runs against a target repository
When the inventory is persisted
Then every entry carries path, source family, content hash, parser
version and last retrieval text hash
And a subsequent run can diff the new inventory against the persisted
one without re-reading unchanged sources

### Requirement: incremental reuse

When a discovered source has unchanged path, content hash and parser
version the service MUST NOT reparse it. New, modified or removed
sources MUST be classified accordingly so the rest of the pipeline
can reuse or rebuild only the affected shards.

#### Scenario: unchanged source is not re-parsed (verifies: incremental reuse)

Given a persisted inventory where source S has content hash h
And the source on disk still has content hash h
When the discovery service runs again
Then S is not re-parsed
And the persisted retrieval text hash for S is preserved

#### Scenario: modified source is reclassified as MODIFIED (verifies: incremental reuse)

Given a persisted inventory where source S has content hash h
And the source on disk now has content hash h'
When the discovery service runs again
Then S is marked MODIFIED
And the downstream reconciliation ingests only S, not the unchanged sources

### Requirement: family classification

The discovery service MUST classify each source into a source family
recognised by the ingestion pipeline (at minimum source code,
canonical knowledge, OpenSpec change, documentation, configuration).
A source MUST NOT be ingested twice by overlapping families.

#### Scenario: family classification is stable (verifies: family classification)

Given a discovered Markdown file
When the inventory is persisted
Then the family is `documentation`
And the same file is not re-discovered under a different family on the next run

### Requirement: required for first-run UX

The discovery service MUST be invoked automatically by the production
`start` command before ingestion when no source inventory exists. A
user MUST be able to start the platform against an empty machine and
a mounted target repository with no manual file listing.

#### Scenario: first start discovers sources automatically (verifies: required for first-run UX)

Given a target repository with no persisted source inventory
When the operator runs the production `start` command
Then the discovery service walks the target repository
And the persisted inventory lists all matching default source files
And non-source directories such as `.git/`, `target/`, `build/`,
`node_modules/` are excluded
