---
id: adr.0032-managed-fast-workspace
title: ADR 0032: Managed local workspace and runtime recovery
kind: adr
status: active
summary: Optional native-host source reconciliation into Linux volumes with direct canonical host writes and verified derived-runtime checkpoints; platform acceptance remains pending.
sourceRefs:
  - tools/workspace-agent/
  - distribution/deployment/compose.workspace-volume.yaml
  - pi_platform/core/sync/workspace_sync_contract.py
  - pi_platform/core/runtime/runtime_checkpoint.py
related:
  - architecture.portable-deployment
  - adr.0029-portable-model-runtime-and-oci-kit
maintenance:
  mode: authored
---

# ADR 0032: Managed local workspace and runtime recovery

- Status: proposed implementation decision; platform acceptance pending
- Date: 2026-11-10
- Change: [add-managed-fast-workspace](../../../openspec/changes/add-managed-fast-workspace/design.md)

## Context

Host repository bind mounts can make repeated small-file access expensive across
Windows/Linux VM boundaries. Host source and reviewed canonical knowledge must
remain recoverable independently of Docker-managed derived state. A fast mirror
must not let indexing publish mixed source generations or turn a live SQLite file
copy into an alleged consistent backup.

## Decision

Offer explicit `PI_WORKSPACE_MODE=volume`; public `auto` continues to select `bind`
pending measured platform gates. A checksummed standard-library Go helper runs on
the native host and sends verified batches to an application-image importer using
the pinned local Docker context. Production mounts source read-only, canonical
`project-knowledge/` directly from the host read/write, and a nested runtime volume
read/write. Existing model and accelerator topology remains unchanged.

Validate the complete manifest/archive before mutation, retain a durable importing
intent until reconciliation finishes, and share the importer/indexer lease across
the entire apply or publication pass. The read-only application descriptor uses
Linux flock on the same lease inode. Native notifications are hints; reconciliation
and periodic hash revalidation remain necessary. OS advisory lifecycle locks release
on death. Exclusion-policy changes affect the derived mirror, never host source.

Coordinate all included SQLite online backups and compatible immutable artifacts
with runtime publication. Verify the complete host snapshot before acknowledging
completion. Retain bounded verified snapshots outside the source repository;
exclude operator credentials, private settings and models. Explicit restore requires
stopped writers and selects a newly imported inactive runtime volume while preserving
the previous volume. It does not merge incompatible generations or alter canonical
host knowledge.

Ship helper cross-builds in the matching deployment kit; require no host Go/Python.
A checksum detects mismatch but does not establish a signed release identity. Default
supervision is session-only; per-user login registration is an explicit operator
command, never an automatic launcher side effect.

## Consequences and evidence

The extra storage copy trades local disk space and synchronization lag for Linux
filesystem locality. Long indexing can delay source synchronization. Host source
and canonical data remain authoritative, while credentials need their own backup.
Offline recovery needs a compatible image/kit and a verified snapshot; otherwise
operators rebuild derived state from retained source.

Portable topology and contract tests provide software evidence. Native Windows,
GPU execution, reboot/power-loss durability and measured speedup remain separate
acceptance gates. This ADR records the implemented direction under an active
change; it does not adopt proposed requirements into current OpenSpec specs.

See [operator setup and recovery](../../../docs/FAST_WORKSPACE.md) and
[implementation plan](../../../docs/superpowers/plans/2026-11-10-managed-fast-workspace.md).
