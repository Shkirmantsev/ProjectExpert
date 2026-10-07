# Tasks — implement-phase-6-agent-integration

This tasks file mirrors the Phase 6 tasks 85-95 from
the canonical
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md).
The implementation work executes the tasks defined by
the
[`prepare-phase-6-agent-integration/tasks.md`](../prepare-phase-6-agent-integration/tasks.md)
file; this file lists the tasks in execution order with
the concrete verification commands.

The ten Phase 6 capability specs under [`specs/`](specs)
are the authoritative behavioural contract.

## Phase 6 — Agent integration (implementation)

### 6.1 — MCP server (task 85)

- [ ] 85. Implement the MCP server per the
  [`mcp-server`](../prepare-phase-6-agent-integration/specs/2026-10-07-mcp-server/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_mcp_server -v`
    MUST report `OK`;
  - `python -m pi_platform.cli mcp-serve --transport
    stdio` MUST boot the MCP server with the
    documented 17 tools plus `describe_capabilities`;
  - write / materialise tools MUST require an
    `approval_id` and MUST NOT bypass the Phase 1
    `MaterialiseService` approval contract.

### 6.2 — Skill distribution plane (task 86)

- [ ] 86. Implement skill distribution resources per
  the
  [`skill-distribution-plane`](../prepare-phase-6-agent-integration/specs/2026-10-07-skill-distribution-plane/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_skill_plane -v`
    MUST report `OK`;
  - the manifest MUST carry the documented fields;
  - two consecutive reads of the manifest MUST return
    byte-identical JSON.

### 6.3 — Canonical Agent Skill (task 87)

- [ ] 87. Author the canonical Agent Skill per the
  [`agent-skill-canonical`](../prepare-phase-6-agent-integration/specs/2026-10-07-agent-skill-canonical/spec.md)
  capability spec.
  Verification:
  - the canonical `SKILL.md` MUST be ≤ 8 KB and MUST
    declare the documented YAML frontmatter;
  - the `references/` directory MUST contain the five
    documented files;
  - the canonical skill SHA-256 MUST be reflected in
    the distribution manifest and every plugin
    packager's manifest.

### 6.4 — Version compatibility handshake (task 88)

- [ ] 88. Implement the version-compatibility handshake
  per the
  [`version-compatibility-handshake`](../prepare-phase-6-agent-integration/specs/2026-10-07-version-compatibility-handshake/spec.md)
  capability spec.
  Verification:
  - `python -m unittest
    tests.test_version_compatibility -v` MUST report
    `OK`;
  - disjoint ranges MUST raise a typed
    `VersionIncompatibleError` with the documented
    payload;
  - two consecutive serialisations of
    `VersionCompatibilityPolicy` MUST be byte-identical.

### 6.5 — Codex plugin packager (task 89)

- [ ] 89. Implement the Codex / ChatGPT plugin
  packager per the
  [`codex-plugin-package`](../prepare-phase-6-agent-integration/specs/2026-10-07-codex-plugin-package/spec.md)
  capability spec.
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
    byte-identical artifacts.

### 6.6 — Claude Code plugin packager (task 90)

- [ ] 90. Implement the Claude Code plugin packager per
  the
  [`claude-code-plugin-package`](../prepare-phase-6-agent-integration/specs/2026-10-07-claude-code-plugin-package/spec.md)
  capability spec.
  Verification:
  - `python -m unittest
    tests.test_claude_code_plugin -v` MUST report
    `OK`;
  - the bundled `SKILL.md` MUST be byte-equal to the
    canonical `SKILL.md`;
  - the plugin slug MUST be `project-intelligence`;
  - the §48 supply-chain gate MUST run before emit.

### 6.7 — OpenCode plugin package (task 91)

- [ ] 91. Implement the OpenCode plugin package per
  the
  [`opencode-plugin-package`](../prepare-phase-6-agent-integration/specs/2026-10-07-opencode-plugin-package/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_opencode_plugin
    -v` MUST report `OK`;
  - the bundled `SKILL.md` MUST be byte-equal to the
    canonical `SKILL.md`;
  - the `package.json` MUST be publishable as a
    versioned npm package OR usable as a local
    project plugin.

### 6.8 — Generic agent bundle (task 92)

- [ ] 92. Implement the generic agent bundle per the
  [`generic-agent-bundle`](../prepare-phase-6-agent-integration/specs/2026-10-07-generic-agent-bundle/spec.md)
  capability spec.
  Verification:
  - `python -m unittest
    tests.test_generic_agent_bundle -v` MUST report
    `OK`;
  - the bundled skill MUST be byte-equal to the
    canonical skill;
  - the `mcp/` directory MUST contain both
    `stdio-example.json` and `http-example.json`.

### 6.9 — Agent adapter contract (task 93)

- [ ] 93. Implement the agent adapter contract per the
  [`agent-adapter-contract`](../prepare-phase-6-agent-integration/specs/2026-10-07-agent-adapter-contract/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_agent_adapter -v`
    MUST report `OK`;
  - the contract MUST expose the documented 8
    operations;
  - adapters MUST NOT own retrieval / business rules.

### 6.10 — Plugin supply-chain security gate (task 94)

- [ ] 94. Implement the plugin supply-chain security
  gate per the
  [`plugin-supply-chain-security`](../prepare-phase-6-agent-integration/specs/2026-10-07-plugin-supply-chain-security/spec.md)
  capability spec.
  Verification:
  - `python -m unittest
    tests.test_supply_chain_gate -v` MUST report `OK`;
  - the gate MUST reject every documented violation
    through a typed error;
  - the gate MUST be invoked by every packager
    before emit.

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
  archive the prep change under
  `archive/<actual-archive-date>-prepare-phase-6-agent-integration/`,
  archive this implementation change under
  `archive/<actual-archive-date>-implement-phase-6-agent-integration/`,
  update `openspec/CURRENT.md`, flip
  `plan-v0-8-platform-architecture/tasks.md` rows
  85-95 to `[x]`.

Verification for the slice (tasks 94-95):

- `python harness.py wiki-validate` MUST pass;
- `python harness.py openspec-check` MUST pass;
- `python harness.py check` MUST pass;
- `openspec validate --all --strict` MUST return no
  failures across Phase 1-6 deltas;
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
