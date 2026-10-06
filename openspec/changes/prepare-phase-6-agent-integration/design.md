# Design — prepare-phase-6-agent-integration

The technical design lives in
[`openspec/changes/implement-phase-6-agent-integration/design.md`](../../implement-phase-6-agent-integration/design.md).
This file is a thin reference so the preparation change
carries its own design section.

## Phase 6 module map

- `pi_platform/mcp/` — new platform subpackage
  hosting the MCP server;
- `pi_platform/ports/agent_integration/` — new ports
  subpackage hosting the `AgentIntegrationAdapter`
  contract and the `VersionCompatibilityPolicy`
  value type;
- `pi_platform/core/agent_integration/` — new cores
  subpackage hosting the deterministic version-handshake
  core and the plugin-supply-chain gate core;
- `pi_platform/adapters/agent_integration/` — new
  default-adapter subpackage hosting the four
  per-vendor plugin packagers and the per-vendor
  adapter adapters;
- `pi_platform/cli/main.py` — new
  `mcp-serve`, `plugin-package`, `agent-integration`
  subcommands;
- `distribution/skills/project-intelligence/` — the
  canonical Agent Skill package;
- `distribution/{codex,claude-code,opencode,
  generic-agent}/` — the per-vendor plugin bundle
  outputs;
- `distribution/licenses/dependency-inventory.json`
  — every Phase 6 dependency lands here after each
  SPDX-tracked entry passes `LicenseGate`.

## Port surfaces (summary)

- `McpServer` — thin adapter; composes the Phase 5
  `QueryOrchestratorPort`, `LocalLLMPort`,
  `TaskContextBuilderPort`, `CapabilityDiscoveryPort`
  and the Phase 4 `MultiStageRetrievalPort`,
  `HybridRetrievalPort`, `ContextAssemblerPort`
  through the 17 §36 semantic tools plus
  `describe_capabilities`;
- `SkillDistributionPlane` — exposes the §38 URI
  namespace through MCP resources;
- `VersionCompatibilityPolicy` — exposes the 9 §39
  version dimensions and the handshake;
- `AgentIntegrationAdapter` — exposes the 8 §46
  operations: `detect`, `install`, `configureMcp`,
  `installSkill`, `verifyCompatibility`,
  `healthCheck`, `uninstall`, `describe`;
- `PluginPackager` — exposes the per-vendor packager
  contract (`codex`, `claude-code`, `opencode`,
  `generic-agent`);
- `PluginSupplyChainSecurityGate` — exposes the §48
  verification function the packagers call before
  emit.

## Default adapters (summary)

- `DefaultMcpServer` — FastMCP server using the
  official MCP Python SDK (Apache-2.0); default stdio
  transport;
- `DefaultSkillDistributionPlane` — exposes the URI
  namespace from the canonical skill and the
  distribution manifest;
- `DefaultVersionCompatibilityPolicy` — deterministic
  semver-range parser / comparator;
- `DefaultAgentIntegrationAdapter` — abstract base
  class with documented typed errors;
- `CodexPluginPackager`, `ClaudeCodePluginPackager`,
  `OpenCodePluginPackager`,
  `GenericAgentBundlePackager` — per-vendor packagers;
- `DefaultPluginSupplyChainSecurityGate` — verification
  function with the documented release controls.

## 9-version-dimension matrix

The §39 handshake tracks 9 dimensions:

| Dimension | Default | Source |
|---|---|---|
| `platformVersion` | `0.7.0` | Phase 1 platform runtime |
| `mcpApiVersion` | `1.3.0` | MCP server SDK release |
| `a2aAdapterVersion` | (Phase 10) | A2A adapter (always `0.0.0` until Phase 10) |
| `knowledgeSchemaVersion` | `0.7.0` | Phase 1 canonical schema |
| `okfProfileVersion` | `0.2` | OKF profile the platform accepts |
| `skillVersion` | `1.4.0` | The canonical Agent Skill version |
| `pluginDistributionSchemaVersion` | `1` | The distribution manifest schema version |
| `agentAdapterVersion` | `1.0.0` | The `AgentIntegrationAdapter` contract version |
| `runtimeIndexSchemaVersion` | (Phase 3) | The runtime index schema version |

## Per-packager shape

The packagers share a common shape:

```text
PluginPackager
├── canonical_sources (read-only)
│   ├── canonical Agent Skill under distribution/skills/
│   ├── MCP capability descriptor (Phase 5)
│   └── distribution manifest
├── packager_inputs
│   ├── vendor name (codex | claude-code | opencode | generic-agent)
│   ├── output root (defaults to distribution/<vendor>/)
│   └── compatibility fallback flag (per-vendor)
├── packager_outputs
│   ├── per-vendor manifest
│   ├── per-vendor MCP config
│   ├── bundled SKILL.md (byte-equal to canonical)
│   ├── optional assets / commands / agents / adapter
│   └── supply-chain gate verdict (recorded in provenance)
└── invariants
    ├── determinism (skill sha256 enforces byte-identity)
    ├── supply-chain gate (always runs before emit)
    ├── no vendor-specific business logic
    └── plugin distribution schema version embedded
```

