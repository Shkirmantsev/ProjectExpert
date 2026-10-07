# Proposal — Prepare the v0.8 Phase 6 Agent Integration Capability Specs

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the agent integration layer as the sixth
implementation phase (§36-§51, §5, §17). Phase 6 turns the
Phase 5 `QueryOrchestratorPort`, `LocalLLMPort`,
`TaskContextBuilderPort`, `CapabilityDiscoveryPort` and
the §47 capability descriptor into a production MCP server
that exposes the Phase 1-5 surface to external coding
agents through 17 semantic tools, distributes the canonical
versioned Agent Skill, ships first-class Codex / Claude Code /
OpenCode / generic agent bundles, enforces the §39 version
handshake and applies the §48 supply-chain security gate.

The Phase 1 foundation, Phase 2 ingestion, Phase 3
storage, Phase 4 retrieval and Phase 5 orchestration
changes are prerequisites. Phase 1 supplies the canonical
`TaskContext` value type, the Git-version-aware runtime,
the bidirectional sync, the `MaterialiseService` approval
contract and the licence gate; Phase 2 supplies the
canonical chunks and entity / relation records that the
Phase 6 MCP read tools surface; Phase 3 supplies the
sparse / dense / full-text indexes, the sharded graph,
the `ProvenancePort` / `KnowledgeState` and the
`FreshnessTracker` that the MCP tools compose; Phase 4
supplies the `MultiStageRetrievalPort`,
`HybridRetrievalPort` and `ContextAssemblerPort` that the
Phase 6 MCP `project.search` and
`project.retrieve_context` tools compose; Phase 5 supplies
the `QueryOrchestratorPort`, `LocalLLMPort`,
`TaskContextBuilderPort` and `CapabilityDiscoveryPort`
that the MCP server composes and the §47 descriptor that
`describe_capabilities` exposes.

Without Phase 6 specs there is no authoritative
behavioural contract for the 17 semantic MCP tools, the
canonical Agent Skill, the version handshake, the plugin
distribution plane or the supply-chain security gate.
Phase 7's Control Plane and Feature / Plugin Registry have
no MCP server to register; Phase 8's enterprise security
boundary has no MCP server to wrap; Phase 9's distribution
has no plugins to launch; Phase 10's A2A delegation has no
MCP surface to complement.

This change resolves the gap by authoring ten Phase 6
capability specs and the supporting design,
context-impact and tasks, while shipping zero production
code. The implementation work is proposed under
`implement-phase-6-agent-integration`; its mirrored deltas remain future
requirements until implementation, verification and adoption. Preparation
completion does not adopt these capabilities. At adoption, reconcile the
provisional `2026-10-07-*` delta identities in both changes to the actual first
Git acceptance date, then promote exactly one delta set. Archive preparation
without reapplying its duplicate ADDED requirements.

## Goal

Author the Phase 6 capability specs and change artifacts
so that a later `implement-phase-6-agent-integration`
change can:

- implement the MCP server (`pi_platform.mcp.server.McpServer`)
  exposing the 17 §36 semantic tools plus
  `describe_capabilities`. The MCP server is a thin
  adapter that composes the Phase 5
  `QueryOrchestratorPort` / `LocalLLMPort` /
  `TaskContextBuilderPort` / `CapabilityDiscoveryPort`,
  the Phase 4 `MultiStageRetrievalPort` /
  `HybridRetrievalPort` / `ContextAssemblerPort` and the
  Phase 1 `MaterialiseService` through the §36 tool
  surface; the server MUST NOT introduce a new runtime
  store. The server uses the official MCP Python SDK
  (`mcp==1.30.0`, Apache-2.0; SPDX entry already present
  via the harness-side MCP package) and ships in the
  default container with stdio as the default transport.
- implement the skill distribution plane
  (`project-intelligence://distribution/manifest`,
  `project-intelligence://skills/index`,
  `project-intelligence://skills/<name>/<version>/...`)
  as MCP resources the server exposes for clients that
  need runtime discovery. The plane complements the
  build / install-time snapshot path used by vendors that
  package the skill statically.
