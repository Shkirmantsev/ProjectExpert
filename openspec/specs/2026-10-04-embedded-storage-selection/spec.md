# 2026-10-04-embedded-storage-selection Specification

## Purpose
Record the default embedded storage engine, optional enterprise alternatives, licensing, and the rationale for the storage choices.
## Requirements
### Requirement: embedded storage engine selection

The platform MUST document the runtime storage engine selection in
`adr.embedded-storage-selection`. The ADR MUST record at minimum:

- the chosen engine for the default desktop profile and the
  rationale;
- any optional enterprise-scale replacement and the rationale;
- the SPDX identifier of every runtime-storage library the platform
  depends on;
- the rejected alternatives and the reason each was rejected.

#### Scenario: ADR records dual-backend selection and rejected alternatives

Given a contributor who reads
`.ai/wiki/adr/0008-embedded-storage-selection.md`
When the contributor reviews the ADR
Then the ADR lists the chosen engine for the default profile and the
rationale
And the ADR lists every SPDX-tracked runtime-storage library
And the ADR lists the rejected alternatives with a one-line reason
each.

### Requirement: dual-backend compatibility through RuntimeStorePort

The platform MUST expose the runtime storage layer behind a
`RuntimeStorePort` abstract class. The default and opt-in engines
MUST each implement the port without leaking backend-specific
details into the port surface.

#### Scenario: adapter swap does not change observable behaviour

Given a test that swaps the `SqliteRuntimeStore` default adapter for
a stub `InMemoryRuntimeStore` adapter implementing the same port
When the test writes and reads canonical chunks through the port
Then the observable behaviour (write/read round-trip, content
address, version stamp, WAL append, file lock) is identical between
the two adapters.

### Requirement: permissive license floor

The runtime storage engine libraries MUST all carry an SPDX
identifier that passes `LicenseGate` under the default
project-context.yaml `licensing.mode: strict` configuration. GPL,
AGPL, SSPL, Commons-Clause and `*-NC-*` licenses MUST NOT appear in
the runtime storage dependency inventory.

#### Scenario: license gate rejects non-permissive runtime storage library

Given a runtime storage library with SPDX `GPL-3.0-only`
When the Phase 1 `license-gate` runs over the dependency inventory
Then the gate reports the GPL library as `deny`
And the gate does not pass.

### Requirement: documented rationale for the rejected alternatives

The `embedded-storage-selection` ADR MUST record the rejected
alternatives with a one-line reason each. The rejected alternatives
MUST include at minimum:

- DuckDB;
- RocksDB;
- sled;
- LevelDB;
- Badger (and any other embedded KV-only engine).

#### Scenario: ADR lists every rejected alternative with rationale

Given a contributor who reads the ADR
When the contributor locates the "Rejected alternatives" section
Then the ADR names DuckDB, RocksDB, sled, LevelDB and Badger
And the ADR gives a one-line reason for each rejection.

### Requirement: enterprise profile opt-in

The runtime storage engine MUST be replaceable through the
`project-context.yaml:storage.backend` configuration value so the
enterprise-scale profile can opt into a different backend without
changing the public contract or the Phase 2 driver.

#### Scenario: postgres backend selection wires the PostgresRuntimeStore adapter

Given `project-context.yaml:storage.backend == "postgres"`
When `init-project` scaffolds the runtime cache
Then the project uses the `PostgresRuntimeStore` adapter
And the WAL and the per-project advisory file lock continue to
work unchanged.

