# Tasks — prepare-phase-6-agent-integration

This tasks file mirrors the Phase 6 tasks 85-95 from
the canonical
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md).
The tasks below are the future implementation work;
they will be executed by the future
`implement-phase-6-agent-integration` change. This
change ships zero production code.

The ten Phase 6 capability specs under
[`specs/`](specs) are the authoritative behavioural
contract for the implementation work. The future
change implements and verifies these proposed deltas before adoption. Tasks
85-95 remain unchecked until their implementation and close-out are verified;
preparation completion alone does not adopt or implement these requirements.

Verification commands referenced below:

- `python -m unittest tests.<module> -v` — focused
  regression tests;
- `openspec validate
  implement-phase-6-agent-integration --type change
  --strict` (future change),
  `openspec validate --all --strict` (canonical harness
  check);
- `python harness.py check` — configuration/session, Wiki, OpenSpec, tests
  and artifact manifest gate; run license-gate separately;
- `python harness.py wiki-validate` — Wiki Markdown
  validation;
- `python scripts/artifact_manifest.py verify` —
  artifact manifest gate;
- `python -m pi_platform.cli license-gate` — license
  inventory gate.

## Phase 6 — Agent integration (preparation only)

### 6.1 — MCP server (task 85)

- [ ] 85. Implement the MCP server
  (`pi_platform.mcp.server.McpServer`) exposing the semantic
  tools from §36 (`project.search`,
  `project.retrieve_context`, `project.get_entity`,
  `project.get_component`, `project.get_requirement`,
  `project.get_spec`, `project.get_architecture`,
  `project.get_dependency`,
  `project.find_implementation`,
  `project.trace_requirement`, `project.find_references`,
  `project.get_project_version`,
  `project.get_conflicts`,
  `project.get_stale_knowledge`,
  `project.build_task_context`,
  `project.materialize_knowledge`,
  `project.refresh_sources`) and
  `describe_capabilities`.
  → `pi_platform/mcp/server.py` (new),
  `pi_platform/mcp/tools.py` (new).
  Verification:
  - `python -m unittest tests.test_mcp_server
    -v` MUST report `OK`;
  - `python -m pi_platform.cli mcp-serve --transport
    stdio` MUST boot the MCP server with the
    documented 17 tools plus `describe_capabilities`;
  - the MCP server MUST compose the Phase 5
    `QueryOrchestratorPort` and the Phase 4
    `MultiStageRetrievalPort` per the
    `mcp-server` capability spec;
  - write / materialise tools MUST require an
    `approval_id` and MUST NOT bypass the Phase 1
    `MaterialiseService` approval contract.

### 6.2 — Skill distribution plane (task 86)

- [ ] 86. Implement skill distribution resources
  (`project-intelligence://distribution/manifest`,
  `project-intelligence://skills/index`,
  `project-intelligence://skills/<name>/<version>/
  SKILL.md` and referenced files).
  → `pi_platform/mcp/skill_plane.py` (new).
  Verification:
  - `python -m unittest tests.test_skill_plane
    -v` MUST report `OK`;
  - the manifest MUST carry the documented fields
    (`platformVersion`, `mcpApiVersion`,
    `knowledgeSchemaVersion`,
    `distributionSchemaVersion`, `skill`,
    `okf`, `agentAdapters`);
  - two consecutive reads of
    `project-intelligence://distribution/manifest`
    MUST return byte-identical JSON.

### 6.3 — Canonical Agent Skill (task 87)

- [ ] 87. Author the canonical Agent Skill at
  `distribution/skills/project-intelligence/SKILL.md`
  per §37 with progressive disclosure (concise main
  file + references for MCP tools, retrieval policy,
  versioning, OKF profile, security).
  → `distribution/skills/project-intelligence/
  SKILL.md` (new),
  `distribution/skills/project-intelligence/
  references/{MCP-TOOLS,RETRIEVAL-POLICY,VERSIONING,
  OKF-PROFILE,SECURITY}.md` (new).
  Verification:
  - the canonical `SKILL.md` MUST be ≤ 8 KB and MUST
    declare the documented YAML frontmatter keys
    (`name`, `description`, `license`,
    `compatibility`, `metadata.{author, version,
    mcp-api, knowledge-schema, okf-profile,
    distribution-schema}`);
  - the `references/` directory MUST contain the five
    documented files;
  - the canonical skill SHA-256 MUST be reflected in
    the distribution manifest and every plugin
    packager's manifest.