- author the canonical versioned Agent Skill at
  `distribution/skills/project-intelligence/SKILL.md`
  per §37 with progressive disclosure (`references/`
  contains `MCP-TOOLS.md`, `RETRIEVAL-POLICY.md`,
  `VERSIONING.md`, `OKF-PROFILE.md`, `SECURITY.md`).
  The skill ships under Apache-2.0 and declares its
  `mcp-api`, `knowledge-schema`, `okf-profile` and
  `distribution-schema` metadata.
- implement the version-compatibility handshake (§39) for
  the 9 tracked version dimensions
  (`platformVersion`, `mcpApiVersion`,
  `a2aAdapterVersion`, `knowledgeSchemaVersion`,
  `okfProfileVersion`, `skillVersion`,
  `pluginDistributionSchemaVersion`,
  `agentAdapterVersion`, `runtimeIndexSchemaVersion`)
  using semver ranges for public APIs and explicit identifier sets for profiles/schemas. The handshake MUST be
  machine-checkable, MUST run without an LLM and MUST
  return a typed `VersionIncompatibleError` with the
  supported range when the client's declared range does
  not intersect.
- ship the Codex / ChatGPT plugin packager that emits
  `dist/codex/{plugin.json, mcp.json, skills/, assets/}`
  with a `.codex-plugin/plugin.json` compatibility
  fallback. The packager MUST validate skill / MCP
  compatibility during packaging, MUST include the
  skill content hash in the plugin manifest and MUST be
  deterministic across the complete output tree so two runs produce
  the same artifacts.
- ship the Claude Code plugin packager that emits
  `dist/claude-code/{.claude-plugin/plugin.json,
  .mcp.json, skills/, optional commands/, agents/,
  README.md}`. The plugin slug MUST be stable after
  public release.
- ship the OpenCode plugin package that emits
  `dist/opencode/{package.json, plugin/*.ts, skill/,
  config/opencode.example.jsonc, README.md}`. The
  package MUST be npm-publishable OR local-project-usable
  and MUST expose a TypeScript or JavaScript plugin
  adapter.
- ship the generic agent bundle that emits
  `dist/generic-agent/{skills/, mcp/{stdio-example.json,
  http-example.json}, AGENTS.example.md, README.md}`
  maximising compatibility through standard MCP, Agent
  Skills, plain Markdown instructions and optional A2A.
- implement the agent adapter contract (§46) as
  `AgentIntegrationAdapter` with `detect`, `install`,
  `configureMcp`, `installSkill`,
  `verifyCompatibility`, `healthCheck`, `uninstall`,
  `describe`. The contract supports one-click setup
  while keeping installers replaceable; adapters MUST
  NOT own retrieval / business rules.
- ship the plugin supply-chain security gate (§48) as a
  verification function the packagers call before
  emit. The gate MUST check pinned version, content
  hash, license, SBOM, malware / secret scan,
  deterministic build, signature support, source
  provenance, permissions and the absence of hidden
  auto-install. The gate MUST keep write /
  materialisation tools approval-controlled even when a
  skill or plugin requests them.

What this change does:

- proposes the ten Phase 6 capability specs under
  `openspec/changes/prepare-phase-6-agent-integration/specs/`;
- documents the technical design covering the MCP
  server, the skill distribution plane, the canonical
  Agent Skill, the version handshake, the four
  plugin-packager profiles (Codex, Claude Code,
  OpenCode, generic), the agent adapter contract and
  the plugin supply-chain security gate;
- creates the `implement-phase-6-agent-integration`
  change folder under
  `openspec/changes/implement-phase-6-agent-integration/`
  and mirrors the ten delta specs verbatim so the future
  implementation archive carries the same delta set;
- lists the Wiki, ADR and context-impact nodes the
  future `implement-phase-6-agent-integration` change
  will need to create or update;
