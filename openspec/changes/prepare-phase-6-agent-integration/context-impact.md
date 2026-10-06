# Context impact — prepare-phase-6-agent-integration

## Knowledge to create

The Wiki nodes below are NOT created by this change; they
are listed as future work the
`implement-phase-6-agent-integration` change must
perform when it ships the production code.

- `.ai/wiki/interfaces/mcp-tools.md` — the Phase 6 MCP
  server contract (17 §36 semantic tools plus
  `describe_capabilities`); the §47 capability
  descriptor delegation; the §39 typed
  `VersionIncompatibleError`; the §48 approval-gated
  write / materialisation contract.
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/skill-distribution.md` — the
  Phase 6 skill distribution plane (`project-
  intelligence://distribution/manifest`,
  `project-intelligence://skills/index`,
  `project-intelligence://skills/<name>/<version>/...`)
  with the §38 manifest schema and the snapshot /
  runtime parity contract.
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/plugin-distribution.md` — the
  Phase 6 per-vendor plugin distribution contract
  (Codex / Claude Code / OpenCode / generic), the
  deterministic-build expectation, the §45 plugin
  generation pipeline and the per-vendor entry points.
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/version-compatibility.md` — the
  Phase 6 version handshake contract (9 §39 dimensions,
  semver range parsing, typed
  `VersionIncompatibleError`, compatibility adapter
  support).
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/agent-adapter-contract.md` — the
  Phase 6 `AgentIntegrationAdapter` port contract (8
  §46 operations, plug-in replaceable installers,
  typed error vocabulary).
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/plugin-supply-chain.md` — the
  Phase 6 plugin supply-chain security gate (§48
  release controls, deterministic-build expectation,
  approval-gated materialise tools).
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/modules/mcp-server.md` — the Phase 6 MCP
  server module map
  (`pi_platform/mcp/server.py`,
  `pi_platform/mcp/tools.py`).
  `kind: modules`, `status: draft`.
- `.ai/wiki/modules/agent-integration.md` — the Phase 6
  agent integration module map
  (`pi_platform/ports/agent_integration/`,
  `pi_platform/core/agent_integration/`,
  `pi_platform/adapters/agent_integration/`).
  `kind: modules`, `status: draft`.
- `.ai/wiki/modules/plugin-packagers.md` — the Phase 6
  plugin packager module map (Codex / Claude Code /
  OpenCode / generic agent packagers under
  `pi_platform/adapters/agent_integration/packagers/`).
  `kind: modules`, `status: draft`.
- `.ai/wiki/adr/0011-agent-integration-packaging.md`
  — the Phase 6 ADR that records the
  §40 Ports-and-Adapters boundary, the
  §41-§44 per-vendor profile decision, the §45
  deterministic-build expectation, the §46 adapter
  contract decision and the §48 supply-chain gate
  decision.
- `.ai/wiki/adr/0012-version-compatibility-handshake.md`
  — the Phase 6 ADR that records the §39 trade-off
  matrix (semver-range enforcement vs. major-version-
  only policy, hash-pinned integrity vs. signed-
  manifest).
- `.ai/wiki/adr/0013-plugin-supply-chain-security.md`
  — the Phase 6 ADR that records the §48 trade-off
  matrix (hash-pinned integrity vs. signed-manifest,
  per-vendor licence review vs. `LicenseGate`
  automated allow-list, hidden-auto-install block,
  approval-gated materialise tools).

## Knowledge to update

The Wiki updates below are NOT performed by this change;
they are listed as future work the
`implement-phase-6-agent-integration` change must
perform alongside the production code.

- `.ai/wiki/architecture/platform-overview.md` — extend
  the Phase 1-5 module map with the Phase 6 module map
  (`mcp/`, `ports/agent_integration`,
  `adapters/agent_integration`,
  `distribution/skills/`, `distribution/codex/`,
  `distribution/claude-code/`,
  `distribution/opencode/`,
  `distribution/generic-agent/`). Reference the new
  `modules/mcp-server.md`, `modules/agent-integration
  .md` and `modules/plugin-packagers.md` nodes.
- `.ai/wiki/architecture/system-overview.md` — extend
  the "Principal components" section with the Phase 6
  MCP server reference and links to the new module /
  interface nodes. Note the MCP server is a thin
  adapter that composes the Phase 5 orchestrator and
  the Phase 4 retrieval / context assembly surface.
- `.ai/wiki/glossary/platform.md` — add Phase 6
  vocabulary entries: `McpServer`,
  `SkillDistributionPlane`, `DistributionManifest`,
  `SkillIndex`, `SkillVersionedUri`,
  `CanonicalAgentSkill`, `SkillMetadataContract`,
  `VersionCompatibilityPolicy`,
  `VersionCompatibilityError`,
  `AgentIntegrationAdapter`, `AdapterDetectionReport`,
  `AdapterInstallReport`, `AdapterConfigureReport`,
  `AdapterCompatibilityReport`, `AdapterHealthReport`,
  `AdapterUninstallReport`, `AdapterDescriptor`,
  `PluginPackager`, `PluginSupplyChainSecurityGate`.
  Status flips from `draft` to `active` once the
  implementation lands.
- `.ai/wiki/glossary/domain.md` — cross-link to the
  platform vocabulary for the new entries.
- `.ai/wiki/project/project-map.md` — add the new
  module folders under "Main source areas" with status
  `planned` until the implementation change lands; flip
  to `active` once the code is on disk. Add
  `distribution/skills/`,
  `distribution/codex/`,
  `distribution/claude-code/`,
  `distribution/opencode/`,
  `distribution/generic-agent/` under "Distribution".
- `.ai/wiki/project/implementation-roadmap.md` — add
  the Phase 6 row to the phase table.
- `.ai/wiki/INDEX.md` — add the new Wiki modules,
  interfaces and ADRs once they exist on disk; the
  future implementation change is responsible for the
  index update.
- `openspec/CURRENT.md` — add the ten Phase 6
  capabilities once the future
  `implement-phase-6-agent-integration` change is
  archived; this change does NOT modify
  `openspec/CURRENT.md`.

## Knowledge to review for staleness

- `.ai/wiki/architecture/platform-overview.md` —
  review the Phase 1-5 module map and ensure the
  Phase 6 extensions remain additive; the existing
  Phase 1-5 boundaries MUST stay unchanged.
- `.ai/wiki/architecture/system-overview.md` — review
  the Phase 1-5 principal components and ensure the
  Phase 6 MCP server is presented as a thin adapter
  that does NOT introduce a new runtime store.
- `.ai/wiki/glossary/platform.md` — review the Phase
  1-5 vocabulary; Phase 6 adds new entries
  (`McpServer`, `SkillDistributionPlane`,
  `VersionCompatibilityPolicy`,
  `AgentIntegrationAdapter`, `PluginPackager`,
  `PluginSupplyChainSecurityGate`). The existing
  `QueryOrchestrator`, `LocalLLMPort`,
  `TaskContextBuilder`, `CapabilityDiscovery`,
  `CapabilityDescriptor`, `CapabilityFeatures`,
  `OrchestrationResult`, `OrchestrationLevel`,
  `TaskContextBundle` entries remain unchanged.
- `.ai/wiki/interfaces/capability-discovery.md` —
  review the Phase 5 capability-discovery contract;
  the Phase 6 MCP `describe_capabilities` tool
  delegates to the `CapabilityDiscoveryPort.describe`.
  The Phase 5 contract MUST NOT change.
- `.ai/wiki/modules/orchestrator.md` — review the
  Phase 5 orchestrator module map; the Phase 6 MCP
  server composes the orchestrator. The Phase 5
  orchestrator contract MUST NOT change.
- `.ai/wiki/modules/llm-port.md` — review the Phase 5
  LLM port module map; the Phase 6 MCP `describe_
  capabilities` tool reports the LLM availability
  through the §47 capability descriptor. The Phase 5
  LLM port contract MUST NOT change.
- `.ai/wiki/modules/task-context.md` — review the
  Phase 5 task context builder module map; the Phase
  6 MCP `project.build_task_context` tool delegates
  to the Phase 5 `TaskContextBuilderPort`. The
  Phase 5 task context builder contract MUST NOT
  change.
- `.ai/wiki/adr/0002-canonical-runtime-separation.md`
  — review the canonical / runtime separation
  invariants; the Phase 6 MCP server does NOT invent a
  new runtime store but composes the Phase 3 stack
  and the Phase 4 / Phase 5 surface. The ADR is
  unchanged in this change; the future implementation
  change adds the Phase 6 module map without
  modifying the ADR text.
- `.ai/wiki/adr/0003-license-governance-default.md`
  — review the licence-governance default; every
  Phase 6 dependency (MCP SDK, plugin runtime, plugin
  model weights) requires an SPDX-tracked inventory
  entry. The MCP Python SDK entry is already present
  via the harness-side MCP package; the future
  implementation change confirms a shared or separate
  top-level entry in
  `distribution/licenses/dependency-inventory.json`
  before emitting the MCP server.
- `.ai/wiki/adr/0005-platform-source-language.md` —
  review the Python 3.11 decision; the Phase 6 MCP
  server is Python. The OpenCode plugin adapter MAY
  use TypeScript / JavaScript and stays under
  `pi_platform/adapters/agent_integration/` rather
  than as a new platform-level language dependency.
  The ADR is unchanged in this change.
- `tools/mcp/project-context-mcp/` — the pre-existing
  harness-side MCP server at
  `tools/mcp/project-context-mcp/` is NOT Phase 6
  work. It is the development-harness MCP server that
  exposes `kb_search`, `kb_get`, `kb_neighbors`,
  `code_symbol`, `spec_context`, `jar_search`,
  `jar_api`, `kb_validate`, `kb_refresh` for the
  harness. The Phase 6 deliverable is the platform's
  `pi_platform/mcp/` package, which is a separate
  deliverable owned by the Phase 6 implementation
  change. The two MCP servers MUST NOT be confused;
  the future implementation change documents the
  distinction in the Wiki.

## Related knowledge

- external:
  `project-intelligence-platform-architecture-v0.8.md`
  §5, §17, §33, §36, §37, §38, §39, §40, §41, §42,
  §43, §44, §45, §46, §47, §48, §49 — every cited
  section is authoritative for the Phase 6 capability
  contracts.