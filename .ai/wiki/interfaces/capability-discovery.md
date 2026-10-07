---
id: interfaces.capability-discovery
title: CapabilityDiscoveryPort contract
kind: interfaces
status: active
summary: Phase 5 §47 CapabilityDiscovery — deterministic capability descriptor the Phase 6 MCP `describe_capabilities` tool exposes and skills / plugins consume.
sourceRefs:
  - pi_platform/ports/orchestration/capability_discovery.py
  - pi_platform/core/orchestration/capability_discovery.py
  - pi_platform/adapters/orchestration/capability_discovery.py
  - openspec/specs/2026-10-05-capability-discovery/spec.md
maintenance:
  mode: authored
related:
  - modules.orchestrator
  - modules.llm-port
  - modules.task-context
---

# CapabilityDiscoveryPort contract

The §47 capability discovery port returns the
deterministic `CapabilityDescriptor` JSON that the
Phase 6 MCP server exposes via `describe_capabilities`
and that skills / plugins consume to adapt to the actual
deployment. The descriptor is the source of truth the
agents and skills use to avoid assuming a feature is
available.

## Surface

- `describe() -> CapabilityDescriptor` — return the
  deterministic capability descriptor for the current
  deployment.
- `refresh() -> CapabilityDescriptor` — re-evaluate the
  runtime registrations and return the updated
  descriptor.
- `stats() -> Mapping[str, int]` — operational counters
  including `describe_calls`, `refresh_calls` and
  `feature_count`.

## CapabilityDescriptor

The descriptor carries:

- `serverVersion` (str) — the platform server version
  (semver);
- `mcpApiVersion` (str) — the MCP API version the server
  speaks (semver);
- `knowledgeSchemaVersion` (str) — the canonical
  knowledge schema version (semver);
- `okfVersions` (Sequence[str]) — the OKF profiles the
  platform accepts;
- `features` (CapabilityFeatures) — a structured map
  of optional features.

## CapabilityFeatures

The features map carries:

- `hybridRetrieval` (bool) — `True` when the Phase 4
  `HybridRetrievalPort` is registered.
- `graphExpansion` (bool) — `True` when the Phase 4
  production `GraphExpansion` adapter is registered.
- `okf` (Sequence[str]) — the OKF profiles the platform
  accepts (duplicate of `okfVersions` for backward
  compatibility).
- `materialization` (bool) — `True` when the Phase 1
  materialise service is available.
- `a2a` (bool) — `True` when the Phase 10 A2A adapter is
  registered (always `False` until Phase 10 ships).
- `localLlm` (bool) — `True` when the Phase 5
  `LocalLLMPort.is_available() == True`.

## Determinism

The descriptor serialises to a stable JSON string for
a fixed deployment state. Two consecutive `describe`
calls return byte-identical JSON. Skills and plugins
read the descriptor at startup; they MUST NOT assume
every deployment exposes every optional feature.

## CLI surface

- `python -m pi_platform.cli capabilities` — emits the
  §47 JSON descriptor with the active
  `serverVersion`, `mcpApiVersion`,
  `knowledgeSchemaVersion`, `okfVersions` and
  `features` map.