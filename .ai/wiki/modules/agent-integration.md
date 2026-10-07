---
id: modules.agent-integration
title: Phase 6 agent-integration core module
kind: modules
status: active
summary: Phase 6 §40 / §46 / §48 core — agent integration adapter base class, version compatibility handshake, supply-chain security gate, trusted approval boundary and readiness gate.
sourceRefs:
  - pi_platform/ports/agent_integration/__init__.py
  - pi_platform/ports/agent_integration/adapter.py
  - pi_platform/core/agent_integration/version_compatibility.py
  - pi_platform/core/agent_integration/supply_chain_gate.py
  - pi_platform/core/agent_integration/adapter.py
  - pi_platform/core/sync/trusted_approval.py
  - pi_platform/core/sync/readiness.py
maintenance:
  mode: authored
related:
  - interfaces.version-compatibility
  - interfaces.agent-adapter-contract
  - interfaces.plugin-supply-chain
  - interfaces.trusted-approval-boundary
---

# Phase 6 agent-integration core module

The `pi_platform/core/agent_integration/` package
contains the Phase 6 cross-cutting core:

| Module | Purpose |
|---|---|
| `version_compatibility.py` | `DefaultVersionCompatibilityPolicy` — semver / identifier-set handshake. |
| `supply_chain_gate.py` | `PluginSupplyChainSecurityGate` — ten documented controls. |
| `adapter.py` | `DefaultAgentIntegrationAdapter` — base for the eight documented operations. |

The companion sync ports
(`pi_platform/core/sync/trusted_approval.py`,
`pi_platform/core/sync/readiness.py`) provide the
write-tool gate (`TrustedApprovalBoundary`) and the
read-tool gate (`KnowledgeReadinessPort`).

## Constraints

- Adapters MUST NOT own retrieval, LLM, or
  materialise operations.
- The version handshake reports unavailable
  dimensions as unavailable, never invents them.
- The supply-chain gate reports signature support as
  declared-but-unverified when no trusted key is
  configured.
- The trusted approval boundary rejects every token
  until an operator key is configured (closed
  default).