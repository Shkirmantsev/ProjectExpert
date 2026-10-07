---
id: adr.0011-agent-integration-packaging
title: "ADR 0011: Phase 6 agent integration packaging"
kind: adr
status: accepted
summary: Adopt the ports-and-adapters boundary between the platform core and the four per-vendor agent-integration packagers (Codex, Claude Code, OpenCode, generic agent); the platform remains vendor-neutral and the packagers consume one shared release input set.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#40
  - project-intelligence-platform-architecture-v0.8.md#41
  - project-intelligence-platform-architecture-v0.8.md#42
  - project-intelligence-platform-architecture-v0.8.md#43
  - project-intelligence-platform-architecture-v0.8.md#44
  - project-intelligence-platform-architecture-v0.8.md#45
  - project-intelligence-platform-architecture-v0.8.md#46
  - openspec/specs/2026-10-05-codex-plugin-package/spec.md
  - openspec/specs/2026-10-05-claude-code-plugin-package/spec.md
  - openspec/specs/2026-10-05-opencode-plugin-package/spec.md
  - openspec/specs/2026-10-05-generic-agent-bundle/spec.md
  - openspec/specs/2026-10-05-agent-adapter-contract/spec.md
maintenance:
  mode: authored
---

# ADR 0011: Phase 6 agent integration packaging

- Status: accepted
- Date: 2026-10-07
- Deciders: Phase 6 implementation change
- Source spec: ten Phase 6 capability specs (mcp-server,
  skill-distribution-plane, agent-skill-canonical,
  version-compatibility-handshake, codex-plugin-package,
  claude-code-plugin-package, opencode-plugin-package,
  generic-agent-bundle, agent-adapter-contract,
  plugin-supply-chain-security)
- Architecture baseline:
  [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
  §40 (Agent Integration Packaging Layer), §41 (Codex),
  §42 (Claude Code), §43 (OpenCode), §44 (Generic Agent),
  §45 (Plugin Generation Pipeline), §46 (Agent Adapter
  Contract)

## Context

The platform must ship installable integration packages for
the major coding-agent ecosystems without making vendor
configuration leak into the retrieval / domain core. §40
requires a clear Ports-and-Adapters boundary between the core
and the per-vendor adapters. §45 requires every per-vendor
package to be generated from one shared release input and to
agree on the shared release identity.

## Options

1. **Hand-written per-vendor packages**, maintained as
   independent copies. (Rejected — drift between vendors,
   hard to keep shared release identity in sync.)
2. **Single shared adapter with vendor-specific flags**.
   (Rejected — vendor configuration leaks into core.)
3. **Ports-and-Adapters boundary with one packager per
   vendor** plus a deterministic build runner. (Chosen.)

## Decision

Adopt a `AgentIntegrationPort` boundary
(`pi_platform/ports/agent_integration/`) plus four
per-vendor packagers under
`pi_platform/adapters/agent_integration/packagers/`. The
`DeterministicBuildRunner` coordinates the four packagers
from one `ReleaseInputSet` and asserts the shared release
identity (skill content hash, version, MCP API range,
license, server identity). Adapters expose the 13 documented
operations (`detect`, `install`, `configure_mcp`,
`install_skill`, `verify_compatibility`, `health_check`,
`uninstall`, `describe`) and MUST NOT own retrieval or
business rules.

## Consequences

- Per-vendor packages are generated deterministically; two
  isolated runs at different absolute paths produce
  byte-identical artifacts.
- The platform core stays vendor-neutral.
- The supply-chain security gate (§48) runs before every
  packager emits its bundle; the verdict is recorded in the
  bundle's `PROVENANCE.json`.
- Vendor-specific lifecycles (Codex plugin manager,
  Claude Code plugin manager, OpenCode plugin / npm
  install, generic drop-in) can be exercised in isolated
  temporary projects without polluting the canonical
  harness repo.