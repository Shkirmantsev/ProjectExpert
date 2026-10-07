---
id: interfaces.skill-distribution
title: Skill distribution plane contract
kind: interfaces
status: active
summary: Phase 6 §38 distribution plane — exposes the canonical Agent Skill through the project-intelligence:// URI namespace; immutable, content-addressed, byte-identical for two consecutive reads.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#38
  - pi_platform/mcp/skill_plane.py
  - openspec/specs/2026-10-05-skill-distribution-plane/spec.md
maintenance:
  mode: authored
related:
  - interfaces.mcp-tools
  - interfaces.agent-skill
---

# Skill distribution plane contract

The distribution plane exposes the canonical Agent Skill
package through the documented URI namespace:

- `project-intelligence://distribution/manifest`
- `project-intelligence://skills/index`
- `project-intelligence://skills/<name>/<version>/SKILL.md`
- `project-intelligence://skills/<name>/<version>/references/...`
- `project-intelligence://skills/<name>/<version>/assets/...`

## Manifest

The manifest carries:

- `platformVersion`, `mcpApiVersion`,
  `knowledgeSchemaVersion`;
- `distributionSchemaVersion` (an identifier, not semver);
- the canonical skill `{name, version, sha256}`;
- `okf.supported` profile identifier set;
- `agentAdapters` mapping vendor → adapter version.

The manifest serialisation is byte-stable; two
consecutive reads return identical bytes.

## Resources

Every skill resource is content-addressed; two
consecutive reads of the same URI return byte-identical
bytes for any pinned version. The plane refuses to
serve resources that escape the skill directory and
refuses symlinks.

## Skill version pinning

The plane cross-checks the requested version against
the version declared in the skill's frontmatter;
mismatched versions are rejected so a client cannot
read a different release than the one it pinned.