# Next iteration prompt — implement Phase 6 agent integration

## Current workflow / state (read this first)

You are the implementation agent for Phase 6 (Agent
Integration) of the v0.8 Project Intelligence Platform.
Preparation and an independent review are complete and
uncommitted in the working tree; this iteration ships
production code. There is **no** Phase 6 product code on
disk yet, despite the name. Read the current state before
deciding anything.

### Repository state

- Branch: `feature/generate-init-project` (8 commits
  ahead of `origin/feature/generate-init-project`, do
  **not** push).
- HEAD: `7eeff65 docs(agent-integration): prepare Phase 6
  capability specs (tasks 85-95)`.
- Working tree: dirty. The review session
  (`review-phase-6-preparation`, status `complete`) left
  many files modified and three untracked:
  - `.ai/state/handoffs/phase-6-prep-brief.md` —
    historical authoring input from the preparation
    iteration. Not the implementation instruction; do
    not rerun preparation.
  - `.ai/state/handoffs/review-phase-6-preparation.json`
    — review session handoff.
  - `.ai/wiki/project/phase-6-readiness.md` — readiness
    Wiki page authored by the review session.
  - `docs/handoff/phase-6-implementation-prompt.md` —
    older draft of this prompt that the review session
    updated; this file supersedes it.
- The review's substantive corrections to the prep /
  implementation spec deltas, design, proposal, context-impact
  and tasks are **uncommitted** in the working tree. Run
  `git status` and `git diff` to see exactly what is
  pending. The implementation change will commit
  production code on top.

### OpenSpec state

- `openspec/CURRENT.md` lists 30 accepted product
  capabilities (5 Phase 1, 9 Phase 2, 9 Phase 3, 8 Phase
  4, 5 Phase 5). Phase 6 is **not** accepted yet.
- `openspec/changes/` currently has:
  - `archive/` — 10 prior implementation/preparation
    changes;
  - `plan-v0-8-platform-architecture/` — active plan
    change; tasks 1-84 `[x]`, tasks 85-95 `[ ]`,
    tasks 96-123 `[ ]`;
  - `prepare-phase-6-agent-integration/` — active prep
    change with 10 spec deltas under `specs/`;
  - `implement-phase-6-agent-integration/` — active
    implementation change with the same 10 mirrored deltas.
- Both Phase 6 changes are `valid` under
  `openspec validate --strict` after the review's
  corrections (45 passed, 0 failed across the canonical
  harness). The review corrected mirrored contracts,
  design, links, version-handshake semantics, approval
  trust boundary, filter preservation, hydrate-before-
  serving, immutable resource bytes, whole-tree
  reproducibility, support-vs-fabricated dimensions and
  shared release identity.

### Session state

- Last session: `review-phase-6-preparation`,
  `status: complete`. See
  `.ai/state/handoffs/review-phase-6-preparation.json`.
- Active session for this iteration:
  `implement-phase-6-agent-integration`. Start it
  through
  `python3 scripts/session_state.py start --id
  implement-phase-6-agent-integration --replace-current
  ...` with acceptance criteria, todos, change ID
  (`implement-phase-6-agent-integration`) and the open
  change references.
- Do not overwrite unrelated user files or the prep
  brief's reference data. The brief is historical input,
  not an instruction to redo preparation.

### Source / harness state

- `python3` 3.12.3 on PATH.
- `tmp/local/bin/openspec` symlink resolves to v1.4.0+
  (npm install). Always add
  `PATH="$(pwd)/tmp/local/bin:$PATH"` for OpenSpec CLI
  calls.
- `tools/markdown/project-context-mcp/` (Python harness
  MCP server) is a **separate deliverable** from the
  proposed `pi_platform/mcp/` package. Do not modify
  the harness-side MCP.
- `distribution/skills/project-intelligence/` does not
  yet exist; `distribution/{codex,claude-code,opencode,
  generic-agent}/` contain only `.gitkeep` placeholders
  and are not the generated output root.
- `distribution/licenses/dependency-inventory.json` is
  populated with Phase 1-5 entries (`mcp==1.30.0`
  Apache-2.0 for the harness; model entries
  `cross-encoder-ms-marco-MiniLM-L-6-v2` MIT,
  `paraphrase-multilingual-MiniLM-L12-v2` Apache-2.0).
  Any new Phase 6 dependency must pass `LicenseGate`
  before the inventory records it.

