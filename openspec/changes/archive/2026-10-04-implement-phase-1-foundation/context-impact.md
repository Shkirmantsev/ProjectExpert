# Context impact — implement-phase-1-foundation

## Knowledge to create

- `.ai/wiki/adr/0005-platform-source-language.md` — ADR for the
  choice of Python 3.11 as the Phase 1 platform source language.
  `kind: adr`, `status: accepted`.

## Knowledge to update

- `.ai/wiki/adr/0002-canonical-runtime-separation.md` — flip
  `status: proposed` → `status: accepted` (was proposed by the
  archived planning change).
- `.ai/wiki/adr/0003-license-governance-default.md` — flip
  `status: proposed` → `status: accepted`.
- `.ai/wiki/adr/0004-ports-and-adapters-extension-style.md` —
  flip `status: proposed` → `status: accepted`.
- `.ai/wiki/architecture/platform-overview.md` — replace the
  "planned" wording with concrete module paths that match the
  implemented `platform/` package; reference the concrete
  Python ports and adapters.
- `.ai/wiki/architecture/system-overview.md` — flip "planned"
  to "implemented" for the Phase 1 module map; reference the new
  Wiki module and interface pages.
- `.ai/wiki/glossary/platform.md` — add Phase-1-specific
  vocabulary (`KnowledgeState`, `PolicyDecision`,
  `ProjectLock`, `WriteAheadLog`, `LicensePolicy`,
  `LicenseGate`, `OkfAdapter`).
- `.ai/wiki/modules/platform-core.md` — new module reference
  describing the implemented `platform/` package.
- `.ai/wiki/interfaces/canonical.md` — new interface reference
  documenting `pi_platform.core.canonical` value types, content
  addressing and serialization.
- `.ai/wiki/interfaces/git.md` — new interface reference
  documenting `pi_platform.core.git` ports.
- `.ai/wiki/interfaces/sync.md` — new interface reference
  documenting `pi_platform.core.sync` ports.
- `.ai/wiki/interfaces/licensing.md` — new interface reference
  documenting `pi_platform.core.licensing` ports.
- `.ai/wiki/INDEX.md` — list the new module and interface pages.

## Knowledge to review for staleness

- `.ai/wiki/project/implementation-roadmap.md` — Phase 1 tasks
  13-44 are now resolved; update the task table to reflect the
  implemented foundation. Phases 2-10 entries remain "planned".
- `.ai/wiki/project/project-map.md` — verify that the listed
  `platform/`, `project-knowledge/`, `.project-intelligence-
  cache/`, `distribution/` directories are now present; flip
  the marker from "planned" to "implemented".

## Affected implementation

- `platform/` (new) — Phase 1 product Python package.
- `project-knowledge/` (new, scaffolded by
  `python -m pi_platform.cli init-project` for a target repo).
- `.project-intelligence-cache/` (new, gitignored).
- `distribution/{licenses,skills,codex,claude-code,opencode,
  generic-agent,sbom}/` (new).
- `Containerfile` (new).
- `docker-compose.yml` (new).
- `scripts/project-intelligence.sh`,
  `scripts/Start-ProjectIntelligence.ps1` (new launcher
  skeletons).
- `.ai/wiki/adr/0005-platform-source-language.md` (new).

## ADR impact

- `adr/0001-separate-core-and-integration-skill-ownership.md`
  remains accepted and unaffected.
- `adr/0002-canonical-runtime-separation.md`,
  `adr/0003-license-governance-default.md`,
  `adr/0004-ports-and-adapters-extension-style.md` flip to
  `status: accepted`.
- New `adr/0005-platform-source-language.md` is created at
  `status: accepted`.

## Acceptance criteria

- [ ] Wiki pages reflect the implemented foundation.
- [ ] Generated local context index has been refreshed by
  `python harness.py wiki-init`.
- [ ] Links and stable knowledge IDs validate via
  `python harness.py wiki-validate`.
- [ ] `python harness.py check` passes.
- [ ] `openspec validate implement-phase-1-foundation --type
  change` passes.
- [ ] Spec/implementation mismatches are resolved or
  documented.