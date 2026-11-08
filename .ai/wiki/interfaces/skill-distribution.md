---
id: interfaces.skill-distribution
title: Skill distribution plane contract
kind: interfaces
status: active
summary: Phase 6 §38 distribution plane — exposes the canonical Agent Skill through the project-intelligence:// URI namespace; immutable, content-addressed, byte-identical for two consecutive reads.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#38
  - pi_platform/mcp/skill_plane.py
  - openspec/specs/2026-10-07-skill-distribution-plane/spec.md
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

## Skills extension (SEP-2640)

The embedded HTTP `/mcp` endpoint and CLI stdio dispatcher expose the bundled
`project-intelligence` workflow through `io.modelcontextprotocol/skills`.
`server/discover` and legacy `initialize` advertise resources, the extension
with no optional features, and instructions pointing to
`skill://project-intelligence/SKILL.md`. Discovery does not require a ready
retrieval index, a chat LLM, or a skill copy inside the target project. Installed
platform resources take precedence over a target's similarly named directory.

`skills/list` returns a single complete catalog page. `skills/get` accepts the
SKILL.md URI and returns the same entry directly, without a prior list. Entries
carry verbatim frontmatter including nested metadata and a complete resource
manifest of `{uri, digest: "sha256:<hex>", size}`. These responses use
`resultType: "complete"`, `ttlMs: 300000`, and `cacheScope: "public"`.
Unknown skill/file URIs and unissued cursors return `-32602`.

All files, including nested references and binary assets, are individually
readable using `resources/read`; binary content that cannot be represented as
UTF-8 uses base64 `blob`. Standard URIs are snapshotted with their bytes and
manifests at server construction, so concurrent file edits cannot make the
served content disagree with its manifest. Restart to pick up bundle changes.
The bundle rejects symlinks and limits each skill to 512 files / 16 MiB. The
shipped frontmatter works without PyYAML; additional YAML constructs require
the optional YAML adapter and are rejected rather than silently flattened.

`resources/list` also exposes these files as ordinary resources, with skill
name, description and Markdown MIME type. Legacy versioned URIs remain
available. The optional directoryRead feature is not advertised or implemented.

The client owns lazy loading, digest/size verification, origin scoping, and
activation approval. Resource reads never execute skill scripts or elevate
permissions. A client lacking native support may read the skill as ordinary
context, or use the existing vendor skill package when resource reads are not
exposed. Server support cannot make every client automatically activate skills.

Evidence: `tests/test_mcp_skills_extension.py`, HTTP/stdio integration in
`tests/test_oci_pipeline_and_standalone_container.py`, packaged-image checks in
`scripts/smoke_production_container.py`. This adds Skills/discovery wire support;
it is not a claim of full MCP protocol conformance certification or support in
every third-party client.