### LLM Wiki state

- 48 documents. Phase 1-5 module / interface / glossary
  / ADR coverage is intact. The review session added
  `.ai/wiki/project/phase-6-readiness.md` and updated
  `.ai/wiki/INDEX.md`, `architecture/platform-overview.md`
  and `project/implementation-roadmap.md`. **No**
  Phase 6 interface / module / ADR pages exist yet —
  these are part of the implementation work (task 95).

### Verification gates (must remain PASS or improve)

- `openspec validate prepare-phase-6-agent-integration
  --strict`: valid
- `openspec validate implement-phase-6-agent-integration
  --strict`: valid
- `openspec validate --all --strict`: ≥ 45 passed
  (increases as Phase 6 specs are adopted)
- `python3 harness.py check`: configuration /
  OpenSpec schema / Wiki / artifact manifest; do **not**
  treat the documented `OpenSpec CLI validation FAIL`
  as a passing gate — if it appears, report the actual
  CLI validator status under `tmp/local/bin/openspec
  validate --all --strict` separately and gate on
  that.
- `python3 harness.py wiki-validate`: ok=true
- `python3 scripts/artifact_manifest.py verify`: PASS
- `python3 -m pi_platform.cli license-gate`: exit=0
- Phase 1-5 regression suite (current 334 tests across
  27 modules; previously 235 tests before Phase 5
  additions): green

## Authoritative requirements

### Source of design (canonical)

- `project-intelligence-platform-architecture-v0.8.md`
  §§36-49 — MCP integration (17 semantic tools +
  describe_capabilities), versioned Agent Skill
  distributed with the MCP server, skill distribution
  plane (URI namespace), protocol and artifact version
  compatibility (9 dimensions, semver handshake),
  agent integration packaging layer (Ports-and-Adapters),
  Codex / Claude Code / OpenCode / generic-agent
  profiles, plugin generation pipeline (deterministic,
  agreed shared release identity), agent adapter
  contract (8 ops), capability discovery (§47), supply-
  chain security gate, integration quality gates and
  evals (§49). Also §§5 (licence governance, model
  licences separate), §17 (ANN-vs-knowledge-graph
  separation) and §68 architectural invariants #1-#4
  (canonical / runtime separation, Git as source of
  truth, bidirectional sync, deterministic round-trip).
- OpenSpec §36 tool list is exhaustive — additional
  tools are documented extensions and MUST NOT shadow
  the §36 names.

### Accepted behaviour

Start at `openspec/CURRENT.md`. Read each accepted Phase
1-5 capability spec the implementation composes:
`runtime-store`, `sharded-graph`, `provenance-state-
model`, `freshness`, `multi-stage-retrieval`, `hybrid-
retrieval`, `context-assembler`, `embedding-model`,
`query-orchestrator`, `local-llm-port`, `task-context-
builder`, `capability-discovery`, `retrieval-first-
policy`. The Phase 6 MCP server is a thin adapter over
these.

### Proposed behaviour (Phase 6)

Ten mirrored spec deltas under both
`openspec/changes/prepare-phase-6-agent-integration/
specs/` and `openspec/changes/implement-phase-6-agent-
integration/specs/`:

1. `mcp-server` (§36, §47) — 17 semantic tools +
   `describe_capabilities`; retrieval-first routing;
   trusted approval boundary; filter preservation;
   hydrate-before-serving; explicit (non-fabricated)
   provenance.
2. `skill-distribution-plane` (§38, §37) — immutable
   pinned URIs; full-package file inventory + hash;
   retained-release parity; manifest with
   `distributionSchemaVersion` as identifier (not
   semver) and `a2aAdapterVersion` marked unavailable
   until Phase 10.
3. `agent-skill-canonical` (§37, §39) — concise
   `SKILL.md` (≤ 8 KB), 10-step behaviour contract,
   `when-not-to-use`, stale/conflict, version-mismatch,
   security bypass, read-vs-write guidance; five
   progressive-disclosure references.
