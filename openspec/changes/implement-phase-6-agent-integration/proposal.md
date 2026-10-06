# Proposal — Implement the v0.8 Phase 6 Agent Integration Capability Specs

## Why

This change adopts the ten Phase 6 capability specs
authored under
[`openspec/changes/prepare-phase-6-agent-integration/`](../../prepare-phase-6-agent-integration/)
and ships the production code that consumes them. The
Phase 6 capability surface is the agent integration layer
defined in §36-§51 of the v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)).

The Phase 1 foundation, Phase 2 ingestion, Phase 3
storage, Phase 4 retrieval and Phase 5 orchestration
changes are prerequisites. Phase 6 extends the Phase 5
orchestrator + capability discovery surface with the
MCP server, the canonical versioned Agent Skill, the
skill distribution plane, the version handshake, the four
plugin packagers, the agent adapter contract and the
plugin supply-chain security gate.

The preparation change
[`prepare-phase-6-agent-integration`](../../prepare-phase-6-agent-integration/)
authors the ten Phase 6 spec deltas (mcp-server,
skill-distribution-plane, agent-skill-canonical,
version-compatibility-handshake, codex-plugin-package,
claude-code-plugin-package, opencode-plugin-package,
generic-agent-bundle, agent-adapter-contract,
plugin-supply-chain-security). This implementation change
adopts those ten specs into `openspec/specs/2026-10-05-*/`
and ships the production code.

## Goal

Ship production code consuming the ten Phase 6 capability
specs. The implementation work:

- implements the MCP server
  (`pi_platform/mcp/server.py`) that exposes the 17 §36
  semantic tools plus `describe_capabilities` and
  composes the Phase 5 `QueryOrchestratorPort`,
  `LocalLLMPort`, `TaskContextBuilderPort`,
  `CapabilityDiscoveryPort` and the Phase 4
  `MultiStageRetrievalPort` /
  `HybridRetrievalPort` / `ContextAssemblerPort`. The
  server uses the official MCP Python SDK
  (`mcp==1.30.0`, Apache-2.0; SPDX entry confirmed via
  the harness-side MCP package — the implementation
  change confirms a shared or separate top-level entry
  in `distribution/licenses/dependency-inventory.json`
  before emitting the MCP server);
- ships the skill distribution plane
  (`pi_platform/mcp/skill_plane.py`) that exposes the
  §38 URI namespace (`project-intelligence://distribution
  /manifest`, `project-intelligence://skills/index`,
  `project-intelligence://skills/<name>/<version>/...`)
  as MCP resources;
- authors the canonical versioned Agent Skill at
  `distribution/skills/project-intelligence/SKILL.md`
  with the documented YAML frontmatter and the
  progressive-disclosure references
  (`MCP-TOOLS.md`, `RETRIEVAL-POLICY.md`,
  `VERSIONING.md`, `OKF-PROFILE.md`, `SECURITY.md`);
- implements the §39 version handshake
  (`pi_platform/ports/agent_integration/
  version_compatibility.py`,
  `pi_platform/core/agent_integration/
  version_compatibility.py`) for the 9 tracked version
  dimensions;
- ships the four per-vendor plugin packagers (Codex /
  Claude Code / OpenCode / generic agent) under
  `pi_platform/adapters/agent_integration/packagers/`;
- implements the `AgentIntegrationAdapter` port
  (`pi_platform/ports/agent_integration/adapter.py`,
  `pi_platform/core/agent_integration/adapter.py`)
  with the documented 8 operations and the typed
  error vocabulary;
- ships the plugin supply-chain security gate
  (`pi_platform/core/agent_integration/
  supply_chain_gate.py`) that every packager calls
  before emit;
- ships Wiki + ADR + archive + `openspec/CURRENT.md`
  updates as the close-out task 95.

What this change does:

- adopts the ten Phase 6 capability specs from
  [`prepare-phase-6-agent-integration/specs/`](../../prepare-phase-6-agent-integration/specs/)
  into `openspec/specs/2026-10-05-*/`;
- ships the production code under the documented
  modules and adapters;