### 6.4 — Version compatibility handshake (task 88)

- [ ] 88. Implement the version-compatibility handshake
  (§39) for MCP API, knowledge schema, OKF profile,
  agent adapter, plugin-distribution schema.
  → `pi_platform/ports/agent_integration/
  version_compatibility.py` (new),
  `pi_platform/core/agent_integration/
  version_compatibility.py` (new).
  Verification:
  - `python -m unittest
    tests.test_version_compatibility -v` MUST report
    `OK`;
  - the handshake MUST compare semver ranges
    deterministically without an LLM;
  - disjoint ranges MUST raise a typed
    `VersionIncompatibleError` with the documented
    payload;
  - two consecutive serialisations of
    `VersionCompatibilityPolicy` MUST be byte-identical.

### 6.5 — Codex plugin packager (task 89)

- [ ] 89. Implement the Codex / ChatGPT plugin
  packager that emits `dist/codex/plugin.json`,
  `dist/codex/mcp.json`, the bundled skill and
  assets, and the `.codex-plugin/plugin.json`
  compatibility fallback. Add a smoke test.
  → `pi_platform/adapters/agent_integration/
  packagers/codex.py` (new).
  Verification:
  - `python -m unittest tests.test_codex_plugin -v`
    MUST report `OK`;
  - the bundled `SKILL.md` MUST be byte-equal to the
    canonical `SKILL.md`;
  - the `plugin.json` MUST carry the documented
    fields and the skill `sha256`;
  - the `.codex-plugin/plugin.json` compatibility
    fallback MUST be present when the selected legacy client profile requires it;
  - two consecutive packager runs MUST produce
    byte-identical artifacts;
  - the §48 supply-chain gate MUST run before emit
    and record its verdict in the provenance.

### 6.6 — Claude Code plugin packager (task 90)

- [ ] 90. Implement the Claude Code plugin packager
  emitting `dist/claude-code/.claude-plugin/
  plugin.json`, `dist/claude-code/.mcp.json`, skill,
  optional commands / agents.
  → `pi_platform/adapters/agent_integration/
  packagers/claude_code.py` (new).
  Verification:
  - `python -m unittest
    tests.test_claude_code_plugin -v` MUST report
    `OK`;
  - the bundled `SKILL.md` MUST be byte-equal to the
    canonical `SKILL.md`;
  - the plugin slug MUST be `project-intelligence`
    and MUST be treated as stable after public
    release;
  - the §48 supply-chain gate MUST run before emit.

### 6.7 — OpenCode plugin package (task 91)

- [ ] 91. Implement the OpenCode plugin package
  emitting `dist/opencode/package.json`,
  `dist/opencode/plugin/*.ts`, skill,
  `config/opencode.example.jsonc`.
  → `pi_platform/adapters/agent_integration/
  packagers/opencode.py` (new).
  Verification:
  - `python -m unittest tests.test_opencode_plugin
    -v` MUST report `OK`;
  - the bundled `SKILL.md` MUST be byte-equal to the
    canonical `SKILL.md`;
  - the `package.json` MUST be publishable as a
    versioned npm package OR usable as a local
    project plugin;
  - the §48 supply-chain gate MUST run before emit.

### 6.8 — Generic agent bundle (task 92)

- [ ] 92. Implement the generic agent bundle
  (`dist/generic-agent/skills/`, `mcp/`,
  `AGENTS.example.md`, `README.md`).
  → `pi_platform/adapters/agent_integration/
  packagers/generic_agent.py` (new).
  Verification:
  - `python -m unittest
    tests.test_generic_agent_bundle -v` MUST report
    `OK`;
  - the bundled skill MUST be byte-equal to the
    canonical skill;
  - the `mcp/` directory MUST contain both
    `stdio-example.json` and `http-example.json`;
  - `AGENTS.example.md` MUST cover the documented
    sections;
  - the §48 supply-chain gate MUST run before emit.

### 6.9 — Agent adapter contract (task 93)

- [ ] 93. Implement the agent adapter contract from
  §46 (`AgentIntegrationAdapter` with `detect`,
  `install`, `configureMcp`, `installSkill`,
  `verifyCompatibility`, `healthCheck`,
  `uninstall`, `describe`).
  → `pi_platform/ports/agent_integration/
  adapter.py` (new),
  `pi_platform/core/agent_integration/
  adapter.py` (new).
  Verification:
  - `python -m unittest tests.test_agent_adapter
    -v` MUST report `OK`;
  - the contract MUST expose the documented 8
    operations;
  - adapters MUST NOT own retrieval / business rules;
  - the typed error vocabulary MUST cover the
    documented errors;
  - the `verifyCompatibility()` operation MUST
    delegate to the §39 handshake.

