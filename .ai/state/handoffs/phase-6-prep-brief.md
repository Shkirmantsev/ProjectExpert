# Phase 6 (Agent Integration) — Preparation brief

This is a self-contained brief for the Phase 6 **preparation** iteration. The Phase 1-5 implementation is complete and archived on `feature/generate-init-project`. Your job is to author the Phase 6 capability specs and change artifacts — **zero production code** — so a future `implement-phase-6-agent-integration` change can consume the contracts.

## Current workflow / state (actual as of this brief)

### Repository state

- **Working tree**: not clean. One uncommitted modification: `.ai/state/CURRENT.md` (modified by the Phase 5 session checkpoint). Run `git status` to confirm. **Commit or revert the drift before starting.**
- **Branch**: `feature/generate-init-project`, 6 commits ahead of `origin/feature/generate-init-project` (unpushed). Do NOT push; the brief and project rules require local-only commits.
- **HEAD**: `520fd80 feat(orchestration): ship Phase 5 orchestration subsystem (tasks 79-84)`.

### OpenSpec state

- `openspec/CURRENT.md` lists 30 accepted product capabilities (5 Phase 1, 9 Phase 2, 9 Phase 3, 8 Phase 4, 5 Phase 5). The `Project product capabilities` table is the central inventory.
- `openspec/changes/` currently has only `archive/` and `plan-v0-8-platform-architecture/` (the plan change is active and used as the source of task ordering).
- All 9 prior implementation / preparation changes are archived under `openspec/changes/archive/2026-10-{04,05}-{prepare,implement}-{phase-N}/`.
- `openspec/changes/plan-v0-8-platform-architecture/tasks.md` rows 1-84 are `[x]`; rows 85-95 (Phase 6) and 96-123 (Phase 7-10) are `[ ]`.

### Session state

- Active session: `implement-phase-5-orchestration` (status: `complete`, task: `implement-phase-5-orchestration`).
- Handoff: `.ai/state/handoffs/implement-phase-5-orchestration.json`.
- All Phase 1-5 verification gates passed: harness.py check, openspec validate (`43 passed 0 failed`), artifact-manifest (`PASS 638 files`), license-gate passed, 235 unit tests pass.
- Use `python3 scripts/session_state.py start --id prepare-phase-6-agent-integration --replace-current ...` to start the new session. The `--replace-current` is allowed because the previous session is `complete` and you are explicitly continuing with the next phase.

### LLM Wiki state (`.ai/wiki/`)

- 47 documents. 5 ADRs (0006-0010) cover phases 2-5. **No ADR for Phase 6 yet**.
- 6 framework ADRs (0001-0005).
- 4 Phase 4 module pages (`modules/retrieval`, `modules/embeddings`, `modules/context-assembler`).
- 4 Phase 5 module pages (`modules/orchestrator`, `modules/llm-port`, `modules/task-context`).
- 17 interface pages (chunker, dense-index, enrichment, freshness, full-text-index, git, graph-expansion, hybrid-retrieval, licensing, provenance, reranker, runtime-store, source-adapters, sparse-index, sync, canonical, capability-discovery).
- 1 glossary (platform), 2 architecture pages (platform-overview, system-overview), 4 project pages (harness-command-lifecycle, harness-framework-adoption, implementation-roadmap, project-map, task-handoff), 1 domain glossary.
- The Wiki state accurately reflects the Phase 1-5 surface. The Phase 5 close-out tasks 78 and 84 already added Phase 4 / Phase 5 module and interface pages.

### Existing `tools/mcp/project-context-mcp/` (NOT Phase 6 work)

There is a pre-existing MCP server at `tools/mcp/project-context-mcp/` (Python, `mcp==1.30.0`, version 4.0.0). This is the **harness-side** MCP server (it exposes `kb_search`, `kb_get`, `kb_neighbors`, `code_symbol`, `spec_context`, `jar_search`, `jar_api`, `kb_validate`, `kb_refresh` for the development harness). It is **not** the platform's `platform.mcp.McpServer` (Phase 6 task 85). The platform's MCP server is a separate deliverable; do not modify the harness-side server.

### Existing `distribution/` state

