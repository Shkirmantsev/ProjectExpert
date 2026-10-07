# Design — Phase 6 agent integration (proposed)

This is the shared implementation design. The [implementation change](../implement-phase-6-agent-integration/design.md)
references it; no Phase 6 product code, skill or vendor bundle is shipped by preparation.
Architecture §§36–49 and the proposed [deltas](specs/) define the scope; accepted
Phase 1–5 behavior starts at [CURRENT](../../CURRENT.md). Decisions below are
proposed and become accepted ADRs only with implementation verification.

## Observed current state

Phases 1–5 have accepted specs, source and archived implementation changes.
The product package is `pi_platform`; `platform.mcp` in the roadmap is a
conceptual name, not an import path. The existing harness MCP at
`tools/mcp/project-context-mcp/` serves Wiki/code navigation and is not the
Phase 6 server. `distribution/` already contains scaffolding, not released
agent integrations. No Phase 6 capability belongs in CURRENT yet.

The supported workflow is: resume/checkpoint task state; retrieve selected Wiki,
accepted specs and source evidence; ingest/hydrate version-bound runtime data;
retrieve evidence; optionally escalate through the orchestrator; build bounded
context; materialise approved durable knowledge; verify and adopt a change.
The Phase 6 tools expose these existing operations through a vendor-neutral
adapter without introducing a new knowledge store.

## Prerequisites and observed gaps

1. **Approval security must be repaired before enabling MCP writes.**
   `pi_platform/core/sync/materialise.py` checks only that a token is nonempty
   for REQUIRE_APPROVAL; DENY has no explicit rejection. No trusted token
   issuance/validation exists. This violates the intended approval-controlled
   boundary even though existing tests pass. Prepare a separate narrow fix
   and its required delta if the contract changes. The owning service must
   reject DENY unconditionally. A trusted local/operator boundary must bind
   approval to action, project/repository, requested changes and validity;
   callers must not mint approvals themselves. Validate before dispatch and
   map to the existing `approval_token` only after success. Record explicit
   negative evidence for DENY, missing, forged, expired and wrong-scope approvals.
   Keep both write tools disabled/failing closed until this prerequisite passes.
2. **Filtered L1/L2 composition is not present.**
   `QueryOrchestratorPort.orchestrate(query, level, task_context)` has no
   filters or project-version argument. Use Phase 4 typed retrieval for
   filtered L0; reject filtered L1/L2 explicitly until a separately specified
   extension preserves those filters throughout escalation. Do not silently
   pass unsupported kwargs or drop security/version filters.
3. **Deployment discovery reports registrations, not operational health.**
   `DefaultCapabilityDiscovery` defaults to server `0.8.0`, MCP API `1.3.0`,
   schema `0.7.0` and OKF `0.2`. Root package metadata remains `0.1.0`.
   These identities differ today; document their release meanings before
   packaging instead of copying architecture example `0.7.0` as platform
   runtime version. `mcpApiVersion` is the product tool-schema API, independent
   of SDK package version and MCP wire protocol. A2A is absent in Phase 6.
4. **Some semantic tools need explicit adapters, not existing named methods.**
   Provenance has no `lookup`; graph lookups have no built-in filter argument.
   Source/reference/requirement views must use canonical records and typed
   graph/retrieval results, with not-found/unsupported responses for missing
   evidence. Never invent data or treat absent fields as proof of freshness.
5. **External vendor formats must be validated before release.**
   Architecture layouts are conceptual profiles. Before packaging, check
   official documentation/schema for the supported Codex, Claude Code and
   OpenCode versions, record citations and versions, and map differences in
   adapters. Do not force custom integrity fields into vendor manifests that
   reject them; put release integrity in a shared sidecar when necessary.

These are observed gaps and readiness work, not completed Phase 6 features.
This review changes no product source and does not repair prerequisite code.

## Tool-to-port composition

Every request binds a server-controlled project/repository and current or
explicitly authorized Git version. Client filters may narrow that scope, never
widen authorization. Unknown filters and unbound project scope fail clearly.

