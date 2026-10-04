# git-version-aware-runtime Specification

## Purpose
Define how the platform identifies the runtime project state, supports
branch switching, tag/history traversal, uncommitted working-tree
overlays, and shares parsed/embedded work via content hashes.

## Requirements

### Requirement: runtime project version identity

The platform MUST compute a runtime project version identifier that is
a structured tuple of:

- `gitHead` — the resolved Git HEAD commit SHA;
- `workingTreeFingerprint` — a SHA-256 of the canonical serialization
  of the project's working-tree changes (untracked and modified
  files, with paths normalised);
- `knowledgeSchemaVersion` — the current internal knowledge schema
  version;
- `embeddingModelVersion` — the version of the bound embedding model;
- `indexSchemaVersion` — the version of the runtime index schema.

Branch names MUST NOT be used as part of the immutable version
identity; they are mutable pointers.

#### Scenario: version identity is reported on startup

Given a target project bound to the platform at HEAD `abc123` with a
modified README and `knowledgeSchemaVersion = "0.1.0"`
When the platform starts up
Then the platform reports a version id tuple with the resolved commit,
the working-tree fingerprint, the knowledge schema version, the
embedding model version and the index schema version
And the reported tuple is stable across two consecutive startup
runs with no source changes in between.

#### Scenario: branch name is not part of version identity

Given the same Git commit `abc123` reachable from branch `main` and
from branch `feature/x`
When the platform reports the version identity
Then both reports use the same `gitHead`
And branch names do not appear in the identity tuple.

### Requirement: Git-version-aware runtime kernel

The platform MUST support the following Git-state transitions without
losing or corrupting the runtime working knowledge:

- branch switch (including from a working-tree with uncommitted
  changes);
- tag checkout;
- detached-HEAD checkout to a historical commit;
- Git worktree mount per working tree;
- release-branch creation and merge.

After every Git-state transition the runtime working knowledge store
MUST be reconciled so that the effective runtime context equals:

```text
HEAD knowledge
      +
working-tree overlay
      =
effective runtime context
```

A branch switch MUST be an incremental reconciliation, not a full
rebuild, whenever the canonical manifests enable that.

#### Scenario: branch switch reuses unchanged cache

Given a runtime working knowledge store hydrated against `branchA`
When the operator switches to `branchB`, which differs from `branchA`
in 5 of 50k chunks
Then the platform reports the count of reused canonical shards and
the count of re-ingested shards in the reconcile report
And the reconcile report shows that only the 5 changed canonical
shards and any stale derived data are re-ingested.

#### Scenario: tag checkout at older commit

Given the canonical HEAD knowledge is at `1.1.0` and a tag `1.0.0`
points to an earlier commit
When the operator checks out `1.0.0`
Then the runtime working knowledge store is reconciled to the
`1.0.0` canonical state
And no data from the `1.1.0` working tree leaks into the new
effective context.

### Requirement: working-tree overlay

The platform MUST apply a working-tree overlay that captures the
uncommitted changes to the target project files (modified, added,
deleted, untracked) and incorporates them into the effective runtime
context.

The overlay MUST be derived deterministically: given the same working
tree state, the platform MUST produce the same overlay representation.

The overlay MUST NOT cause uncommitted changes to leak into durable
Git canonical knowledge without an explicit materialization step.

#### Scenario: working-tree change is observable in retrieval

Given an uncommitted edit to a Markdown document in the target
project
When the operator asks the platform for the relevant requirement
Then the retrieval answer reflects the edited text
And no Git commit is produced.

#### Scenario: working-tree overlay is not materialised automatically

Given uncommitted changes in the target project
When the platform rehydrates after a restart
Then the runtime working knowledge store contains the overlay
And no durable canonical files are modified
And no Git diff is produced in the target repository.

### Requirement: content-addressed processing reuse

Expensive derived information (parsed structure snapshots, chunks,
contextualised chunks, embeddings, deterministic summaries,
deterministic entity/relation extraction results) MUST be associated
with a SHA-256 content hash derived from the canonical serialization
of the input content.