4. `version-compatibility-handshake` (§39, §47) —
   9 dimensions, semver ranges for API/skill/adapter,
   explicit identifier sets for profiles/schemas,
   unavailable dimensions reported not invented,
   typed `VersionIncompatibleError` with offered /
   client / adapter / upgrade instructions.
5. `codex-plugin-package` (§41, §45) — generated,
   deterministic across the **complete output tree**;
   legacy `.codex-plugin/plugin.json` fallback only
   for a recorded client profile that requires it.
6. `claude-code-plugin-package` (§42, §45) —
   `.claude-plugin/plugin.json` + `.mcp.json`;
   stable slug; marketplace-ready metadata.
7. `opencode-plugin-package` (§43, §45) — npm-
   publishable or local-project-usable; documented
   bootstrap fallback when the supported client
   profile has no Agent Skills loading convention.
8. `generic-agent-bundle` (§44, §45) — stdio +
   HTTP MCP examples, `AGENTS.example.md`,
   `README.md`.
9. `agent-adapter-contract` (§46, §40) — 8
   operations, plug-in replaceable installers,
   adapters MUST NOT own retrieval / business rules,
   documented typed error vocabulary.
10. `plugin-supply-chain-security` (§48, §45) —
    pinned version, content hash, SBOM, malware /
    secret scan, deterministic build, signature
    support against a configured trusted key, source
    provenance, permissions, network requirements, no
    hidden auto-install, approval-gated materialise
    tools, **shared release identity agreement across
    vendors**.

### Wiki context (refresh before deep work)

Read `.ai/wiki/INDEX.md` and only the relevant
nodes. Use `kb_search` / `kb_get` / `spec_context` /
`code_symbol` through the harness MCP at
`tools/mcp/project-context-mcp/` when available; check
the source code directly. The Wiki is durable
explanation, **not** normative; accepted OpenSpec wins
on conflict. Report mismatches, do not silently
rewrite them.

Critical Wiki nodes for this iteration:
`architecture/platform-overview`,
`architecture/system-overview`, `glossary/platform`,
`project/project-map`, `project/implementation-roadmap`,
`project/phase-6-readiness`, `interfaces/capability-
discovery`, `interfaces/context-assembler`,
`interfaces/hybrid-retrieval`, `modules/orchestrator`,
`modules/llm-port`, `modules/task-context`,
`adr/0002-canonical-runtime-separation`,
`adr/0003-license-governance-default`,
`adr/0005-platform-source-language`,
`adr/0008-embedded-storage-selection`,
`adr/0009-embedding-model-selection`,
`adr/0010-hybrid-fusion-strategy`.

## Outstanding prerequisites — fix BEFORE Phase 6 ships

These are source-backed gaps documented in the readiness
Wiki. The Phase 6 implementation cannot enable MCP writes
or filtered L1/L2 until they are addressed.

### 1. Repair the approval security boundary

`pi_platform/core/sync/materialise.py` currently checks
that an approval token is **nonempty** for
`REQUIRE_APPROVAL` actions; there is no validation that
the token authenticates against a trusted issuer and
`DENY` is not explicitly rejected. A caller-chosen
nonempty token is **not** proof of approval.

- Define a trusted local / operator approval boundary
  scoped to action, repository, requested changes and
  validity window.
- Reject `DENY` unconditionally.
- Validate authenticity and scope before mapping to
  `MaterialiseService.materialise_durable_changes`.
- Preserve `LOCAL_ONLY` exclusion, licence governance
  and deterministic serialization.
- Add focused negative tests for: missing, forged,
  expired, wrong-scope, wrong-action approvals.
- Both `project.materialize_knowledge` and
  `project.refresh_sources` MUST fail closed until
  this passes.
- If this changes a public contract, create a bounded
  OpenSpec delta before treating the fixed service as
  the production authorization system. Do not paper
  over the stub.

### 2. Filter / scope preservation through orchestration

`QueryOrchestratorPort.orchestrate(query, level,
task_context)` has no filters / project-version
argument. Filtered retrieval is therefore dropped at L1 /
L2 unless you compose the Phase 4 typed retrieval
explicitly. Required:

- Use `MultiStageRetrievalPort.retrieve` with a typed
  `RetrievalQuery` (filters, projectVersion, security
  scope, contextBudget) for filtered L0.
