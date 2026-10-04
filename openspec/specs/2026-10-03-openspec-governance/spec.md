# OpenSpec Governance Specification

## Purpose

Keep one discoverable accepted project state and distinguish dated current
capabilities and historical changes from active proposals.

## Requirements

### Requirement: dated accepted and archived identities

Current capabilities SHALL use `YYYY-MM-DD-domain-capability/spec.md` under
`openspec/specs/`, dated by first Git acceptance. Updates SHALL retain that date.
Active changes SHALL use undated semantic kebab-case names. Archived changes
SHALL use `YYYY-MM-DD-original-change-name`, dated on archival without stacking
dates. Names SHALL use lowercase kebab-case without underscores. Delta folders
for existing capabilities SHALL match their accepted dated identity. Historical
archives SHALL retain their original paths during an identity migration.

#### Scenario: accepting a new capability

- **WHEN** a verified capability is adopted as a current specification
- **THEN** its directory receives its first Git acceptance date and a semantic capability name
- **AND** subsequent updates retain that dated identity.

#### Scenario: validating invalid names

- **WHEN** current or archive directories contain invalid calendar dates or names, or active changes have date prefixes
- **THEN** the harness OpenSpec gate fails with the offending name.

### Requirement: one central accepted-state inventory

`openspec/CURRENT.md` SHALL link each current capability spec exactly once using
relative canonical paths. It SHALL exclude proposed and archived changes from
accepted requirements. Adoption, retirement and identity migration SHALL update
this inventory together with current specs. The inventory SHALL serve navigation
without duplicating normative requirement bodies. The harness OpenSpec gate
SHALL reject missing, duplicate or stale current-spec links.

#### Scenario: adopting or retiring a capability

- **WHEN** the accepted capability set changes
- **THEN** the central current-state inventory reflects the complete resulting set.

#### Scenario: stale central state

- **WHEN** the inventory omits a spec, repeats a spec or links a retired spec
- **THEN** the OpenSpec gate fails and identifies the mismatch.