- writes the documented per-capability regression
  tests (`tests/test_mcp_server`,
  `tests/test_skill_plane`,
  `tests/test_version_compatibility`,
  `tests/test_codex_plugin`,
  `tests/test_claude_code_plugin`,
  `tests/test_opencode_plugin`,
  `tests/test_generic_agent_bundle`,
  `tests/test_agent_adapter`,
  `tests/test_supply_chain_gate`);
- writes the §49 integration quality gate tests
  (skill activation, MCP tool-selection, retrieval-
  first compliance, version-mismatch, stale/conflict,
  security-filter, plugin install/uninstall smoke,
  OKF materialization/conformance, round-trip DB ↔
  Git, branch-switch, token / context-cost);
- updates the Wiki (new `interfaces/mcp-tools`,
  `interfaces/skill-distribution`,
  `interfaces/plugin-distribution`,
  `interfaces/version-compatibility`,
  `interfaces/agent-adapter-contract`,
  `interfaces/plugin-supply-chain`; new
  `modules/mcp-server`,
  `modules/agent-integration`,
  `modules/plugin-packagers`; new
  `adr/0011-agent-integration-packaging`,
  `adr/0012-version-compatibility-handshake`,
  `adr/0013-plugin-supply-chain-security`);
- updates `openspec/CURRENT.md` to add the ten Phase 6
  capabilities;
- flips `plan-v0-8-platform-architecture/tasks.md`
  rows 85-95 to `[x]`;
- archives the prep change under
  `archive/2026-10-05-prepare-phase-6-agent-integration/`;
- archives this implementation change under
  `archive/2026-10-05-implement-phase-6-agent-integration/`.

Out of scope for this change:

- any A2A integration work — Phase 10 tasks 119-123;
- the Phase 7 Control Plane and Feature / Plugin
  Registry — Phase 7 tasks 96-100;
- the Phase 8 enterprise security boundary — Phase 8
  tasks 105-110;
- the Phase 9 distribution one-click launcher — Phase
  9 tasks 111-118;
- the pre-existing harness-side MCP server at
  `tools/mcp/project-context-mcp/` — that is a
  different deliverable owned by the harness scope.

## Affected capabilities

This change adopts the ten additive capability specs
authored by the
[`prepare-phase-6-agent-integration`](../../prepare-phase-6-agent-integration/)
change. The ten specs are listed in
[`proposal.md`](../../prepare-phase-6-agent-integration/proposal.md#affected-capabilities)
and cover tasks 85-94 from
[`plan-v0-8-platform-architecture/tasks.md`](../../plan-v0-8-platform-architecture/tasks.md).
Task 95 (Wiki maintenance + ADR + archive + `CURRENT.md`)
is the close-out task and does not require its own
capability spec.

## Compatibility / migration impact

This change adopts ten new capability specs and ships
the corresponding production code. It does NOT modify
the accepted Phase 1-5 capability specs under
`openspec/specs/`. It does NOT touch the pre-existing
harness-side MCP server at
`tools/mcp/project-context-mcp/`.

## Related knowledge

- `kb://architecture.platform-overview` — extended
  with the Phase 6 module map;
- `kb://glossary.platform` — extended with the Phase 6
  vocabulary;
- new `kb://interfaces.mcp-tools`,
  `kb://interfaces.skill-distribution`,
  `kb://interfaces.plugin-distribution`,
  `kb://interfaces.version-compatibility`,
  `kb://interfaces.agent-adapter-contract`,
  `kb://interfaces.plugin-supply-chain`;
- new `kb://modules.mcp-server`,
  `kb://modules.agent-integration`,
  `kb://modules.plugin-packagers`;
- new `kb://adr.0011-agent-integration-packaging`,
  `kb://adr.0012-version-compatibility-handshake`,
  `kb://adr.0013-plugin-supply-chain-security`;
- external:
  `project-intelligence-platform-architecture-v0.8.md`
  §5, §17, §33, §36, §37, §38, §39, §40, §41, §42,
  §43, §44, §45, §46, §47, §48, §49.