- Reject filtered L1 / L2 explicitly with a documented
  error until a separately specified extension
  preserves those filters through escalation.
- Graph / exact lookup tools (`project.get_entity`,
  `project.find_implementation`,
  `project.trace_requirement`, `project.find_references`)
  MUST enforce project / Git-version / security
  eligibility before returning records or edges; the
  graph port alone does not enforce these constraints.

### 3. Hydrate / reconcile before serving project evidence

The MCP server MUST wait for a consistent hydrate /
reconcile report before serving project knowledge.
Inconsistent state after start, branch switch or refresh
fails with a documented readiness error; no cross-
version or stale evidence is returned. Follow the
accepted bidirectional sync contract.

### 4. No fabricated evidence

`ProvenancePort` exposes `evidence(entity_id)`,
`current_state`, `staleness_map` and `events` — not
`lookup`. Graph lookups have no built-in filter
argument. Tool results MUST NOT invent requirement /
reference / provenance records; missing evidence is
described explicitly as missing.

### 5. Version-source / dimension honesty

`DefaultCapabilityDiscovery` currently reports server
`0.8.0`, MCP API `1.3.0`, schema `0.7.0`, OKF `0.2`
by default; root package metadata is `0.1.0`. The
handshake must map dimensions to actual offered
metadata, not copy architecture example numbers.
`mcpApiVersion` is the **product tool-schema API**,
independent of the MCP SDK package version and the
MCP wire protocol version. Unavailable dimensions
(e.g. `a2aAdapterVersion` until Phase 10,
`agentAdapterVersion` / `runtimeIndexSchemaVersion`
until implemented) are reported **unavailable**, not
fabricated with example values.

## Skills to load (skill-router at intake)

Run:

```bash
printf '%s' "<compact task text>" \
  | python3 scripts/skill_router.py --profile balanced
```

Follow the router's `required_skills` only. Confirmed
relevant skills for this iteration:

- `skill-router` — at intake.
- `openspec-change` — for adopting the implementation
  change, validation and archive flow.
- `verification` and `verification-before-completion`
  — gate each task; do not claim success without
  evidence.
- `lean-build` — Phase 6 is overbuilding-prone; defer
  vendor-specific choice to runtime config.
- `karpathy-guidelines` — explicit assumptions,
  surgical changes, verifiable goals.
- `architecture-design` — REQUIRED for §39 version-
  handshake design and §48 plugin-supply-chain
  security trade-offs. Record trade-offs in
  `design.md` before implementation.
- `test-driven-development` — TDD-first for the MCP
  tool / resource / version / security / vendor
  smoke tests; the tests are the contract.
- `safe-refactor` — Phase 6 composes Phase 3 / 4 / 5
  surface; the regression suite (currently 334 tests)
  MUST stay green.
- `llm-wiki-maintenance` — Wiki updates at close-out.
- `code-reviewer` and `requesting-code-review` —
  before final close-out.
- `systematic-debugging` / `investigate-first` — if a
  verification check fails.

## Agent team — use available capabilities

The repository is wired with the `task` tool. Discover
the current roster instead of assuming names. From
your available roster, assign bounded independent work
to:

- **read-only investigator** — vendor schema /
  licensing / source checks for Codex, Claude Code,
  OpenCode and a representative generic agent. Pin
  the supported client version and record the official
  documentation URL for each.
