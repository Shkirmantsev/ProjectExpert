# Context impact

## Knowledge to create

- Managed fast workspace operating guide and ADR covering ownership, fencing and recovery.

## Knowledge to update

- .ai/wiki/architecture/portable-deployment.md
- .ai/wiki/INDEX.md
- docs/README.md

## Knowledge to review for staleness

- Deployment ownership and persisted runtime reconciliation contracts.

## Affected implementation

Modules/paths: distribution/deployment, tools/workspace-agent, pi_platform/core/sync, pi_platform/adapters/sync, pi_platform/adapters/runtime, CLI bootstrap and additive status.

Primary symbols/interfaces: WorkspaceSyncFence, RuntimeCheckpointService, read_project_version, _bootstrap_and_index_target.

## ADR impact

- Add managed workspace ownership/publication decision; keep original inference decisions.

## Acceptance criteria

- [x] Wiki and operator documentation describe observed behavior and limitations.
- [x] OpenSpec and harness validation pass.
- [x] Platform matrix distinguishes PASS, FAIL and NOT TESTED.
