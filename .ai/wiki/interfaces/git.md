---
id: interfaces.git
title: Git interface reference
kind: interfaces
status: active
summary: Reference for the Git CLI adapter, version identity tuple and working-tree overlay implemented by Phase 1.
sourceRefs:
  - pi_platform/core/git/git_port.py
  - pi_platform/core/git/version_identity.py
  - pi_platform/core/git/working_tree_overlay.py
  - pi_platform/adapters/git/cli_adapter.py
  - openspec/specs/2026-10-04-git-version-aware-runtime/spec.md
maintenance:
  mode: authored
---

# Git interface reference

Implements the
[`git-version-aware-runtime`](../../../openspec/specs/2026-10-04-git-version-aware-runtime/spec.md)
spec.

## Git CLI adapter

`pi_platform.adapters.git.cli_adapter.GitCliAdapter` is the
default Phase 1 Git port. It uses the system `git` binary
exclusively; the documented minimum version contract is `>= 2.30`.

Methods:

- `head(repo_root) -> str` — returns the resolved HEAD commit SHA.
- `current_branch(repo_root) -> Optional[str]` — returns the
  current branch name (`None` on detached HEAD).
- `status(repo_root) -> Sequence[WorkingTreeChange]` — returns
  the `git status --porcelain=1 -z` parsed list.
- `lfs_pointer_for(repo_root, path) -> Optional[str]` — returns
  the OID of a Git LFS pointer when the file is LFS-managed,
  otherwise `None`.
- `version() -> tuple[int, ...]` — parses `git --version` and
  validates the minimum version contract.

`GitCliAdapter()` raises `GitPortError` when the `git` binary is
not in `PATH`.

## Version identity

`pi_platform.core.git.version_identity.compute_version_identity`
returns a `VersionIdentity` dataclass:

```python
@dataclass(frozen=True)
class VersionIdentity:
    gitHead: str
    workingTreeFingerprint: str
    knowledgeSchemaVersion: str
    embeddingModelVersion: str   # defaults to "unknown"
    indexSchemaVersion: str
```

Branch names MUST NOT appear in the identity tuple. The
working-tree fingerprint is the SHA-256 hex digest of the
canonical working-tree overlay.

## Working-tree overlay

`pi_platform.core.git.working_tree_overlay.compute_working_tree_overlay`
returns a deterministic JSON document:

```json
{
  "schemaVersion": "0.1.0",
  "changes": [
    {"path": "<repo-relative path>", "kind": "modified|added|deleted|untracked"}
  ]
}
```

The overlay is computed via the Git port; when the port is
unavailable the function returns an empty overlay rather than
failing so hydrate can proceed in test environments.

## Failure and recovery

- `GitPortError` propagates when the Git binary is missing or
  the version contract is violated; the CLI surfaces the error
  in JSON form and exits non-zero.
- The version identity is deterministic across two consecutive
  startup runs with no source changes in between.
- A branch switch triggers `reconcile_branch_switch` on the
  sync service rather than a full rebuild; the report lists
  reused shards and re-ingested shards.