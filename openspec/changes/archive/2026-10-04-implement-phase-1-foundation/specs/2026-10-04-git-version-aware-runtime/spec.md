# git-version-aware-runtime Specification delta (Phase 1 addendum)

This delta pins the concrete `platform/core/git/` ports and
adapters that the Phase 1 implementation delivers. The base
specification in
[`openspec/specs/2026-10-04-git-version-aware-runtime/spec.md`](../../../../specs/2026-10-04-git-version-aware-runtime/spec.md)
remains authoritative for the platform-level contract.

## ADDED Requirements

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