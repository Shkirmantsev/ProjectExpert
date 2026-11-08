# Design

## Current state

SkillDistributionPlane serves a canonical distribution/skills package through
proprietary versioned URIs. Embedded HTTP and CLI stdio share McpServer dispatch.
The container already copies the skill tree; no new service is needed. Its
legacy frontmatter parser flattens nested metadata and cannot supply SEP-2640
frontmatter faithfully.

## Proposed design

Add an immutable in-memory snapshot of bundled skill files, complete manifests,
and skill:// aliases in the existing distribution plane. Use safe YAML parsing
when installed and a strict mapping/string subset for the shipped frontmatter
without optional YAML. Never publish a partially parsed frontmatter. Reject
symlinks and unsafe paths, cap each skill at 512 files and 16 MiB. Return binary
resources as base64 rather than replacing invalid UTF-8 bytes.

Add skills/list and skills/get to the shared dispatcher; advertise the extension
without optional directoryRead. A single complete catalog page suffices for the
small bundled catalog; reject supplied cursors. Add server/discover and modern
metadata/result envelopes needed for discovery and resource consumption while
preserving legacy initialize. Keep tool dispatch and authorization boundaries.

## Affected modules / interfaces

pi_platform/mcp/skill_plane.py, pi_platform/mcp/server.py, CLI skill-root selection,
container smoke verification, distribution documentation and skill Wiki contract.

## Data / persistence / concurrency impact

Read-only process-local bundle snapshot; no target writes or credentials.
Restart loads a new bundle. Digests and served bytes share the same snapshot.

## Compatibility and migration

Preserve proprietary versioned URIs and existing initialization. Prefer the
installed platform's skill bundle over a target repository's similarly named
folder. No automatic host installation, approval bypass, or claim that clients
without native skill support activate skills automatically.

## Risks and rollback

Beta extension and host adoption vary. Retain resource-based manual fallback.
No SDK upgrade or optional directory method. Remove added discovery/aliases to
roll back; existing versioned resources and stored project state remain intact.
