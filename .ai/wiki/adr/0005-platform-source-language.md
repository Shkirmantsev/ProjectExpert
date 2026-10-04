---
id: adr.platform-source-language
title: Use Python 3.11 as the platform source language for Phase 1
kind: adr
status: accepted
summary: Implement the Phase 1 platform foundation in Python 3.11; keep adapter ports language-neutral so a Java runtime can be added later if a workload requires it.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md
  - openspec/changes/implement-phase-1-foundation/design.md
maintenance:
  mode: authored
---

# Use Python 3.11 as the platform source language for Phase 1

## Context

The v0.8 architecture
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
is implementation-language-neutral. The Phase 1 foundation must
provide deterministic canonical serialization, SHA-256 content
addressing, Git CLI integration, hydrate/reconcile/materialise
services and a license gate. None of these capabilities intrinsically
require Java; the harness framework already targets Python.

The
[`plan-v0-8-platform-architecture/design.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md)
file requires every product module to expose ports behind
adapters; the core domain is not coupled to any specific runtime.

## Decision

The Phase 1 platform foundation is implemented in **Python 3.11**
using only the standard library plus two lightweight MIT/Apache-2.0
dependencies (`PyYAML` for OKF frontmatter, `packaging` for version
comparisons) that pass the documented permissive license policy.

A Java back-end can be introduced later as an adapter behind a
stable port if a workload (e.g. Java source intelligence, JAR
intelligence) requires it. Phase 1 stays language-neutral at the
boundary by declaring every Phase 1 capability as a port in
`platform/ports/` and shipping the default adapter in
`platform/adapters/`.

## Alternatives considered

- **Java 21.** Rejected for Phase 1 because the foundation modules
  do not require JVM semantics; using Java would multiply the
  build/test/Maven surface for no Phase 1 benefit. The architecture
  reserves a Java adapter slot for later ingestion and JAR
  intelligence work.
- **Rust.** Rejected because the harness and the agent ecosystem are
  Python-heavy and a second language would raise the contributor
  baseline without addressing any Phase 1 workload concern.
- **Polyglot from day one.** Rejected because the v0.8 architecture
  requires a single modular deployable. A polyglot default would
  duplicate the build pipeline, the licensing gate and the test
  runner.

## Consequences

- Phase 1 ships a `platform/` Python package importable via
  `python -m platform.cli` and installable via `pip install -e .`
  in the container image.
- The licence policy is enforced at the dependency level by the
  Phase 1 CI license gate. New runtime dependencies in later
  phases MUST have an SPDX identifier before being added to the
  inventory; they MAY add Python packages that pass the gate
  without further architectural changes.
- A Java back-end can be added in Phase 2 or later by introducing
  a `platform.adapters.java.javadoc/` adapter (or equivalent) that
  exposes the same ports as the Python core. No core domain code
  changes when this happens.

## Verification

`openspec/changes/implement-phase-1-foundation/tasks.md` records
the Phase 1 implementation tasks 1-10 that exercise this decision.
`tests/test_license_gate.py` and `tests/test_license_policy.py`
cover the dependency-policy side of the language choice. The
container `Containerfile` builds the `python:3.11-slim` base.