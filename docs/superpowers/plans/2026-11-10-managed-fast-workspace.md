# Managed Fast Workspace Implementation Plan

> Execution: subagent-driven-development for bounded helper implementation and independent reviews; remaining integration executed inline. User authorized implementation and subsequently requested structured local commits; no plan-approval pause is required.

**Goal:** Implement optional fast local source/runtime storage with durable host canonical writes and recoverable derived state.

**Architecture:** Native host helper batches verified source changes into a Linux volume. A shared importer/index lease guards publication; canonical knowledge is directly host bound. Runtime snapshots use coordinated online SQLite backup and verified export/restore.

**Tech Stack:** Go standard library, existing Python runtime, Docker CLI/Compose, Bash/PowerShell.

**Spec:** openspec/changes/add-managed-fast-workspace/specs/managed-fast-workspace/spec.md and design.md; supplied external design is reference.

## Global Constraints

- No changes to installed projects, remote publication or accelerator profile files. The user subsequently authorized structured local commits.
- No host Python/Go requirement; binaries built and packaged at release time.
- PI_WORKSPACE_MODE=auto|volume|bind; auto remains bind pending measured platform acceptance.
- Source/canonical/runtime/model ownership boundaries remain separate.
- No partial generation publication, raw live SQLite archive, privileged/socket helper or remote source transfer.

### Task 1: Portable transport and importer

Files: tools/workspace-agent/**, pi_platform/adapters/sync/**, tests/test_workspace_importer.py.
Interface: helper prepare|sync|supervise|stop|status --repo PATH --kit PATH. Writes workspace.env; schema-1 manifest tar; importer shares ProjectLock('commit', root=repo/'.projectexpert-workspace').
- [x] Test traversal, links, collision, corrupt/truncated archives, interruption/replay and complete-scan deletion.
- [x] Implement stable incremental native scanning, receiver-authoritative manifest, VCS bridge, Docker context identity and capped retry.
- [x] Verify Go tests and cross-build Windows/Linux; benchmark 30k mixed files and one-file update.

### Task 2: Deployment and lifecycle

Files: distribution/deployment/compose.workspace-volume.yaml, workspace.sh/ps1, compose.sh/ps1, stop.ps1, export.py, Containerfile and CI.
Consumes helper CLI/env; produces unchanged accelerator Compose topology with only production mounts changed.
- [x] Test rendered Compose CPU/CUDA/Vulkan/native Windows/gemma-torch retains sidecars, model mounts, devices and endpoints.
- [x] Integrate preflight/first import before Compose startup; supervise/stop safely; package checksummed helpers.
- [x] Verify existing launcher regressions and native syntax.

### Task 3: Runtime integration

Files: core/sync/workspace_sync_contract.py, version_monitor.py, core/git/version_identity.py, cli/main.py, UI additive status.
Consumes managed sentinel/applied-generation/importing state and commit.lock; produces exclusive full-pass lease and coherent generation status.
- [x] Test unavailable/importing/malformed state fails closed; source mutation cannot race publication.
- [x] Preserve ordinary bind identity; bridge managed Git/SVN/plain identity and canonical edits.
- [x] Verify lifecycle/bootstrap and retrieval regressions.

### Task 4: Runtime checkpoints and recovery

Files: core/runtime/runtime_checkpoint.py, adapters/runtime/runtime_checkpoint_export.py, checkpoint CLI and host export helper.
Consumes existing project writer lock and active snapshot/profile; produces schema/version/profile/checksum manifest and completed host backups.
- [x] Test online backup with WAL/writer, full artifact set, secret exclusion, corruption, interrupted export, retention and inactive restore.
- [x] Coordinate all SQLite snapshots and non-SQLite immutable files; bound bytes and durations.
- [x] Wire after-publication/periodic/stop paths and verify scheduler behavior.

### Task 5: Acceptance and documentation

Files: tests, docs/FAST_WORKSPACE.md, .ai/wiki ADR and architecture, OpenSpec tasks/evidence.
- [x] Review full diff and reconcile every mandatory external scenario against test or explicit platform limitation.
- [x] Run focused regression suites, harness and OpenSpec checks.
- [x] Record actual host/GPU performance evidence; leave Windows and unavailable hardware NOT TESTED and auto promotion disabled.

## Preflight review

| Tasks | Shared contract | Resolution |
|---|---|---|
| 1 / 2 | helper CLI + workspace.env | Explicit flags and env file, never execute dotenv as code |
| 1 / 3 | managed sentinel, generation, importing, commit.lock | Full-pass shared lease, durable intent before mutation |
| 3 / 4 | writer project lock + publication snapshot | Backup serializes with publication; no nested lock reacquisition |
| 2 / 4 | host completion and shutdown | Verify host snapshot before final rename; checkpoint before stop |
| Each | Tests vs behavior | Security/recovery contract tests and real platform evidence are separate gates |

Local implementation/verification is complete with the final harness gate passing. Native Windows, actual GPU and reboot/power-loss release acceptance remain open in the OpenSpec verification record; auto is not promoted.