Given identical content, the platform MUST reuse the cached derived
result rather than recompute it. The reuse MUST apply across Git
branches, across Git worktrees, and across repeated ingests of the
same source file in the same project.

#### Scenario: identical chunk body reuses derived result

Given a source file producing identical chunk `rawText` in two
separate project runs
When the platform ingests the second instance
Then the platform reports a cache hit for the derived result of that
content address in the ingest report
And no second derived-result computation is performed for that body.

#### Scenario: cross-branch reuse for derived results

Given two branches that share most source files byte-for-byte
When the platform hydrates the second branch
Then the platform reports a per-family reuse rate in the reconcile
report.

### Requirement: large-binary-source strategy

The platform MUST support Git LFS for genuinely large binary source
artifacts (PDF packages, binary requirement documents, archived
exports). Git LFS MUST NOT be required for the structured canonical
knowledge model.

The platform MUST detect LFS-managed files and record their content
hashes through the LFS pointer mechanism when ingesting them.

#### Scenario: LFS-managed PDF is ingested through its pointer

Given a target project with a Git LFS-managed PDF requirement file
When the platform ingests the source inbox
Then the platform uses the LFS pointer's OID as the content hash
And the platform does not require the binary blob to be readable to
register the source existence.

### Requirement: Git CLI adapter contract

The Phase 1 implementation MUST provide a
`pi_platform.adapters.git.cli_adapter.GitCliAdapter` class that uses
the system `git` binary exclusively (Phase 1 ships no libgit2
binding). The class MUST expose the methods `head`, `branch`,
`status`, `log_paths`, `lfs_pointer_for` and `working_tree_diff`.

The adapter MUST document and enforce a minimum `git` version
contract of `>= 2.30` (the `--no-pager`, `--format=%H`, and
`--raw` flags are mandatory).

#### Scenario: Git CLI adapter requires a real git binary

Given a system without the `git` executable in PATH
When `GitCliAdapter()` is instantiated
Then the adapter raises `GitPortError` with a clear message naming
the missing dependency.

### Requirement: VersionIdentityPort contract

The Phase 1 implementation MUST provide a
`pi_platform.core.git.version_identity.compute_version_identity(...)`
function that returns a dataclass with the fields `git_head`,
`working_tree_fingerprint`, `knowledge_schema_version`,
`embedding_model_version` and `index_schema_version`.

`embedding_model_version` MUST default to the literal string
`"unknown"` until Phase 4 binds an embedding model.

#### Scenario: version identity includes embedding-model-version unknown

Given a target repository bound to the platform with no embedding
model configured
When `compute_version_identity` is called
Then `embedding_model_version == "unknown"`.

#### Scenario: branch name does not appear in version identity

Given a target repository with HEAD `abc123` reachable from both
`main` and `feature/x`
When `compute_version_identity` is called from each branch
Then both calls return the same `git_head`
And the dataclass has no field whose name or value contains the
branch name.

### Requirement: WorkingTreeOverlayPort contract

The Phase 1 implementation MUST provide a
`pi_platform.core.git.working_tree_overlay.compute_working_tree_overlay(...)`
function that returns a deterministic JSON document describing
the modified, added, deleted and untracked paths under the target
repository root.

#### Scenario: overlay is deterministic across calls

Given an identical working-tree state produced by editing two
files and adding one file
When `compute_working_tree_overlay` is called twice
Then both calls return byte-identical overlay documents.

#### Scenario: overlay does not modify canonical files

Given uncommitted changes in the target repository
When `compute_working_tree_overlay` is called
Then no file under `project-knowledge/` is rewritten.

### Requirement: LFS pointer detection

The Phase 1 implementation MUST detect Git LFS-managed files via
the `git lfs ls-files --name-only` command (when LFS is available)
and treat the LFS pointer OID as the content hash for the source
artifact. When LFS is not configured, the implementation MUST
record the file's canonical content hash.

#### Scenario: LFS pointer is detected without downloading the blob

Given a target repository with one Git LFS-managed PDF requirement
file
When `GitCliAdapter.lfs_pointer_for(<path>)` is called
Then it returns the LFS pointer OID as a hex string
And it does not require the binary blob to be readable.
