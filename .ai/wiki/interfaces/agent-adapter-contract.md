---
id: interfaces.agent-adapter-contract
title: Agent integration adapter contract
kind: interfaces
status: active
summary: Phase 6 §46 — eight documented operations every vendor adapter implements; typed error vocabulary; adapters MUST NOT own retrieval or business rules.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#46
  - pi_platform/ports/agent_integration/adapter.py
  - pi_platform/core/agent_integration/adapter.py
  - openspec/specs/2026-10-05-agent-adapter-contract/spec.md
maintenance:
  mode: authored
related:
  - interfaces.plugin-distribution
  - interfaces.plugin-supply-chain
---

# Agent integration adapter contract

The §46 agent-integration adapter contract is the
narrow interface every vendor adapter implements:

| Operation | Purpose |
|---|---|
| `detect(target_root)` | Identify the installed vendor client; raise `UnsupportedClientError` on mismatch. |
| `install(target_root, *, skill_version, mcp_endpoint, client_version=None)` | Run install + configure_mcp + install_skill. |
| `configure_mcp(target_root, *, mcp_endpoint)` | Configure the vendor MCP file(s). |
| `install_skill(target_root, *, skill_version)` | Install the canonical skill. |
| `verify_compatibility(target_root)` | Run the §39 handshake. |
| `health_check(target_root)` | Produce `AdapterHealthReport`. |
| `uninstall(target_root)` | Remove adapter-managed files; preserve user entries. |
| `describe()` | Stable description of vendor + supported client version. |

## Typed errors

- `UnsupportedClientError` — installed client version
  does not match the supported profile.
- `InstallRefusedError` — required install inputs
  missing.
- `CapabilityMismatchError` — the §39 handshake fails
  for the installed client.
- `AdapterError` — generic adapter-level failure.

## Constraints

Adapters MUST NOT own retrieval, LLM, or materialise
operations; the actual knowledge / business logic
remains in the Project Intelligence core. Adapters
manipulate only owned configuration files (vendor MCP
config, vendor skill install location, vendor manifest).

## Vendor profile

The adapter is bound to a `VendorProfile` carrying
`vendor`, `client_version` and `schema_url`. The
default `DefaultAgentIntegrationAdapter` base class
records the profile and refuses installation against
unsupported client versions.