- enumerates Phase 6 tasks 85-95 (mirroring
  [`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md))
  with concrete verification commands; task 95 is the
  close-out task and does not require its own
  capability spec.

Out of scope for this change:

- any production code under `pi_platform/mcp/`,
  `pi_platform/adapters/agent_integration/`,
  `distribution/skills/`, `distribution/codex/`,
  `distribution/claude-code/`,
  `distribution/opencode/`,
  `distribution/generic-agent/` or any related Phase 6
  module;
- any addition to the runtime dependency inventory
  beyond the MCP Python SDK entry already approved via
  the harness-side MCP server; the future
  `implement-phase-6-agent-integration` change MAY add
  one optional TypeScript / JavaScript runtime for the
  OpenCode plugin adapter, but only after each
  SPDX-tracked license inventory entry passes
  `LicenseGate`;
- the MCP server (task 85), skill distribution plane
  (task 86), canonical Agent Skill (task 87), version
  handshake (task 88), four plugin packagers (tasks
  89-92), agent adapter contract (task 93), supply-chain
  security gate (task 94) and Wiki maintenance
  (task 95) — all Phase 6 implementation work;
- the Wiki materialisation, control plane, security
  enterprise boundary, distribution one-click launcher,
  A2A — Phase 7+ tasks 96-123;
- the pre-existing harness-side MCP server at
  `tools/mcp/project-context-mcp/` — that is a different
  deliverable owned by the harness scope, not by the
  Phase 6 platform scope; the Phase 6
  `pi_platform/mcp/` package is a separate deliverable
  that the Phase 6 implementation change owns;
- archiving this change. The change stays active
  (proposal-only) until the future
  `implement-phase-6-agent-integration` change uses it
  as prerequisite.

## Affected capabilities

This change introduces the following additive capability
specs. None of the five accepted Phase 1 specs, the nine
accepted Phase 2 specs, the nine accepted Phase 3 specs,
the eight accepted Phase 4 specs or the five accepted
Phase 5 specs is modified or retired. Phase 6 specs depend
on the Phase 1 specs (canonical schema, Git-version-aware
runtime, repository layout, `MaterialiseService`
approval contract, licence governance), the Phase 2 specs
(content-addressed processing, semantic-structural
chunking, context enrichment), the Phase 3 specs (runtime
store, sparse / dense / full-text indexes, sharded graph,
provenance / `KnowledgeState`, freshness tracking), the
Phase 4 specs (multi-stage retrieval, context assembler,
embedding model) and the Phase 5 specs (query
orchestrator, local LLM port, task context builder,
capability discovery, retrieval-first policy) but do not
alter their normative content.

| New capability | Architecture sections | Phase 6 task(s) | Spec delta path |
|---|---|---|---|
| `mcp-server` | §36, §47 | 85, 95 | [`specs/2026-10-07-mcp-server/spec.md`](specs/2026-10-07-mcp-server/spec.md) |
| `skill-distribution-plane` | §38, §37 | 86, 95 | [`specs/2026-10-07-skill-distribution-plane/spec.md`](specs/2026-10-07-skill-distribution-plane/spec.md) |
| `agent-skill-canonical` | §37, §39 | 87, 95 | [`specs/2026-10-07-agent-skill-canonical/spec.md`](specs/2026-10-07-agent-skill-canonical/spec.md) |
| `version-compatibility-handshake` | §39, §47 | 88, 95 | [`specs/2026-10-07-version-compatibility-handshake/spec.md`](specs/2026-10-07-version-compatibility-handshake/spec.md) |
| `codex-plugin-package` | §41, §45 | 89, 95 | [`specs/2026-10-07-codex-plugin-package/spec.md`](specs/2026-10-07-codex-plugin-package/spec.md) |
| `claude-code-plugin-package` | §42, §45 | 90, 95 | [`specs/2026-10-07-claude-code-plugin-package/spec.md`](specs/2026-10-07-claude-code-plugin-package/spec.md) |
| `opencode-plugin-package` | §43, §45 | 91, 95 | [`specs/2026-10-07-opencode-plugin-package/spec.md`](specs/2026-10-07-opencode-plugin-package/spec.md) |
| `generic-agent-bundle` | §44, §45 | 92, 95 | [`specs/2026-10-07-generic-agent-bundle/spec.md`](specs/2026-10-07-generic-agent-bundle/spec.md) |
| `agent-adapter-contract` | §46, §40 | 93, 95 | [`specs/2026-10-07-agent-adapter-contract/spec.md`](specs/2026-10-07-agent-adapter-contract/spec.md) |
| `plugin-supply-chain-security` | §48, §45 | 94, 95 | [`specs/2026-10-07-plugin-supply-chain-security/spec.md`](specs/2026-10-07-plugin-supply-chain-security/spec.md) |

Note on count: this change produces ten capability specs
that cover tasks 85-94. Task 95 (Wiki maintenance + ADR +
archive + `CURRENT.md`) is the
`implement-phase-6-agent-integration` close-out task and
does not require its own capability spec; its Wiki and
ADR outputs are documented in
[`context-impact.md`](context-impact.md) so the future
archive step can flip the plan row from `[ ]` to `[x]`.

The ten specs cover Phase 6 tasks 85-94 from
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md).
Tasks 85-95 remain `[ ]` in the plan change after this
change is archived; they will be flipped to `[x]` by the
future `implement-phase-6-agent-integration` change when
it lands.

Cross-phase task responsibility:

- the MCP server (task 85) is owned by Phase 6 and
  composes the Phase 5 `QueryOrchestratorPort` /
  `LocalLLMPort` / `TaskContextBuilderPort` /
  `CapabilityDiscoveryPort` and the Phase 4
  `MultiStageRetrievalPort` / `HybridRetrievalPort` /
  `ContextAssemblerPort`;
- the skill distribution plane (task 86) is owned by
  Phase 6 and exposes the canonical Agent Skill through
  MCP resources for runtime discovery;
- the canonical Agent Skill (task 87) is owned by Phase
  6 and ships under `distribution/skills/...` with
  progressive-disclosure references;
- the version-compatibility handshake (task 88) is owned
  by Phase 6 and is consumed by the MCP server, the
  skill distribution plane and every plugin packager;
- the Codex / ChatGPT plugin packager (task 89), the
  Claude Code plugin packager (task 90), the OpenCode
  plugin package (task 91) and the generic agent bundle
  (task 92) are owned by Phase 6 and emit per-vendor
  plugin bundles from the canonical sources;
- the agent adapter contract (task 93) is owned by
  Phase 6 and provides the `detect` / `install` /
  `configureMcp` / `installSkill` /
  `verifyCompatibility` / `healthCheck` / `uninstall` /
  `describe` port the future Phase 7 Feature / Plugin
  Registry composes;
- the plugin supply-chain security gate (task 94) is
  owned by Phase 6 and is the verification function
  every packager calls before emit.

Naming and adoption conventions (per
[`openspec/config.yaml`](../../config.yaml) and
[`openspec/README.md`](../../README.md)):

- active change IDs are undated semantic kebab-case
  (`prepare-phase-6-agent-integration`);
- delta folders under `specs/` use the future
  first-acceptance date at adoption; their current `2026-10-07-*` names are provisional;
- `openspec/CURRENT.md` is updated by the future
  `implement-phase-6-agent-integration` change when the
  ten Phase 6 specs are adopted, not by this change.

## Compatibility / migration impact

This change is a pure planning artifact. It adds:

- one new active change directory at
  `openspec/changes/prepare-phase-6-agent-integration/`;
- ten new spec deltas under
  `openspec/changes/prepare-phase-6-agent-integration/specs/2026-10-07-*/`;
- one new active change directory at
  `openspec/changes/implement-phase-6-agent-integration/`;
- ten mirrored spec deltas under
  `openspec/changes/implement-phase-6-agent-integration/specs/2026-10-07-*/`.

It does not:

- modify any accepted Phase 1 / Phase 2 / Phase 3 /
  Phase 4 / Phase 5 capability spec under
  `openspec/specs/`;
- modify `openspec/CURRENT.md`, the harness, the
  license inventory or the regression suite;
- introduce any source code, dependency or runtime
  configuration;
- rename any existing capability, port or adapter;
- alter the `plan-v0-8-platform-architecture` change
  (`tasks.md` still lists tasks 85-95 as `[ ]`);
- modify the pre-existing harness-side MCP server at
  `tools/mcp/project-context-mcp/` — that is a
  different deliverable owned by the harness scope.

Language and dependency decisions:

- the Python 3.11 platform source language decision
  recorded in
  [`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md)
  still holds. The MCP server itself is Python (the
  official MCP Python SDK is Apache-2.0; SPDX entry
  already present via the harness-side MCP package —
  the future `implement-phase-6-agent-integration`
  change confirms a shared or separate top-level entry
  in `distribution/licenses/dependency-inventory.json`
  before emitting the MCP server).
- the OpenCode plugin adapter MAY require a TypeScript
  / JavaScript runtime. That runtime is opt-in and
  ships only after each SPDX-tracked license inventory
  entry passes `LicenseGate`; no transitive runtime
  enters the default container.
- no change to the licence-governance defaults. Any new
  dependency must be SPDX-tracked and pass
  `LicenseGate` before it lands in
  `distribution/licenses/dependency-inventory.json`. The
  future `plugin-distribution-pipeline` ADR (if needed)
  carries the documented rationale for any new
  dependency the OpenCode plugin adapter requires.
- the Phase 1-5 invariants #1-#4 (canonical / runtime
  separation, Git as source of truth, bidirectional
  sync, deterministic round-trip) and the §17
  ANN-vs-knowledge-graph separation are NOT touched by
  Phase 6. The MCP server is a thin adapter; it MUST
  NOT introduce a new runtime store and MUST NOT alter
  the canonical / runtime boundary.