- `distribution/skills/.gitkeep` exists but `distribution/skills/project-intelligence/SKILL.md` is **not yet authored** (task 87).
- `distribution/{codex,claude-code,opencode,generic-agent}/.gitkeep` exist but no plugin bundle content is shipped yet (tasks 89-92).
- `distribution/licenses/dependency-inventory.json` is populated (Phase 1-5 work added `sentence-transformers`, `cross-encoder-ms-marco-MiniLM-L-6-v2`, `paraphrase-multilingual-MiniLM-L12-v2`).
- `distribution/sbom/` has the Phase 1 baseline SBOM.

### Known issues / things to fix before Phase 6 implementation

These are the items the **preparation** iteration should NOT change but should **document** in the prep change's `context-impact.md` so the future implementation iteration knows:

1. **MCP server scope** — task 85 must add a `pi_platform/mcp/` package. None exists today. The MCP server depends on the Phase 5 `QueryOrchestratorPort` / `CapabilityDiscoveryPort` / `LocalLLMPort` and on the Phase 4 `MultiStageRetrievalPort` / `HybridRetrievalPort` / `ContextAssemblerPort`. Use the **MCP Python SDK** (`mcp==1.30.0`, Apache-2.0, already in the license inventory via the harness-side MCP package — confirm a separate top-level entry or share the entry).
2. **Skill SKILL.md is missing** — `distribution/skills/project-intelligence/SKILL.md` must be authored against §37, including the progressive-disclosure reference files (`references/MCP-TOOLS.md`, `references/RETRIEVAL-POLICY.md`, `references/VERSIONING.md`, `references/OKF-PROFILE.md`, `references/SECURITY.md`).
3. **Version handshake** — task 88 needs a `version_compatibility.py` core that compares `mcpApiVersion`, `knowledgeSchemaVersion`, `okfProfileVersion`, `agentAdapterVersion`, `pluginDistributionSchemaVersion` against semver ranges. The platform currently has `DEFAULT_MCP_API_VERSION = "1.3.0"`, `DEFAULT_KNOWLEDGE_SCHEMA_VERSION = "0.7.0"`, `DEFAULT_OKF_VERSIONS = ("0.2",)` already exported from `pi_platform.core.orchestration.capability_discovery`.
4. **Plugin packagers** — tasks 89-92 require a `distribution/packager.py` core plus per-target packagers that emit vendor bundles from the canonical skill + MCP + capability manifest. The packagers should be deterministic (skill content hash) so two runs produce the same artifacts.
5. **Agent adapter contract** — task 93 requires an `AgentIntegrationAdapter` port with `detect`, `install`, `configureMcp`, `installSkill`, `verifyCompatibility`, `healthCheck`, `uninstall`, `describe`. Adapters must not own retrieval / business rules (per the §46 invariant).
6. **Plugin supply-chain security** — task 94 is a security gate, not a new dependency. Implement as a verification function the packagers call before emit: pinned version, content hash, license, source provenance, no hidden auto-install, approval-gated materialise tools.
7. **MCP tool naming** — §36 lists 17 semantic tools + `describe_capabilities`. The list is exhaustive. Any new tool must be a documented extension.

## Authoritative source of truth

@project-intelligence-platform-architecture-v0.8.md — read it end-to-end. Specifically:

- §36 MCP Integration (17 semantic tools + `describe_capabilities`)
- §37 Versioned Agent Skill Distributed with the MCP Server (`SKILL.md` schema, references, behaviour)
- §38 Skill Distribution Plane (`project-intelligence://distribution/manifest`, `project-intelligence://skills/index`, `project-intelligence://skills/<name>/<version>/...`)
- §39 Protocol and Artifact Version Compatibility (the 9 tracked version dimensions, semver, handshake)
- §40 Agent Integration Packaging Layer (Ports-and-Adapters boundary)
- §41 Codex / ChatGPT Plugin Distribution Profile
- §42 Claude Code Plugin Distribution Profile
- §43 OpenCode Plugin Distribution Profile
- §44 Generic Agent Integration Profile
- §45 Plugin Generation Pipeline
- §46 Agent Adapter Contract
- §47 Capability Discovery (already accepted via Phase 5)
- §48 Security and Trust for Skills and Plugins
- §49 Integration Quality Gates and Evals (regression suites for MCP, skill, version, security, plugin)
- §50 A2A Integration (do NOT include in Phase 6; deferred to Phase 10)
- §51 External Coding Agents (do NOT include in Phase 6)
- §5.1-§5.5 License and Dependency Governance (especially §5.4 Model Licenses Are Separate and §5.5 Automated License Gate — every new dependency and every bundled skill model needs SPDX tracking)
- Invariants #1-#4 and the §17 ANN-vs-knowledge-graph separation (carry-over from Phase 1-3; Phase 6 must not violate)