## Per-vendor entry points

| Vendor | Entry point | Compatibility fallback |
|---|---|---|
| Codex | `dist/codex/plugin.json` | `dist/codex/.codex-plugin/plugin.json` |
| Claude Code | `dist/claude-code/.claude-plugin/plugin.json` | (none) |
| OpenCode | `dist/opencode/package.json` | (local-project-usable alternative) |
| Generic agent | `dist/generic-agent/AGENTS.example.md` + `dist/generic-agent/mcp/*.json` | (none) |

## Distribution manifest schema (project-intelligence://distribution/manifest)

```yaml
platformVersion: "0.7.0"
mcpApiVersion: "1.3.0"
knowledgeSchemaVersion: "0.7.0"
distributionSchemaVersion: "1"
skill:
  name: project-intelligence
  version: "1.4.0"
  sha256: "<hex>"
  mcpApiRange: ">=1.3.0 <2.0.0"
okf:
  supported:
    - "0.2"
agentAdapters:
  codex: "1.0.0"
  claude-code: "1.0.0"
  opencode: "1.0.0"
```

The manifest is deterministic; two consecutive reads
of `project-intelligence://distribution/manifest` MUST
return byte-identical JSON.

## Deterministic-build expectation

Every packager is deterministic. The skill content hash
(SHA-256) enforces byte-identity across two runs with
the same canonical sources. The supply-chain gate
rejects non-deterministic builds through the
`PluginBuildNotDeterministicError` typed error.

## Plugin-supply-chain gate checks

Every packager calls the gate before emit. The gate
runs the documented release controls:

- pinned version (semver, no `latest` / `*` / `main`);
- content hash (matches canonical SHA-256);
- license (SPDX-tracked and on the allow-list);
- SBOM (every transitive dependency declared);
- malware / secret scan (no shell-script auto-install,
  no embedded credentials);
- deterministic build (skill SHA-256 enforces
  byte-identity);
- signature support (optional signature verified when
  present);
- source provenance (canonical repository URL,
  commit hash, build identity);
- permissions (no over-broad `["*"]`);
- network requirements (no undisclosed destinations);
- absence of hidden auto-install;
- approval-controlled write / materialise tools.

The gate emits a typed error for every failure. The
packager records the verdict in the artifact's
provenance metadata.

## Architecture decisions

The Phase 6 implementation change records the
following trade-off matrix (per `architecture-design`):

### §39 version-handshake alternatives

| Alternative | Trade-off | Decision |
|---|---|---|
| Semver-range enforcement (PEP 440 / `node-semver`) | Most precise; covers pre-release tags, hyphen ranges | **Adopted.** Default range parser is the documented semver-range syntax. |
| Major-version-only policy | Simple; no patch-level compatibility | Rejected. Phase 6 needs patch-level compatibility for the canonical skill content hash. |
| Hash-pinned integrity + version-stamped range | Strongest integrity; minor version drift impossible | **Adopted.** Skill SHA-256 is bundled in every plugin manifest. |
| Signed-manifest | Strongest trust; requires key infrastructure | Deferred to Phase 8 (enterprise security boundary); Phase 6 records the gate supports signatures when present. |

### §48 plugin-supply-chain security trade-offs

| Alternative | Trade-off | Decision |
|---|---|---|
| Hash-pinned integrity (SHA-256) | Strong; reproducible | **Adopted.** Every bundled file has a documented SHA-256. |
| Signed-manifest | Strongest; requires key infrastructure | Deferred to Phase 8; gate supports signature verification when present. |
| Per-vendor licence review | High-friction; manual | Replaced with `LicenseGate` automated allow-list. |
| Hidden auto-install blocked | Strong; baseline | **Adopted.** Shell scripts that auto-install unrelated software are rejected. |
| Approval-gated materialise tools | Strong; user-controlled | **Adopted.** Skill declarations that enable write tools are rejected. |

## Phase 1-5 invariant impact

The MCP server is a thin adapter and MUST NOT introduce
a new runtime store. The MCP server composes the Phase 3
runtime store, sparse / dense / full-text indexes and
sharded graph through the Phase 4 / Phase 5 surface.
Invariants #1-#4 (canonical / runtime separation, Git
as source of truth, bidirectional sync, deterministic
round-trip) and the §17 ANN-vs-knowledge-graph
separation are NOT touched. The MCP server respects
the §33 retrieval-first escalation policy by routing
every tool through the Phase 5 orchestrator or the
Phase 4 retrieval surface.

## Risks and mitigations

See
[`openspec/changes/implement-phase-6-agent-integration/design.md#risks-and-mitigations`](../../implement-phase-6-agent-integration/design.md#risks-and-mitigations)
for the full risk matrix.