OpenSpec CLI conventions:

- the change folder uses lowercase kebab-case without a
  date prefix (`prepare-phase-6-agent-integration`)
  per [`openspec/config.yaml`](../../config.yaml);
- provisional delta dates must be reconciled to actual first Git acceptance;
  archives use the actual archive date and preserve accepted capability identity.
  Do not drop capability date prefixes or apply both mirrored ADDED sets.

- no production code, license inventory entry or
  harness command is touched.

## Related knowledge

- `kb://architecture.platform-overview` — Phase 1-5
  Wiki node; will be updated by the future
  `implement-phase-6-agent-integration` change to add
  the Phase 6 module map (`mcp/`,
  `adapters/agent_integration/`,
  `distribution/skills/`, `distribution/codex/`,
  `distribution/claude-code/`,
  `distribution/opencode/`,
  `distribution/generic-agent/`).
- `kb://architecture.system-overview` — cross-cutting
  view; will gain a Phase 6 module map row.
- `kb://glossary.platform` — Phase 1-5 platform
  vocabulary; the future change adds `McpServer`,
  `SkillDistributionPlane`, `DistributionManifest`,
  `SkillIndex`, `SkillVersionedUri`,
  `CanonicalAgentSkill`, `SkillMetadataContract`,
  `VersionCompatibilityHandshake`,
  `VersionCompatibilityError`,
  `AgentIntegrationAdapter`, `PluginPackager`,
  `PluginSupplyChainSecurityGate`.