### 6.10 — Plugin supply-chain security gate (task 94)

- [ ] 94. Implement the plugin supply-chain security
  gate (pinned version, content hash, SBOM,
  license / scan, source provenance, signature
  support, no hidden auto-install, approval-gated
  materialise tools).
  → `pi_platform/core/agent_integration/
  supply_chain_gate.py` (new).
  Verification:
  - `python -m unittest
    tests.test_supply_chain_gate -v` MUST report
    `OK`;
  - the gate MUST reject every documented violation
    through a typed error;
  - the gate MUST be invoked by every packager
    before emit;
  - the gate's verdict MUST be recorded in the
    artifact's provenance metadata.

### 6.11 — Wiki maintenance and archive (task 95)

- [ ] 95. Update Wiki (new `interfaces/mcp-tools`,
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
  `adr/0013-plugin-supply-chain-security`),
  archive this change under
  `archive/<actual-archive-date>-prepare-phase-6-agent-integration/`,
  archive the implementation change under
  `archive/<actual-archive-date>-implement-phase-6-agent-integration/`,
  update `openspec/CURRENT.md`, flip
  `plan-v0-8-platform-architecture/tasks.md` rows
  85-95 to `[x]`.

Verification for the slice (tasks 94-95):

- `python harness.py wiki-validate` MUST pass;
- `python harness.py openspec-check` MUST pass;
- `python harness.py check` MUST pass;
- `openspec validate
  implement-phase-6-agent-integration --type change
  --strict` MUST return `valid`;
- the Phase 1-5 regression suites MUST remain green.

## Out-of-scope tasks (this change)

- Phase 7+: control plane, security enterprise
  boundary, distribution one-click launcher, A2A
  (tasks 96-123).

## Readiness, ordering and integration evidence

Before task 85 enables writes, resolve the approval-policy prerequisite in the
[design](../prepare-phase-6-agent-integration/design.md#prerequisites-and-observed-gaps).
Do not infer readiness from the Phase 1-5 test count. Track the prerequisite
fix separately and checkpoint its evidence; it is not implemented by preparation.

Build dependency order: validated schemas/version policy and trusted write
boundary (88, 93, 94), canonical skill (87), MCP tools/resources (85, 86),
then generated vendor packages (89-92), then close-out (95). Contract stubs
can be drafted earlier; release packages require the completed gate.

Phase 6 integration tests must exercise an actual SDK client session over stdio
and Streamable HTTP (startup, initialize, tools/list, resources/list/templates,
tools/call, resources/read and shutdown). A blocking `mcp-serve` invocation
alone is not a smoke test. Test filtered version-correct retrieval and exact
lookup, bounded task context from a goal, immutable pinned resources, malformed
and incompatible versions, absent optional A2A/LLM, denied/forged/expired/wrong
scope approvals, refresh approval, stale/conflict metadata, branch reconciliation,
and resource traversal/symlink rejection. Use bounded timeouts and clean up children.

For each vendor, validate with its supported official schema/client version,
record that version, and exercise install/configure/health/uninstall in an
isolated temporary project. Preserve pre-existing user configuration on uninstall.
If a client is unavailable, report NOT RUN and leave its release verification
pending; JSON existence does not prove installability. Include deterministic
skill activation/tool-selection/retrieval-first fixtures and record context
budget, latency and setup results per architecture §49; live agent evals remain
optional and must be identified separately from deterministic tests.

Generate all four bundles from one canonical release input set. Compare skill
package hash, version, MCP range, license, server identity and required
capabilities across vendors (§45); fail the shared build on any disagreement.
Compare every output path/byte across two isolated builds, including references,
configs and provenance; exclude self-referential digest fields through a
documented canonical inventory rule. Stage builds locally and publish outputs
only after the supply-chain gate passes.

At task 95 reconcile new capability dates to actual first Git acceptance,
promote only the implementation deltas, archive preparation without duplicate
application, use actual archive dates, update CURRENT and Wiki/ADRs, and mark
the canonical plan rows complete only after all implementation gates pass.
Preparation/review session completion is independent of implementation adoption.
