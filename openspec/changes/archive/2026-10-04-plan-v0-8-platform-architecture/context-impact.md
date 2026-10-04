# Context impact — plan-v0-8-platform-architecture

## Knowledge to create

- `.ai/wiki/architecture/platform-overview.md` — high-level platform
  architecture boundaries, runtime flow, control plane vs data plane
  split. `kind: architecture`, `status: draft`.
- `.ai/wiki/glossary/platform.md` — platform vocabulary (canonical
  knowledge, runtime working knowledge, hydration, materialisation,
  working-tree overlay, knowledge state, content addressing, OKF,
  capability, hook, plugin, feature flag, secret reference, control
  plane, data plane). `kind: glossary`, `status: draft`.
- `.ai/wiki/adr/0002-canonical-runtime-separation.md` — ADR for the
  architectural invariant #1-4 (canonical vs runtime, Git as
  source of truth, bidirectional sync, deterministic serialization).
  `kind: adr`, `status: proposed`.
- `.ai/wiki/adr/0003-license-governance-default.md` — ADR for the
  default permissive license policy and the review/deny mechanism.
  `kind: adr`, `status: proposed`.
- `.ai/wiki/adr/0004-ports-and-adapters-extension-style.md` — ADR
  for the hexagonal + micro-kernel extension style from §59.
  `kind: adr`, `status: proposed`.
- `.ai/wiki/project/implementation-roadmap.md` — ordered phase
  summary (Phases 1-10) produced from the proposal; `kind:
  project`, `status: draft`.

## Knowledge to update

- `.ai/wiki/INDEX.md` — add the new nodes listed above under the
  relevant knowledge areas (`architecture`, `glossary`, `adr`,
  `project`).
- `.ai/wiki/architecture/system-overview.md` — extend the
  "Principal components" section with a product module map that
  references the Phase 1 specs (`canonical-knowledge-schema`, `git-
  version-aware-runtime`, `bidirectional-canonical-runtime-sync`,
  `license-governance`, `project-knowledge-repository-layout`).
  Add a link to the v0.8 architecture baseline and to the new
  `architecture/platform-overview` node.
- `.ai/wiki/project/project-map.md` — add the
  `platform/`, `project-knowledge/`, `.project-intelligence-cache/`
  and `distribution/` directories under "Main source areas", with
  status `planned`. Reference the new `project/implementation-
  roadmap` node.
- `.ai/wiki/glossary/domain.md` — add cross-links to the new
  `glossary/platform` node for the platform vocabulary.

## Knowledge to review for staleness

- `.ai/wiki/project/harness-framework-adoption.md` — verify the
  scope statement still holds now that a product tree is being
  introduced; the harness remains upstream tooling and the product
  tree must not import the harness in the wrong direction. If any
  assumption has shifted, file a follow-up change.
- `.ai/wiki/architecture/system-overview.md` — current text says
  "Product source tree (to be created)". After this change the
  product source tree is **planned** but not yet created; rewrite the
  phrasing to reflect the new state without breaking the link to
  the v0.8 architecture baseline.
- `.ai/wiki/project/task-handoff.md` — confirm the durable task-
  state lifecycle still applies for the new task
  (`plan-v0-8-platform-architecture`); the new task uses
  `openspec-change` linkage, which the existing model supports.

## Affected implementation

Modules/paths:
- `openspec/changes/plan-v0-8-platform-architecture/` — created by
  this change (artifacts only).
- `openspec/CURRENT.md` — updated when this change is adopted to
  list the five Phase 1 capabilities.
- `.ai/wiki/**` — updated by this change (additive only).
- `platform/`, `project-knowledge/`, `.project-intelligence-cache/`,
  `distribution/` — **not** created by this change; they are the
  target of the next code-producing change that depends on the
  foundation specs.

Primary symbols/interfaces (future, declared by the foundation
specs and design; implemented in the next change):
- `platform.core.canonical.Chunk`, `Entity`, `Relation`,
  `KnowledgeState`, `Manifest`, `OkfAdapter`;
- `platform.core.git.GitPort`, `VersionIdentity`,
  `WorkingTreeOverlay`;
- `platform.core.sync.Hydrate`, `Reconcile`, `Materialise`;
- `platform.core.licensing.LicensePolicy`, `LicenseGate`,
  `DependencyInventory`.

## ADR impact

- `adr/0001-separate-core-and-integration-skill-ownership.md`
  remains accepted and unaffected. This change respects its
  decision by keeping the harness core skills and the agent skill
  packaging produced in Phase 7 clearly separated.
- New `adr/0002-canonical-runtime-separation.md` formalises the
  invariants #1-#3 and #5-#8 from §68.
- New `adr/0003-license-governance-default.md` formalises §4
  preferred/review/deny policy and the SBOM requirement.
- New `adr/0004-ports-and-adapters-extension-style.md` formalises
  the architectural style of §59 and prevents premature
  microservice splitting.

## Acceptance criteria

- [x] Relevant Wiki pages reflect planned/shipped implementation.
  All updates above are additive and link back to the v0.8
  architecture baseline.
- [ ] Generated local context index was refreshed. After the Wiki
  edits, `python harness.py wiki-init` MUST be re-run by the
  operator (Phase 1 task 43 records the same command for the Phase 1
  implementation change; this change records it as a manual
  operator action item — not a verification pass performed by this
  change).
- [x] Links and stable knowledge IDs validate. The new Wiki
  pages use stable `id` frontmatter values (see Knowledge to
  create above) so that `kb_validate` succeeds.
- [x] Spec/implementation mismatches are resolved or explicitly
  documented. There is no implementation in this change; the
  accepted specs in this change describe the planned platform
  behaviour against the v0.8 baseline, with no conflict.