| Surface | Existing owner and implementation mapping |
|---|---|
| `project.search` | For filtered L0 construct `RetrievalQuery(text, filters=MetadataFilter(...), projectVersion=..., contextBudget=...)` and call `MultiStageRetrievalPort.retrieve`; wrap in the documented L0 result. Unfiltered escalation uses `QueryOrchestratorPort.orchestrate`. |
| `project.retrieve_context` | Retrieve through Phase 4 and return `contextBundle`, or call `ContextAssemblerPort.assemble(hits, contextBudget=ContextBudget(tokenLimit=...), query=...)` on eligible hits. |
| entity/component/requirement/spec/architecture/dependency lookups | Resolve canonical records, graph and relevant indexed chunks. Check project/version/security eligibility before returning records or traversing relations; the graph port alone does not enforce these constraints. |
| implementation/reference/requirement tracing | Exact structured code/chunk/graph evidence; include provenance and eligible trace edges, not fabricated AST or requirement links. |
| `project.get_project_version` | Existing Git version identity adapter. |
| conflict/stale reports | Hydrate/reconcile conflicts, `ProvenancePort.current_state`, `evidence`, `staleness_map`, `events`, and `FreshnessTrackerPort.snapshot`; describe missing evidence explicitly. |
| `project.build_task_context` | `TaskContextBuilderPort.build(goal, budget_tokens=..., project_version=..., retrieval=...)` after filtered retrieval. Requirement ID is optional narrowing context; goal is required. |
| `project.materialize_knowledge` | Validate approval, convert validated entries to `RuntimeChange`, then `MaterialiseService.materialise_durable_changes(repo_root, cache_root=..., approval_token=..., changes=...)`. Preserve LOCAL_ONLY exclusion, licence gate and deterministic serialization. |
| `project.refresh_sources` | Validate approval and source IDs within configured scope, then the Phase 2 ingestion driver plus runtime reconciliation. Do not dispatch refresh to MaterialiseService. |
| `describe_capabilities` | Exact `CapabilityDiscoveryPort.describe()` JSON, without LLM; do not add the missing handshake dimensions to the Phase 5 response. |

Schemas must document field types, defaults, budget bounds, metadata filter
vocabulary, version scope, not-found/unsupported/readiness/approval errors and
side effects. Serialize typed values at the MCP boundary. Do not infer
retrieval-first enforcement from tools/list ordering. Exact lookups are valid
retrieval-first behavior for known identifiers.

Startup and branch switches must wait for consistent hydrate/reconcile before
serving project evidence, as required by the accepted sync spec.

## Version compatibility model

| Dimension | Authoritative source / comparison |
|---|---|
| `platformVersion` | Map Phase 5 `serverVersion`; current default `0.8.0`. Semver, not SDK version. |
| `mcpApiVersion` | Phase 5 descriptor, default `1.3.0`; actual offered product API or implemented compatibility adapter must satisfy client range. |
| `knowledgeSchemaVersion` | Descriptor/canonical release, default `0.7.0`; semver range. |
| `okfProfileVersion` | `okfVersions` supported set, currently `0.2`; explicit profile identifier. |
| `skillVersion` | Canonical skill release metadata; not authored yet, architecture `1.4.0` is an example. |
| `pluginDistributionSchemaVersion` | Release manifest `distributionSchemaVersion`; explicit identifier, architecture example `1`. |
| `agentAdapterVersion` | Selected adapter release metadata; unavailable until implemented. |
| `runtimeIndexSchemaVersion` | Owning runtime schema metadata; define explicitly before emitting, do not invent a default. |
| `a2aAdapterVersion` | Registered A2A metadata; unavailable until Phase 10. |

Use one documented semver grammar for API/skill/adapter ranges. PEP 440 is not
interchangeable with node-style semver. Profile/schema identifiers use explicit
sets. Record all dimensions and availability, but require only applicable public
compatibility dimensions; unavailable unrequested A2A does not fail startup.
The shared release metadata supplements the unchanged Phase 5 descriptor.
VersionIncompatibleError must identify the failed dimension, offered value,
client constraint, applicable adapter and upgrade instructions. An adapter's
advertised range is usable only when its schema/behavior conversion exists and
is tested. Never accept range overlap without an implementation satisfying it.

## Skill and distribution resources

The canonical source is `distribution/skills/project-intelligence/`, with concise
SKILL.md and progressive references per §37. All custom metadata values remain
strings; validate semantic types only for their appropriate fields.

