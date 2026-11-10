# Proposal

## Why

Cross-OS source bind mounts can dominate ingestion. Derived databases need local I/O without sacrificing canonical host durability.

## Goal

Add an explicitly selected managed workspace with automatic incremental import, fenced publication, canonical host write-through and verified host runtime checkpoints. Preserve bind deployment and inference selection.

## Affected capabilities

New managed-fast-workspace capability; additive integration with portable deployment and persisted runtime reconciliation.

## Compatibility / migration impact

New installs only. No installed deployment is modified. Auto remains bind until platform acceptance evidence warrants promotion. Structured local commits are explicitly authorized by the user. Branch switching and publishing are outside scope.

## Related knowledge

- .ai/wiki/architecture/portable-deployment.md
- External design: ProjectExpert-Cross-Platform-Fast-Workspace-Implementation-Design.md

Implementation and measured release boundaries: [verification](verification.md).