## Hard prerequisites (verify at intake)

- Working tree clean, on `feature/generate-init-project`. (Drift: `.ai/state/CURRENT.md` modified. Commit the Phase 5 handoff state OR revert before starting the prep iteration.)
- Phase 5 archives present:
  `openspec/changes/archive/2026-10-05-implement-phase-5-orchestration/`
  AND `openspec/changes/archive/2026-10-05-prepare-phase-5-orchestration/`
- Phase 6 prep archive present (you must create this first):
  `openspec/changes/archive/2026-10-05-prepare-phase-6-agent-integration/`
  (today's date is 2026-10-05; follow the Phase 4 / 5 convention)
- The ten Phase 6 spec deltas authored (one per task 85-94):
  - `mcp-server` (§36, §47)
  - `skill-distribution-plane` (§38, §37)
  - `agent-skill-canonical` (§37, §39)
  - `version-compatibility-handshake` (§39, §47)
  - `codex-plugin-package` (§41, §45)
  - `claude-code-plugin-package` (§42, §45)
  - `opencode-plugin-package` (§43, §45)
  - `generic-agent-bundle` (§44, §45)
  - `agent-adapter-contract` (§46, §40)
  - `plugin-supply-chain-security` (§48, §45)
  - `phase-6-wiki-archive` (task 95 — close-out, no own spec delta; the close-out task flips plan rows 85-95 to `[x]` and updates `openspec/CURRENT.md` after the implementation change adopts the ten capability deltas)

  Decision: 10 capability deltas + 1 close-out task. The 10 capabilities cover tasks 85-94; task 95 ships the Wiki + ADR + archive + CURRENT.md. This matches the Phase 4 / 5 ratio.
- `python3 harness.py check` returns the harness core gate (the OpenSpec CLI validation FAIL is the documented pre-existing quirk)
- `PATH="$(pwd)/tmp/local/bin:$PATH" openspec validate --all --strict` returns `43 passed, 0 failed` or higher
- `python3 scripts/artifact_manifest.py verify` returns `Artifact manifest: PASS`
- `python3` on `PATH`; the OpenSpec CLI symlink at `tmp/local/bin/openspec` resolves to v1.4.0+

If any precondition is false, STOP and report the blocker before doing any implementation work.

## Phase 6 task list (tasks 85-95)

| #  | Task | Capability | Architecture |
|----|------|------------|--------------|
| 85 | MCP server exposing 17 semantic tools + `describe_capabilities` | `mcp-server` | §36 §47 |
| 86 | Skill distribution resources (manifest, index, versioned skill URI) | `skill-distribution-plane` | §38 §37 |
| 87 | Canonical Agent Skill at `distribution/skills/project-intelligence/SKILL.md` + references | `agent-skill-canonical` | §37 §39 |
| 88 | Version-compatibility handshake (9 version dimensions) | `version-compatibility-handshake` | §39 §47 |
| 89 | Codex / ChatGPT plugin packager + smoke test | `codex-plugin-package` | §41 §45 |
| 90 | Claude Code plugin packager | `claude-code-plugin-package` | §42 §45 |
| 91 | OpenCode plugin package | `opencode-plugin-package` | §43 §45 |
| 92 | Generic agent bundle | `generic-agent-bundle` | §44 §45 |
| 93 | Agent adapter contract (`AgentIntegrationAdapter` with 8 ops) | `agent-adapter-contract` | §46 §40 |
| 94 | Plugin supply-chain security gate | `plugin-supply-chain-security` | §48 §45 |
| 95 | Wiki maintenance + ADR (if needed) + archive + CURRENT.md | `phase-6-wiki-archive` (close-out, no spec delta) | §49 |

Naming and adoption conventions follow `openspec/config.yaml` and `openspec/README.md`:

- active change IDs: undated kebab-case `prepare-phase-6-agent-integration` and `implement-phase-6-agent-integration`
- delta folders under `specs/` use the future first-acceptance date `2026-10-05-<capability>` (matches Phase 4 / 5 convention; same date used across the 10 capability deltas)
- `openspec/CURRENT.md` is updated by THIS implementation change when the ten Phase 6 specs are adopted, not by the prep change
- The "phase-6-wiki-archive" task is a close-out task; it does not require its own capability spec. The prep change's `tasks.md` documents it inline; the implementation change flips the plan rows.

## Skill loadout

Load these skills at intake and follow their contracts throughout:

- `skill-router` — at intake. Run `python3 scripts/skill_router.py --profile balanced`.
- `openspec-change` — for adopting the prep change, writing the implementation proposal/design/tasks/context-impact. CRITICAL: 10 spec deltas is more than Phase 4 (8) or Phase 5 (5); the strict validator must pass for every delta. Watch for the "MUST" / "SHALL" requirement check and the "Scenario" block requirement.
- `lean-build` — Phase 6 is overbuilding-prone. Defer every vendor-specific choice to a runtime config. The plugin packagers must be deterministic; the skill distribution plane is a URL namespace, not a back-end database.
- `architecture-design` — REQUIRED for §39 version-handshake design and §48 plugin-supply-chain-security gate. Record the trade-off matrix in `design.md`. Compare semver-range enforcement vs. major-version-only policy; compare hash-pinned integrity vs. signed-manifest.
- `test-driven-development` — for designing the §89 Codex-plugin smoke test, the §95 MCP tool-selection tests, and the §95 version-mismatch tests. TDD-first; the test code is the primary deliverable.
- `verification` and `verification-before-completion` — before claiming any task done and before the final archive.
- `safe-refactor` — Phase 6 work touches the Phase 4 / Phase 5 surface (the MCP server composes the Phase 5 `QueryOrchestrator` and the Phase 4 `HybridRetrieval` / `ContextAssembler`); the Phase 1-5 regression suite MUST stay green. The Phase 1-5 tests are 235 tests.
- `llm-wiki-maintenance` for the Wiki edits task 95 ships.
- `code-reviewer` and `requesting-code-review` before final close-out.
- `systematic-debugging` / `investigate-first` if any verification check fails.

## Configured agents — when to dispatch via the `task` tool

The repository is wired with multi-agent tools. When the work clearly benefits from parallelizable, context-isolated, or fresh-perspective subtasks, DISPATCH via the `task` tool rather than doing it inline:

- **`explore` subagent** — for Wikipedia / domain-knowledge mini-research (e.g. "compare Codex `.codex-plugin/plugin.json` vs `plugin.json` for backward-compat shimming", "investigate the MCP Python SDK FastMCP server decorator contract for typed tool definitions"). Use the explicit source-list constraint.
- **`mimo-flash` subagent** — for per-capability spec delta authoring (one of the 10 deltas). Pass the §36-§48 reference and the Phase 5 spec deltas as the source-of-truth contract. Only re-author if the strict validator surfaces issues.
- **`mimo-pro` subagent** — for architecture review (e.g. §39 version-handshake alternatives, §48 plugin-supply-chain security trade-offs, §45 plugin-generation pipeline, §46 agent-adapter contract).
- **`deepseek-verify` subagent** — for independent verification (rerun OpenSpec strict validator across all 10 deltas, rerun wiki-validate, rerun harness-check in a fresh working copy, rerun Phase 1-5 regression suite).

Default profile from `python3 scripts/skill_router.py --profile balanced` already lists the four skills in `required_skills[]`; follow it. The prompt does NOT auto-dispatch — verify the chosen agent exists and is reachable before dispatching.

## What to author (PREPARATION ONLY — zero production code)

The prep change produces:

1. **Active change directory** `openspec/changes/prepare-phase-6-agent-integration/`
2. **Ten spec deltas** under `openspec/changes/prepare-phase-6-agent-integration/specs/2026-10-05-*/`:
   - `mcp-server/spec.md` (covers §36 tool surface; lists all 17 tools with `query` / `path_param` / `result` shape; mandates `describe_capabilities`; mandates no LLM required for capability read)
   - `skill-distribution-plane/spec.md` (covers §38 URI namespace `project-intelligence://distribution/manifest`, `project-intelligence://skills/index`, `project-intelligence://skills/<name>/<version>/SKILL.md`; mandates manifest schema: `platformVersion`, `mcpApiVersion`, `knowledgeSchemaVersion`, `distributionSchemaVersion`, `skill.{name, version, sha256, mcpApiRange}`, `okf.supported`, `agentAdapters.{codex,claude-code,opencode}`)
   - `agent-skill-canonical/spec.md` (covers §37 `SKILL.md` schema: `name`, `description`, `license`, optional `compatibility`, version + protocol metadata; mandates the 10-step behaviour contract; mandates `references/` for progressive disclosure: `MCP-TOOLS.md`, `RETRIEVAL-POLICY.md`, `VERSIONING.md`, `OKF-PROFILE.md`, `SECURITY.md`; mandates the "when not to use a tool" / "stale / conflict" / "version incompatibility" / "bypass security policy" / "read vs write" guidance)
   - `version-compatibility-handshake/spec.md` (covers §39 9 version dimensions: `platformVersion`, `mcpApiVersion`, `a2aAdapterVersion`, `knowledgeSchemaVersion`, `okfProfileVersion`, `skillVersion`, `pluginDistributionSchemaVersion`, `agentAdapterVersion`, `runtimeIndexSchemaVersion`; mandates semver ranges; mandates the `compatible? → continue / fail clearly → offer upgrade` decision contract)
   - `codex-plugin-package/spec.md` (covers §41: `dist/codex/{plugin.json, mcp.json, skills/, assets/}`; mandates compatibility fallback `.codex-plugin/plugin.json`; mandates generated-not-maintained; mandates skill content hash in plugin manifest)
   - `claude-code-plugin-package/spec.md` (covers §42: `dist/claude-code/{.claude-plugin/plugin.json, .mcp.json, skills/, optional commands/, agents/, README.md}`; mandates marketplace-ready metadata; mandates stable plugin slug after release)
   - `opencode-plugin-package/spec.md` (covers §43: `dist/opencode/{package.json, plugin/*.ts, skill/, config/opencode.example.jsonc, README.md}`; mandates npm-publishable OR local-project-usable; mandates TypeScript / JavaScript plugin adapter)
   - `generic-agent-bundle/spec.md` (covers §44: `dist/generic-agent/{skills/, mcp/{stdio-example.json, http-example.json}, AGENTS.example.md, README.md}`; mandates plain Markdown / MCP / Agent Skills / A2A compatibility)
   - `agent-adapter-contract/spec.md` (covers §46: 8 operations `detect`, `install`, `configureMcp`, `installSkill`, `verifyCompatibility`, `healthCheck`, `uninstall`, `describe`; mandates adapters must not own retrieval / business rules; mandates plug-in replaceable installers)
   - `plugin-supply-chain-security/spec.md` (covers §48: pinned version, content hash, license, SBOM, malware/secret scan, deterministic build, signature support, source provenance, permissions, network requirements, no hidden auto-install; mandates write / materialise tools remain approval-controlled)
3. **`proposal.md`** — Why (Phase 5 ships the orchestrator + capability discovery; Phase 6 ships the agent integration; MCP is the documented primary interface per §36; 17 semantic tools expose the Phase 4 / Phase 5 surface to coding agents). Goal (the ten spec deltas + the close-out task 95). Affected capabilities (table: capability → architecture sections → task → spec delta path). Out of scope (the existing `tools/mcp/project-context-mcp/` harness-side MCP server is NOT Phase 6; the A2A integration is deferred to Phase 10; the control plane is Phase 7; the security enterprise boundary is Phase 8; the distribution one-click launcher is Phase 9). Compatibility / migration impact (zero production code; same as Phase 4 / 5 prep changes). Related knowledge (Wiki, ADR, harness, source code paths).
4. **`design.md`** — Thin reference plus: a 9-version-dimension matrix; the per-packager shape (Codex / Claude Code / OpenCode / generic); the per-vendor entry-point list (Codex `.codex-plugin/plugin.json` vs `plugin.json`; Claude Code `.claude-plugin/plugin.json`; OpenCode `package.json`); the manifest schema for `project-intelligence://distribution/manifest`; the deterministic-build expectation; the security gate checks the packagers call before emit.
5. **`context-impact.md`** — Knowledge to create (Wiki pages, ADRs). Knowledge to update (Phase 4 / 5 pages remain unchanged; new platform-overview / glossary / INDEX entries). Knowledge to review for staleness (the `tools/mcp/project-context-mcp/` should not be confused with the future `pi_platform/mcp/`; flag this in the review list). Document the close-out task 95 explicitly (Wiki, ADR, archive, CURRENT.md).
6. **`tasks.md`** — Mirror the canonical Phase 6 tasks 85-95 from `plan-v0-8-platform-architecture/tasks.md`. Each task references the relevant spec delta path and the verification command. The tasks.md must clearly mark all of 85-95 as `[ ]` because this is the prep change.
7. **Mirrored implementation change folder** `openspec/changes/implement-phase-6-agent-integration/` with the same 10 spec deltas (verbatim copy), `proposal.md`, `design.md`, `context-impact.md`, `tasks.md`. Future archive step promotes the same delta set into the canonical specs directory.

## Hard "do NOT"s

- **Phases 7-10** (Control plane, Security enterprise boundary, Distribution one-click launcher, A2A). Stay disciplined.
- Touching invariants #1-#4 (canonical/runtime boundary, Git as source of truth, bidirectional sync, deterministic serialization) or the §17 ANN-vs-knowledge-graph separation. The MCP server MUST NOT introduce a new runtime store; it composes the Phase 3 storage and Phase 4 retrieval.
- Breaking the Phase 1-5 round-trip / cross-branch reuse / retrieval-first policy invariants. The MCP server is a thin adapter; it MUST NOT change the Phase 5 `QueryOrchestrator` / `ContextAssembler` / `CapabilityDiscovery` semantics.
- Modifying Phase 1-5 capability specs under `openspec/specs/2026-10-04-*/` or `openspec/specs/2026-10-05-*/`.
- Modifying `tools/mcp/project-context-mcp/` (the harness-side MCP server) — it is a different deliverable owned by a different scope.
- Bundling a non-Apache / non-MIT model or runtime for the new MCP server without a documented SPDX entry. The MCP server itself can be Apache-2.0 (the Python `mcp` SDK is Apache-2.0; confirm in the SPDX inventory).
- Generating the `dist/codex/`, `dist/claude-code/`, `dist/opencode/`, `dist/generic-agent/` plugin bundles in this prep change. Those are implementation artifacts; the prep change only documents the contract.
- Authoring the `SKILL.md` file content in this prep change. The prep change only documents the §37 contract; the implementation change authors the actual `distribution/skills/project-intelligence/SKILL.md` content.

## Verification gates (all must PASS / valid before declaring done — for the prep change only)

- `openspec validate prepare-phase-6-agent-integration --type change --strict` returns `valid` (10 spec deltas, each with `## ADDED Requirements` and `#### Scenario:` blocks, every requirement containing `SHALL` or `MUST`).
- `python3 harness.py check` returns `Harness core checks: PASS` (the OpenSpec CLI validation FAIL is the documented pre-existing quirk).
- `PATH="$(pwd)/tmp/local/bin:$PATH" openspec validate --all --strict` returns no failures across Phase 1-6 deltas (target: `>= 43 passed`; should be `>= 53 passed` after the prep change is on disk but before archive).
- `python3 harness.py wiki-validate` returns `{"ok": true, ...}`.
- `python3 scripts/artifact_manifest.py verify` returns `Artifact manifest: PASS`.
- `python3 -m unittest tests.test_platform_phase1 tests.test_platform_phase2 tests.test_content_address_cross_branch tests.test_canonical_roundtrip tests.test_platform_phase3 tests.test_graph_50k tests.test_platform_phase4 tests.test_retrieval_benchmark tests.test_orchestration_phase5 tests.test_orchestration_policy -v` returns green (235 tests).
- `python3 -m pi_platform.cli license-gate` exits 0.
- The `openspec/changes/implement-phase-6-agent-integration/` change folder exists and the strict validator accepts it.
- `plan-v0-8-platform-architecture/tasks.md` rows 85-95 remain `[ ]` (the prep change does NOT flip plan rows; the implementation change does after adoption).

## Definition of done (for the prep change)

- All step-4 verification gates return PASS / valid.
- `openspec/changes/prepare-phase-6-agent-integration/` exists with `proposal.md`, `design.md`, `context-impact.md`, `tasks.md`, `README.md` (auto-generated by openspec), and ten `specs/2026-10-05-*/spec.md` deltas.
- `openspec/changes/implement-phase-6-agent-integration/` exists with the same 10 spec deltas (verbatim) and the same proposal / design / context-impact / tasks artifacts.
- `plan-v0-8-platform-architecture/tasks.md` rows 85-95 are still `[ ]` (this is the prep change, not the implementation change).
- Phase 1-5 regression suites still green.
- The MCP server design respects the Phase 1-5 invariants (no new runtime store; composes Phase 3 / Phase 4 / Phase 5).
- Final commit on `feature/generate-init-project` with a message that names the ten Phase 6 capabilities and the future implementation boundary. Do NOT push.

## What to STOP and report

- Phase 5 precondition fails: STOP, report blocker.
- `python3` not on `PATH`: STOP, install Python + the OpenSpec CLI as documented.
- A Phase 6 design decision touches invariants #1-#4 or the §17 ANN-vs-knowledge-graph separation: STOP and surface the conflict.
- The Phase 1-5 round-trip / cross-branch reuse / retrieval-first policy invariants would be broken: STOP and report.
- A new dependency is required and its SPDX identifier is missing from `distribution/licenses/dependency-inventory.json`: STOP, do not invent the entry — let the `LicenseGate` approval process own the SPDX-tracked inventory entry.
- The prep change's strict validator surfaces "MUST" / "SHALL" / `#### Scenario:` issues: fix the spec text; do not bypass the validator with `--no-validate`.

## Recommended workflow

1. **Clean up the working tree first.** Commit the Phase 5 handoff state to `.ai/state/CURRENT.md` (or revert it). The Phase 5 close-out already happened; the drift is residual.
2. `skill-router` at intake.
3. Verify the Phase 5 + Phase 6 prep preconditions (working tree, archive dirs, `openspec/CURRENT.md`, harness check, openspec validate, artifact-manifest).
4. `python3 scripts/session_state.py start --id prepare-phase-6-agent-integration --replace-current --goal "Author 10 Phase 6 capability spec deltas and the prep change artifacts (proposal, design, context-impact, tasks) for the Agent Integration phase. Zero production code. Create the implementation change folder with mirrored deltas. Document the close-out task 95 in context-impact.md." --acceptance "All verification gates PASS for the prep change only; openspec validate prepare-phase-6-agent-integration --strict returns valid; openspec validate --all --strict returns >= 53 passed 0 failed (10 new deltas); 235 Phase 1-5 tests still green; wiki-validate ok; artifact-manifest PASS; license-gate exits 0. Both prepare and implement change folders exist with 10 mirrored spec deltas. plan tasks 85-95 remain [ ]." --todo "Author 10 spec deltas (mcp-server, skill-distribution-plane, agent-skill-canonical, version-compatibility-handshake, codex-plugin-package, claude-code-plugin-package, opencode-plugin-package, generic-agent-bundle, agent-adapter-contract, plugin-supply-chain-security); proposal, design, context-impact, tasks; mirrored implementation change; verify strict validator passes; final commit" --openspec-change prepare-phase-6-agent-integration`.
5. Read the architecture doc end-to-end (§36-§51, §5, §17) before authoring the first spec delta. Use `kb_get` on the LLM Wiki for any referenced node.
6. Author the 10 spec deltas with `## ADDED Requirements` and `#### Scenario:` blocks. Every requirement body MUST contain `SHALL` or `MUST`. Each scenario MUST include `Given` / `When` / `Then`. Watch the strict validator's "deterministic level selection" / "deterministic bundle ordering" MUST-content style (Phase 4 / 5 trap).
7. Author `proposal.md`, `design.md`, `context-impact.md`, `tasks.md` for the prep change. Mirror the Phase 5 style.
8. Copy the 10 spec deltas verbatim into the `implement-phase-6-agent-integration/` change folder. Author its `proposal.md`, `design.md`, `context-impact.md`, `tasks.md` as thin references to the prep change.
9. Run `openspec validate prepare-phase-6-agent-integration --type change --strict` and `openspec validate implement-phase-6-agent-integration --type change --strict` until both return `valid`.
10. Run all verification gates. Dispatch a `deepseek-verify` subagent to rerun the strict validator + Phase 1-5 regression suite + harness check in a fresh working copy.
11. `python3 scripts/session_state.py checkpoint --status reviewing` (with `verified` listing every gate's pass output).
12. **Do NOT archive the prep change** in this iteration. The future `implement-phase-6-agent-integration` change uses the prep change as a prerequisite and archives both at the end. This matches the Phase 4 / 5 pattern.
13. **Do NOT flip plan rows 85-95 to `[x]`**. The prep change ships them as `[ ]`; the implementation change flips them after adoption.
14. **Do NOT update `openspec/CURRENT.md`**. The implementation change updates CURRENT.md when the ten Phase 6 specs are adopted.
15. Final commit with a message that names the ten Phase 6 capabilities and the future implementation boundary. Do NOT push.

## Project context refresh — what the LLM Wiki currently says about Phase 5 / orchestration

Quick refresher so the prep change does not duplicate or contradict existing Wiki content:

- `modules/retrieval.md` (Phase 4 module map) — describes the 8 ports / cores / adapters / production graph expansion.
- `modules/embeddings.md` (Phase 4 embedding-model module map) — the `HashingEmbeddingAdapter` default + opt-in `MultilingualSentenceTransformerEmbeddingModel`.
- `modules/context-assembler.md` (Phase 4 context-assembler module map) — `ContextBudget`, `Citation`, `ContextBundle`.
- `modules/orchestrator.md` (Phase 5 query orchestrator module map) — `DefaultQueryOrchestrator`, `OrchestrationLevel`, `OrchestrationResult`, the `retrieval-first-violation` counter.
- `modules/llm-port.md` (Phase 5 local LLM port module map) — `StubLocalLLMAdapter` default, opt-in `llama-cpp` / `transformers` / `external-llm`.
- `modules/task-context.md` (Phase 5 task context builder module map) — `BUNDLE_SLOT_PRIORITY`, `TaskContextBundle`, the slot value types.
- `interfaces/hybrid-retrieval.md` (Phase 4) — `RetrievalHit` source vocabulary, RRF default.
- `interfaces/reranker.md` (Phase 4) — `DEFAULT_RERANK_BUDGET`, cross-encoder / BM25-light / ColBERT-style.
- `interfaces/capability-discovery.md` (Phase 5) — `CapabilityDescriptor` / `CapabilityFeatures` / `serverVersion` / `mcpApiVersion` / `knowledgeSchemaVersion` / `okfVersions` / `features.{hybridRetrieval, graphExpansion, okf, materialization, a2a, localLlm}`.
- `adr/0009-embedding-model-selection.md` — stdlib-only hashing default + opt-in `paraphrase-multilingual-MiniLM-L12-v2` Apache-2.0.
- `adr/0010-hybrid-fusion-strategy.md` — RRF default with `k=60` and `dense_weight=0.5, sparse_weight=0.5`.

The Phase 6 prep change extends the Phase 4 / 5 surface with the MCP server, the skill distribution plane and the plugin packagers. The Wiki is the durable source-of-truth and must be referenced (not duplicated) in the spec deltas.

## Agent team / agentic dispatch (use the multi-agent tools)

This brief expects the next iteration to be run by a single primary agent. The primary agent may dispatch to:

- `explore` (fast, read-only research) for skill-format research, MCP SDK contract research, vendor-plugin-format research, or LLM-Wiki structural searches.
- `mimo-flash` (default intelligent worker) for per-spec-delta authoring, per-Wiki-page drafting, or focused code-investigation tasks that need fresh context.
- `mimo-pro` (highest capability) for architecture design reviews of §39 version handshake, §45 plugin generation pipeline, §46 agent adapter contract, or §48 plugin supply-chain security. Use sparingly; only when the design question is consequential.
- `deepseek-verify` (independent verifier) for end-of-iteration independent verification: rerun the strict validator across all 10 deltas, rerun wiki-validate, rerun harness check, rerun the Phase 1-5 regression suite (235 tests), rerun `python3 scripts/artifact_manifest.py verify`, rerun `python3 -m pi_platform.cli license-gate`. Report the full pass / fail list.

Do NOT dispatch for trivial one-step tasks. Use direct file reads for single-fact lookups. Use the MCP `kb_search` / `kb_get` / `spec_context` tools (via the existing `tools/mcp/project-context-mcp/`) to retrieve LLM Wiki nodes and OpenSpec state without bulk-reading the repository.

## Handoff and traceability

- The active session `implement-phase-5-orchestration` is `complete`. The prep iteration's session id is `prepare-phase-6-agent-integration`. The handoff JSON lives at `.ai/state/handoffs/prepare-phase-6-agent-integration.json`.
- The implementation iteration that follows this prep change will use session id `implement-phase-6-agent-integration` and handoff JSON at `.ai/state/handoffs/implement-phase-6-agent-integration.json`.
- The plan change `openspec/changes/plan-v0-8-platform-architecture/` is the authoritative source for task ordering; tasks 85-95 are the Phase 6 scope. Tasks 96-123 (Phase 7-10) are out of scope.
- The prep change ships with `status: planning` then `status: executing` then `status: reviewing`; it does NOT reach `status: complete` until the implementation change adopts it. Use `python3 scripts/session_state.py checkpoint --status complete` only after the implementation change archives both prep and implement changes.