- **trusted-write-boundary implementation worker**
  — the MaterialiseService approval fix (prerequisite
  #1) with focused negative tests; owns
  `pi_platform/core/sync/materialise.py` and any new
  trusted-boundary module.
- **MCP server / resource implementation worker** —
  `pi_platform/mcp/`, the resource plane, the SDK
  pin, stdio + Streamable HTTP transports. Owns
  `tests/test_mcp_server.py` and the SDK session
  integration tests.
- **packaging / adapter implementation worker** —
  the four per-vendor packagers under
  `pi_platform/adapters/agent_integration/packagers/`,
  the supply-chain security gate, the agent adapter
  contract base class. Owns
  `tests/test_codex_plugin.py`,
  `tests/test_claude_code_plugin.py`,
  `tests/test_opencode_plugin.py`,
  `tests/test_generic_agent_bundle.py`,
  `tests/test_agent_adapter.py`,
  `tests/test_supply_chain_gate.py` and the
  deterministic-build inventory test.
- **independent reviewer** — strict validator,
  wiki-validate, license-gate, artifact-manifest,
  full regression run, byte-identity diff between two
  isolated packager runs, vendor lifecycle smoke
  tests in isolated temporary projects. Treat as
  fresh-context verification; do not let
  implementation workers self-verify.
- **strongest reasoning role** — version-handshake
  design (§39), supply-chain security gate (§48),
  plugin generation pipeline (§45) and agent adapter
  contract (§46) decisions.

Give each agent explicit file ownership and source
constraints; avoid overlapping edits. Centralise
review. If a worker fails to start, record it and use
sequential isolated review passes; do not claim
independent verification you did not perform.

## Implementation and verification

### Build order

1. **Prerequisite 1** — repair approval boundary +
   focused negative tests. Both write tools MUST fail
   closed until this passes.
2. **Compatibility / adapter / trusted security
   boundaries** — `VersionCompatibilityPolicy`,
   `AgentIntegrationAdapter` base class,
   `PluginSupplyChainSecurityGate` core (tasks 88, 93,
   94).
3. **Canonical skill** — author
   `distribution/skills/project-intelligence/SKILL.md`
   plus the five references; record its SHA-256 as
   the canonical release metadata (task 87).
4. **Server / resources** — MCP server, skill
   distribution plane, resource URIs (tasks 85, 86).
5. **Generated vendor profiles** — Codex, Claude Code,
   OpenCode, generic-agent packagers (tasks 89-92).
6. **Close-out** — Wiki, ADR, archive, CURRENT,
   plan rows (task 95).

### Hard rules

- The MCP server is a thin adapter. It composes the
  Phase 5 `QueryOrchestratorPort`, `LocalLLMPort`,
  `TaskContextBuilderPort`, `CapabilityDiscoveryPort`
  and the Phase 4 `MultiStageRetrievalPort`,
  `HybridRetrievalPort`, `ContextAssemblerPort`. It
  does **not** introduce a new runtime store.
- §36 tool list is exhaustive — additional tools are
  documented extensions and MUST NOT shadow the §36
  names.
- Use the official MCP Python SDK (`mcp==1.30.0`,
  Apache-2.0 already in `dependency-inventory.json`
  for the harness; confirm shared or separate
  top-level entry before installing in the platform
  container). Pin transitive versions independently;
  licence success does not prove installability.
- Default transport is stdio. Support explicit
  Streamable HTTP configuration. Do **not** expose an
  unauthenticated network listener by default or
  assume Phase 8 policy exists.
- Distinguish SDK package version, MCP wire protocol
  version and `mcpApiVersion` (product tool-schema
  API). Never copy architecture example numbers as
  runtime defaults.
- Generated vendor bundles live under
  `tmp/local/dist/{codex,claude-code,opencode,
  generic-agent}/` by default. The architecture's
  `dist/<vendor>/` is the **logical** release layout.
  Caller-selected export destinations are validated.
- All four bundles are generated from **one release
  input set**. They MUST agree on skill content hash,
  version, MCP range, license, server identity and
  required capabilities; the gate rejects mismatch.
- Determinism compares a sorted **whole-output path/
  hash inventory** under fixed build inputs across
  two isolated runs — SKILL.md hash alone is not
  sufficient. Document self-digest exclusions.
- Optional signature verification uses a
  **configured trusted key**, never a key supplied by
  the artifact.
- Adapter install / uninstall is limited to owned
  configuration; preserve pre-existing user entries.
  Optional vendor runtimes (TypeScript / JavaScript for
  OpenCode adapter) MUST NOT be prerequisites for
  core correctness.
- Adapter MUST NOT own retrieval / business rules.
- Phase 1-5 invariants #1-#4 and §17 ANN-vs-
  knowledge-graph separation MUST NOT be violated.

### Verification evidence

- **MCP SDK session tests** — actual stdio and
  Streamable HTTP sessions covering startup,
  initialize, `tools/list`, `resources/list` /
  `templates`, `tools/call`, `resources/read` and
  shutdown with bounded timeouts and clean child
  teardown. A blocking `mcp-serve` invocation alone
  is not a smoke test.
- **Bounded retrieval / context** — filtered version-
  correct retrieval and exact lookup; bounded task
  context from a goal; immutable pinned resources.
- **Security scope** — malformed / incompatible
  versions, denied / forged / expired / wrong-scope
  approvals, refresh approval. Filtered L1 / L2
  rejected explicitly.
- **Branch reconciliation** — serve only after
  consistent hydrate; reject inconsistent state;
  reject cross-version evidence.
- **Vendor lifecycle** — for each vendor, validate
  against its supported official schema / client
  version with citation, exercise install /
  configure / health / uninstall in an isolated
  temporary project. Preserve pre-existing user
  configuration on uninstall. If a client is
  unavailable, report NOT RUN; do **not** claim PASS.
- **§49 fixtures** — deterministic skill activation,
  tool-selection, retrieval-first compliance,
  version-mismatch, stale / conflict, security-filter
  and snapshot-upgrade tests. Record context budget,
  latency and setup results. Live agent evals are
  optional and must be reported separately from
  deterministic tests.
- **Permission of `approval_id` for materialise and
  refresh** — typed rejection of every negative
  case listed above. Both tools fail closed until the
  trusted boundary passes.
- **OpenSpec validation** — strict
  `openspec validate implement-phase-6-agent-
  integration --type change --strict` returns valid;
  `openspec validate --all --strict` returns no
  failures across Phase 1-6 deltas (target ≥ 45
  passed; increases as Phase 6 specs are adopted).
  Validator counts are **counts of changes/specs**, not
  individual delta requirements.
- **Harness gates** — `python3 harness.py wiki-validate`
  ok=true; `python3 scripts/artifact_manifest.py verify`
  PASS; `python3 -m pi_platform.cli license-gate` exit=0;
  `python3 -m unittest` for the Phase 1-5 modules plus
  the new Phase 6 test modules reports green.
  **Record the actual current counts** (the regression
  suite is now 334 tests across 27 modules; Phase 5
  shipped 235 in earlier count). Do not copy an
  earlier count.
- **Do not waive a failing harness check as a pre-
  existing quirk without reporting it explicitly.**
  Re-run `PATH="$(pwd)/tmp/local/bin:$PATH" openspec
  validate --all --strict` directly and report its
  result alongside the harness output.

### Missing / not-yet-implemented evidence

- Live Codex / Claude Code / OpenCode client sessions
  if the client binary is unavailable in the sandbox:
  NOT RUN with reason. Do not assert PASS.
- Live agent eval fixtures: NOT RUN until a
  representative agent harness is wired; record
  separately from deterministic tests.
- Missing clients / live evals do **not** waive the
  remaining release gates.

## Knowledge, state and adoption

- Update affected Wiki context as observations
  change. Wiki does not outrank accepted OpenSpec.
- Record architecture decisions in `design.md` as
  they are made; promote verified ones to ADRs with
  available stable IDs (likely `0011-agent-
  integration-packaging`, `0012-version-compatibility-
  handshake`, `0013-plugin-supply-chain-security`).
  Confirm the IDs are unused before creating files.
- Use `python3 scripts/session_state.py checkpoint`
  after material implementation steps, decisions,
  blockers / failures and verification results, and
  before compaction, handoff or the final response.
- **Never** manually edit
  `.ai/state/handoffs/*.json` or
  `.ai/state/CURRENT.md`; the scripts own those
  files.
- Maintain `working_set` entries and a concrete
  `next_action` so another agent can resume.

## Close-out (task 95)

Only after every implementation gate passes:

1. Reconcile the provisional
   `2026-10-05-<capability>` delta identities to the
   **actual first Git acceptance date** in both
   change folders.
2. Promote exactly one set of deltas (the
   implementation change) into
   `openspec/specs/2026-10-05-*/`. Do **not** apply
   the prep change's mirrored `## ADDED Requirements`
   set; archive preparation without reapplying it.
3. Archive the prep change under
   `archive/<actual-archive-date>-prepare-phase-6-
   agent-integration/` and the implementation change
   under
   `archive/<actual-archive-date>-implement-phase-6-
   agent-integration/`. Use **actual archive dates**.
4. Update `openspec/CURRENT.md` with the ten
   accepted Phase 6 capabilities. Update
   `.ai/wiki/INDEX.md`, `architecture/platform-
   overview.md`, `project/implementation-roadmap.md`,
   `project/project-map.md`, `glossary/platform.md`.
5. Create the documented new Wiki nodes under
   `.ai/wiki/interfaces/` and `.ai/wiki/modules/`
   and the proposed ADRs under `.ai/wiki/adr/`.
6. Flip `plan-v0-8-platform-architecture/tasks.md`
   rows 85-95 to `[x]`.
7. Final commit on `feature/generate-init-project`
   with a message that names the ten Phase 6
   capabilities and the close-out. **Do not push.**

## Out of scope

- Phases 7-10 (control plane, security enterprise
  boundary, distribution one-click launcher, A2A).
  Tasks 96-123 stay `[ ]`.
- `tools/mcp/project-context-mcp/` — separate
  harness deliverable.
- Modifying unrelated Phase 1-5 accepted specs.
- Adopting `openspec/CURRENT.md` changes during
  preparation; preparation does not adopt.

## Acceptance criteria (suggested)

- All prerequisite gaps (approval, filtering, hydrate,
  provenance, version-source honesty) are closed with
  focused negative tests; both write tools remain
  fail-closed until prerequisite 1 passes.
- MCP server boots and serves 17 §36 tools plus
  `describe_capabilities` over stdio and Streamable
  HTTP; SDK session tests are green.
- Canonical `distribution/skills/project-intelligence/
  SKILL.md` + 5 references; `≤ 8 KB` SKILL.md;
  declared YAML frontmatter matches §37 contract.
- Version handshake covers all 9 dimensions with
  semver / identifier-set honesty; typed
  `VersionIncompatibleError` carries failed
  dimension, offered value, client constraint,
  applicable adapter and upgrade instructions.
- Four vendor packagers generate deterministic,
  byte-identical artifacts across the whole output
  tree from a single release input set; they agree on
  shared release identity; supply-chain gate records
  verdict in provenance.
- `AgentIntegrationAdapter` base class exposes the
  documented 8 ops + typed errors; does **not** own
  retrieval / business rules.
- 5 Phase 1-5 modules + 4 Phase 6 modules (`mcp`,
  `agent_integration`, `packagers`, `supply-chain
  gate`) added to `architecture/platform-overview`,
  `project-map`, `INDEX`, `glossary/platform`.
- 3 ADRs created (or their stable IDs reused) with
  options, chosen policy and trade-offs.
- `openspec validate implement-phase-6-agent-
  integration --strict` valid;
  `openspec validate --all --strict` no failures,
  target ≥ 55 passed (45 baseline + 10 adopted
  specs after archive).
- `python3 harness.py check` reports actual current
  results; `wiki-validate`, `license-gate`,
  `artifact_manifest verify` PASS; Phase 1-6
  regression suite green (current 334 tests plus
  Phase 6 additions).
- `plan-v0-8-platform-architecture/tasks.md` rows
  85-95 `[x]` after adoption; both changes archived
  under actual archive dates; `openspec/CURRENT.md`
  lists the ten Phase 6 capabilities.
- Final commit on `feature/generate-init-project`;
  no push.

## Hard "do NOT"s

- Do not push or publish.
- Do not touch invariants #1-#4 or §17 ANN-vs-
  knowledge-graph separation.
- Do not introduce a new runtime store or a new
  knowledge model in the MCP server.
- Do not break the Phase 1-5 regression suite.
- Do not bypass the trusted approval boundary with
  caller-supplied tokens; both write tools fail
  closed until prerequisite 1 is fixed.
- Do not silently drop filters through orchestration.
- Do not fabricate unavailable version dimensions.
- Do not waive a failing harness check as a pre-existing
  quirk without recording the actual CLI output.
- Do not edit `.ai/state/handoffs/*.json` or
  `.ai/state/CURRENT.md` by hand; use
  `session_state.py`.
- Do not modify `tools/mcp/project-context-mcp/`.
- Do not claim independent verification without
  dispatching a fresh-context reviewer.
- Do not bring in Phases 7-10 work.