Stable URIs follow §38. The current manifest exposes platform/API/schema
versions, distribution schema, skill name/version/SKILL.md sha256/MCP range,
OKF supported set and available adapter versions. Manifest/index entries also
provide license, build provenance, full-package file inventory/hash and required
capabilities. Distinguish the existing SKILL.md hash from whole-package integrity;
references and assets are part of the release, not unprotected extras.

Use canonical sorted JSON for fixed release state. Keep raw resources byte-exact;
metadata belongs in manifest/index entries or linked integrity records, not
prepended to SKILL.md. Pin every version URI to immutable release bytes. Retain
older release snapshots when supported, otherwise return version-not-found;
report upgrades separately. Reject traversal, absolute paths, encoded escape
paths and symlinks outside the published package.

## Packaging and supply chain

Canonical source lives under `distribution/skills/`; generated vendor bundles
live under `tmp/local/dist/{codex,claude-code,opencode,generic-agent}/` by default.
The architecture's `dist/<vendor>/` is the logical release layout, relative to
that build root. Existing `distribution/<vendor>/` scaffolding is not the generated
output root. Explicit export destinations are caller-selected and validated.

Conceptual entry points from §§41–44: Codex plugin.json/mcp.json and optional
legacy `.codex-plugin/plugin.json`; Claude Code `.claude-plugin/plugin.json` and
`.mcp.json`; OpenCode package.json/plugin adapter/skill/config; generic skills,
stdio/HTTP examples, AGENTS.example.md and README. Generate a Codex fallback
only for a recorded client profile that requires it. On OpenCode versions without
skill support, provide documented minimal bootstrap instructions rather than
assuming skill installation succeeded. All vendor metadata remains in adapters.

Proposed Python seams: `pi_platform/mcp/`, `ports/agent_integration/`,
`core/agent_integration/`, `adapters/agent_integration/`. Add typed server,
compatibility, adapter, packager and supply-chain surfaces without relocating
Phase 1–5 source. CLI names `mcp-serve`, `plugin-package`, `agent-integration`
are proposed implementation names, not currently available commands.

Use the MCP SDK with a verified compatible pinned release; the existing inventory
records `mcp==1.30.0` for the harness, but the platform dependency and container
installation still need implementation. Confirm dependency licensing and lock
transitive versions independently; licence success does not prove installability.
Support stdio by default and explicit Streamable HTTP configuration; do not expose
an unauthenticated network listener by default or assume Phase 8 policy exists.

Build all vendors from one release input set. Enforce agreement on skill content
hash/version, MCP range, license, server identity and required capabilities (§45).
An unchanged SKILL.md hash alone does not prove deterministic configs, references
or manifests. Compare a sorted whole-output path/hash inventory across isolated
builds, fixing timestamps and provenance inputs. Define self-digest exclusions.
Stage, inspect all files and publish only after the security gate passes; failed
builds leave no usable partial release. Optional signatures verify against a
configured trust root, never a public key accepted solely from the artifact.

Allow approved write capabilities in a skill; reject instructions that bypass
approval. No hidden installation, undisclosed network access, embedded secrets,
unreviewed licences or scope-widening permissions. Adapter install/uninstall is
limited to owned configuration; preserve pre-existing user entries. Optional
vendor runtimes must not become prerequisites for core correctness.

## Verification, decisions and close-out

The [tasks](tasks.md#readiness-ordering-and-integration-evidence) define actual
SDK sessions, vendor lifecycle smoke tests, deterministic fixtures and §49
integration evidence. Missing clients/evals are NOT RUN, not PASS.

Proposed ADRs 0011–0013 cover adapter packaging, compatibility and supply-chain
policy. Confirm unused IDs before creation; record options, chosen policy and
tradeoffs as proposed until verified. Preserve accepted ADRs and core invariants.
Risk controls are the prerequisites and negative/integration tests above: version
coercion, filter loss, write authorization, URI mutability, vendor-format drift,
partial output and false determinism each require explicit evidence.

Preparation may complete now without adoption. Implementation later reconciles
new delta identities to actual first Git acceptance date, promotes exactly one
set of deltas and archives both changes using actual archive dates. Archive the
preparation without duplicate delta application. Only then add accepted Phase 6
capabilities to CURRENT and close plan tasks 85–95.