- `kb://glossary.domain` — cross-links to the platform
  vocabulary for the new entries.
- `kb://project.implementation-roadmap` — links to
  Phase 6 entry.
- `kb://project.project-map` — Phase 6 module map
  placeholder.
- `kb://adr.platform-source-language` — Python 3.11
  holds; the MCP server is Python; the OpenCode plugin
  adapter MAY use TypeScript / JavaScript and stays
  under `pi_platform/adapters/agent_integration/`.
- `kb://adr.canonical-runtime-separation` — Phase 6
  specs respect invariants #1-#4 and the canonical /
  runtime boundary; the MCP server does not invent a
  new runtime store but composes the Phase 3 stack and
  the Phase 4 / Phase 5 surface.
- `kb://adr.license-governance-default` — every Phase
  6 dependency (MCP SDK, plugin runtime, plugin model
  weights) requires an SPDX-tracked inventory entry.
- `kb://modules.orchestrator`,
  `kb://modules.llm-port`,
  `kb://modules.task-context` — Phase 5 module maps
  that the Phase 6 MCP server composes.
- `kb://interfaces.capability-discovery` — Phase 5
  interface that the MCP `describe_capabilities` tool
  delegates to.
- `kb://interfaces.hybrid-retrieval`,
  `kb://interfaces.context-assembler` — Phase 4
  interface maps the MCP `project.search` and
  `project.retrieve_context` tools compose.
- future `kb://interfaces.mcp-tools`,
  `kb://interfaces.skill-distribution`,
  `kb://interfaces.plugin-distribution` — Wiki
  interface nodes the future implementation change
  authors.
- external:
  `project-intelligence-platform-architecture-v0.8.md`
  §5, §17, §33, §36, §37, §38, §39, §40, §41, §42,
  §43, §44, §45, §46, §47, §48, §49 — every cited
  section is authoritative for the Phase 6 capability
  contracts.