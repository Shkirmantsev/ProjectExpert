# project-knowledge-repository-layout Specification delta (Phase 1 addendum)

This delta adds concrete observable behaviour for the
`project-knowledge-repository-layout` Phase 1 implementation in
`platform/cli/main.py` and `platform/core/sync/`. The base
specification in
[`openspec/specs/2026-10-04-project-knowledge-repository-layout/spec.md`](../../../../specs/2026-10-04-project-knowledge-repository-layout/spec.md)
remains authoritative for the platform-level contract.

## ADDED Requirements

### Requirement: Phase 1 `init-project` command

The platform MUST provide a CLI command `python -m pi_platform.cli
init-project --target <path>` that, when executed against a target
repository, performs all of the following actions atomically:

1. creates `project-knowledge/{wiki,graph,chunks,sources,objects,
   manifests}/` when missing;
2. writes a default `project-knowledge/project-context.yaml` when
   missing, using the documented defaults;
3. appends only the missing entries
   `tmp/local/**` and `.project-intelligence-cache/**` to the
   target's `.gitignore` while preserving every pre-existing
   user-managed entry verbatim;
4. writes a stub `distribution/licenses/dependency-inventory.json`
   listing the Python standard-library-only stub dependencies when
   missing;
5. writes a stub `distribution/sbom/PROJECT-INTELLIGENCE.sbom.json`
   matching the SPDX minimal SBOM shape when missing.

The command MUST be idempotent: a second invocation against the same
target MUST NOT overwrite user-edited files.

#### Scenario: idempotent init-project on fresh target

Given an empty target repository at `/tmp/proj-a`
When the operator runs `python -m pi_platform.cli init-project
--target /tmp/proj-a`
Then the command reports a single line per created path
And a second invocation reports zero changes.

#### Scenario: init-project preserves user gitignore

Given a target repository whose `.gitignore` already contains
`build/**`
When the operator runs `python -m pi_platform.cli init-project
--target /tmp/proj-b`
Then `.gitignore` still contains `build/**`
And it now also contains `tmp/local/**` and
`.project-intelligence-cache/**`.

### Requirement: per-target runtime cache root resolution

The `HydrateService`, `MaterialiseService`, `WriteAheadLog` and
`LicenseGate` MUST resolve the runtime cache root from the target
repository's `project-context.yaml`. If the file is absent the
services MUST use the documented fallback path
(`.project-intelligence-cache/`).

#### Scenario: cache root from project-context.yaml

Given a target repository with `runtimeCacheRoot: .pi-cache` in
`project-knowledge/project-context.yaml`
When the operator runs `python -m pi_platform.cli hydrate
--target /tmp/proj-c`
Then the runtime cache is read from and written to
`/tmp/proj-c/.pi-cache/`
And no path under `/tmp/proj-c/.project-intelligence-cache/` is
created or written.

### Requirement: distribution tree gitkeep scaffolding

The `init-project` command MUST create the empty
`distribution/{licenses,skills,codex,claude-code,opencode,
generic-agent,sbom}/` tree by writing a `.gitkeep` file in each
empty subdirectory so the directories survive checkout but the
artifacts that will be generated in later phases are not committed
prematurely.

#### Scenario: distribution tree is tracked but contains only gitkeep

Given a target repository after `init-project`
Then every `distribution/<subdir>/.gitkeep` file exists
And no other files under `distribution/` exist by default.