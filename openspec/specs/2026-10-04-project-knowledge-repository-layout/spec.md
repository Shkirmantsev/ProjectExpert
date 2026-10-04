# project-knowledge-repository-layout Specification

## Purpose
Define the canonical on-disk layout that the platform product code uses
inside a target project repository, so that durable Git-versioned
knowledge, runtime working knowledge, optional dynamic ingestion, and
distribution artifacts have predictable, documented locations.

## Requirements

### Requirement: canonical knowledge directory layout

The platform MUST recognize and create (when missing) the following
canonical knowledge directory tree inside a target project repository
when the platform is bound to that repository:

```text
project-knowledge/
├── wiki/        # OKF-bundled durable human-readable knowledge
├── graph/       # sharded knowledge graph (nodes/, edges/)
├── chunks/      # contextualized chunk shards
├── sources/     # canonical source snapshots
├── objects/     # content-addressed immutable objects
├── manifests/   # per-family manifests (graph, chunks, sources, schema)
└── project-context.yaml
```

The directory tree MUST live at the root of the target project or at a
configured `projectKnowledgeRoot` path. The directory MUST always be
Git-versioned because the canonical knowledge is the durable source of
truth (invariant #1 of the v0.8 architecture and §7.1 "Portable,
Git-versioned and human-inspectable"). There is no ephemeral canonical
mode.

#### Scenario: bound project without project-knowledge/

Given a target project repository that has no `project-knowledge/`
directory
When the platform starts up against that repository
Then the platform creates `project-knowledge/` with the six documented
subdirectories (`wiki/`, `graph/`, `chunks/`, `sources/`, `objects/`,
`manifests/`) and an initial `project-knowledge/project-context.yaml`
file
And the operation completes without overwriting any existing files.

#### Scenario: bound project with existing project-knowledge/

Given a target project repository that already has a `project-knowledge/`
directory with content
When the platform starts up against that repository
Then the platform reads the existing layout and does not recreate or
overwrite subdirectories or manifests
And the startup reports the existing layout as the binding layout.

### Requirement: runtime working knowledge cache location

The runtime working knowledge store (database, vector index, full-text
index, graph index, embeddings cache, model cache, working-tree
overlay) MUST live under a separate, Git-ignored directory at:

```text
.project-intelligence-cache/
├── runtime.db
├── vector-index/
├── fts/
├── graph-index/
├── embeddings/
└── model-cache/
```

The default cache root MUST be configurable via
`runtimeCacheRoot` in `project-context.yaml` and MUST be added to the
target project's `.gitignore` if it is not already present.

#### Scenario: default cache location

Given a target project repository bound to the platform with no custom
`runtimeCacheRoot` configured
When the platform first writes runtime working knowledge
Then the cache is created under `.project-intelligence-cache/` at the
repository root
And the cache directory is added to `.gitignore` if absent.

#### Scenario: custom cache location

Given a target project with `project-context.yaml` setting
`runtimeCacheRoot: .pi-cache`
When the platform writes runtime working knowledge
Then the cache is created under `.pi-cache/` instead of the default
And `.pi-cache/**` is added to the project's `.gitignore` if absent.

### Requirement: local dynamic source inbox location

The platform MUST recognize the directory
`tmp/local/source/` as a recursive dynamic ingestion inbox when present
at the target project root.

The directory MUST be added to the target project's `.gitignore` by
default so that local-only material is never committed unintentionally.

The inbox MAY contain arbitrary nested subdirectories such as
`requirements/`, `customer/`, `protocols/`,
`confluence-export/`, `diagrams/`, `jar-docs/`.

#### Scenario: local source inbox auto-gitignore

Given a target project without an explicit `.gitignore` entry for
`tmp/local/`
When the platform binds to that project
Then `.gitignore` is updated to contain `tmp/local/**`
And the platform does not commit or materialise any file under
`tmp/local/source/` without an explicit source promotion policy.

### Requirement: distribution artifacts directory

The platform MUST use `distribution/` as the canonical location for
generated integration artifacts (skills, Codex/Claude/OpenCode
plugin bundles, generic agent bundles).

The directory tree is scaffolded by the Phase 1 implementation as
an empty tree under `distribution/{licenses,skills,codex,claude-
code,opencode,generic-agent,sbom}/`. It is populated by the license
governance module in Phase 1 (`distribution/licenses/` and
`distribution/sbom/`) and by the plugin generation pipeline in
Phase 6 (`distribution/skills/`, `distribution/codex/`,
`distribution/claude-code/`, `distribution/opencode/`,
`distribution/generic-agent/`). The platform MUST NOT write
integration bundles outside `distribution/` by default.

#### Scenario: plugin generation output location

Given the platform plugin generation pipeline is run with no explicit
output override
Then it writes the Codex bundle to `distribution/codex/`,
the Claude Code bundle to `distribution/claude-code/`, the OpenCode
package to `distribution/opencode/`, and the generic agent bundle to
`distribution/generic-agent/`.

### Requirement: project-context.yaml root configuration

The platform MUST read its project-level configuration from
`project-knowledge/project-context.yaml` (or a path configured by the
operator). The file MUST be valid YAML and MUST be parsable in a single
pass without external dependencies.

The configuration MUST support at minimum the following top-level keys
with documented defaults:

```yaml
projectKnowledgeRoot: project-knowledge   # canonical knowledge root
runtimeCacheRoot: .project-intelligence-cache  # runtime cache root
localInbox: tmp/local/source              # local dynamic inbox
okfVersion: "0.2"                         # OKF profile version
knowledgeSchemaVersion: "0.1.0"            # internal knowledge schema version
embeddingModelVersion: "unknown"            # populated once an embedding is bound
indexSchemaVersion: "0.1.0"               # runtime index schema version

licensing:                                # license governance (§4, see license-governance spec)
  mode: strict
  allow:
    - Apache-2.0
    - MIT
    - BSD-2-Clause
    - BSD-3-Clause
    - ISC
  review:
    - MPL-2.0
    - EPL-2.0
    - LGPL-2.1-only
    - LGPL-3.0-only
  denyPatterns:
    - "*-NC-*"
    - "research-only"
    - "non-commercial"
    - "source-available-restricted"

sources:                                  # source ingestion (§3, §8.2, §66)
  localInbox:
    path: tmp/local/source
    recursive: true
    defaultPolicy: LOCAL_ONLY
  externalDocumentation:
    path: external-documentation
    recursive: true
    defaultPolicy: SNAPSHOT
  confluence:
    enabled: false
  intranet:
    enabled: false
```

Unknown top-level keys MUST be ignored with a single warning, not
rejected. Unknown nested keys under `licensing` or `sources` MUST
produce an explicit error during hydrate so that misconfiguration cannot
silently degrade ingestion policy.

#### Scenario: project-context.yaml with defaults

Given `project-knowledge/project-context.yaml` containing only `okfVersion`
When the platform starts up
Then the platform uses the documented default values for all other keys
And reports a single warning for any keys that are present but unknown.

#### Scenario: project-context.yaml missing

Given a target project without `project-knowledge/project-context.yaml`
When the platform starts up
Then the platform creates the directory if needed and writes a default
`project-context.yaml` containing all the default keys above
And the startup succeeds without operator input.

#### Scenario: source policy overridden per-project

Given `project-knowledge/project-context.yaml` with
`sources.localInbox.defaultPolicy: SNAPSHOT`
When the inbox scanner runs
Then the default promotion policy for newly discovered sources is
`SNAPSHOT` rather than `LOCAL_ONLY`
And no other source-family behaviour changes.

### Requirement: distribution and runtime cache gitignore contract

The platform MUST guarantee that the following paths are excluded from
the target project's git tree:

```text
tmp/local/**
.project-intelligence-cache/**
```

The contract applies to the platform-managed `.gitignore` entries it
maintains for the target project; the platform MUST NOT delete
pre-existing user-managed `.gitignore` entries.

#### Scenario: platform updates gitignore safely

Given a target project `.gitignore` with user entries
When the platform binds and needs to ensure
`tmp/local/**` and `.project-intelligence-cache/**` are excluded
Then the platform appends only the missing entries and preserves all
existing entries verbatim.

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
