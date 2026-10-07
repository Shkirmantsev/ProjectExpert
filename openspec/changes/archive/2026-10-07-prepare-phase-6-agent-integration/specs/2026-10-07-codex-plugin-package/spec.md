# codex-plugin-package Specification delta

Covers architecture section §41 (Codex / ChatGPT Plugin
Distribution Profile) and §45 (Plugin Generation
Pipeline). The Codex / ChatGPT plugin packager emits a
portable OpenAI Agent Plugin package containing the
canonical Agent Skill and the MCP configuration. The
packager is generated, NOT maintained by hand; the
canonical sources are the Phase 6 skill
(`distribution/skills/project-intelligence/`) and the
Phase 6 MCP server capability descriptor.

The packager emits:

```text
dist/codex/
├── plugin.json
├── mcp.json
├── skills/
│   └── project-intelligence/
│       ├── SKILL.md
│       └── references/...
├── assets/
└── optional OpenAI-specific extension metadata
```

A compatibility fallback
`dist/codex/.codex-plugin/plugin.json` MAY also be
emitted for environments that still require the legacy
entry point.

## ADDED Requirements

### Requirement: codex-packager is generated, not maintained

The Codex / ChatGPT plugin package MUST be generated
by a code packager from the canonical sources. The
package MUST NOT be maintained by hand; the canonical
sources are the Phase 6 Agent Skill and the Phase 6 MCP
server capability descriptor. The packager MUST run as
part of the documented build pipeline.

#### Scenario: packager regenerates the bundle

Given the canonical Agent Skill at
`distribution/skills/project-intelligence/SKILL.md` is
updated
When the packager runs
Then `dist/codex/` is regenerated
And the bundled `SKILL.md` is byte-identical to the
canonical `SKILL.md`.

#### Scenario: packager fails on skill / MCP mismatch

Given the canonical skill declares an `mcp-api` range
that does not intersect the MCP server's
`mcpApiVersion`
When the packager runs
Then the packager raises a documented
`SkillMcpRangeMismatchError`
And no `dist/codex/` artifact is emitted.

### Requirement: codex plugin manifest schema

The Codex / ChatGPT plugin manifest MUST be emitted at
`dist/codex/plugin.json` and MUST declare the documented
fields. The packager MUST emit the manifest with every
documented key and MUST validate the manifest against
the documented JSON schema at packaging time. The
documented fields are:

- `name` — the canonical plugin name
  (`project-intelligence`);
- `version` — the semver plugin version, aligned with
  the canonical skill version;
- `mcp` — the MCP server endpoint (local stdio path
  or HTTP URL);
- `skill` — the bundled skill's name, version, SHA-256
  content hash and `mcp-api` semver range;
- `license` — the plugin license (Apache-2.0);
- `assets` — the list of bundled assets.

#### Scenario: plugin manifest carries the documented fields

Given the packager runs with the canonical skill at
version `1.4.0`
When the operator reads `dist/codex/plugin.json`
Then the manifest declares `name`,
`project-intelligence`, `version: 1.4.0`
And `skill.sha256` matches the canonical `SKILL.md`
content hash.

### Requirement: codex MCP configuration

The packager MUST emit `dist/codex/mcp.json` pointing
to the local or remote Project Intelligence MCP
endpoint. The MCP configuration MUST carry the
`mcpApiVersion` and the supported semver range.

#### Scenario: mcp.json points to the documented endpoint

Given the packager runs with the default
configuration
When the operator reads `dist/codex/mcp.json`
Then the file carries the `mcpApiVersion` and the
supported semver range
And the endpoint matches the documented transport (default
stdio, optional HTTP).

### Requirement: compatibility fallback

The packager MUST emit
`dist/codex/.codex-plugin/plugin.json` as a
compatibility fallback for environments that still
require the legacy entry point. The fallback MUST be
byte-equivalent to `dist/codex/plugin.json` modulo the
documented field name differences.

#### Scenario: compatibility fallback is emitted

Given the packager runs for a client profile requiring the legacy fallback
When the operator inspects `dist/codex/`
Then both `plugin.json` and
`.codex-plugin/plugin.json` are present
And the two manifests share the documented fields.

### Requirement: deterministic build

The packager MUST be deterministic. Two consecutive
runs with the same canonical sources MUST produce
byte-identical artifacts. The determinism MUST be
verified across the complete output file tree with fixed build inputs; the
`plugin.json` MUST include the skill SHA-256 so two
runs with identical complete release inputs produce the same
manifest. An unchanged skill hash alone does not establish output determinism.

#### Scenario: two runs produce identical artifacts

Given the canonical sources are unchanged
When the packager runs twice consecutively
Then the byte sequence of `dist/codex/plugin.json`,
`dist/codex/mcp.json`, the bundled `SKILL.md` and the
optional fallback are identical.

### Requirement: skill content hash is bundled

The plugin manifest MUST carry the canonical skill's
SHA-256 content hash. The hash MUST match the
canonical `distribution/skills/project-intelligence/
SKILL.md` content hash byte-for-byte.

#### Scenario: skill sha256 is byte-equal

Given the canonical `SKILL.md` has a known SHA-256
When the packager runs
Then `dist/codex/plugin.json` reports the same SHA-256
as the canonical file
And the bundled `SKILL.md` has the same SHA-256.

### Requirement: codex plugin smoke test

The packager MUST ship with a smoke test under
`tests/test_codex_plugin.py` that asserts:

- the bundled `SKILL.md` matches the canonical
  `SKILL.md`;
- the `plugin.json` carries the documented fields;
- the `mcp.json` carries the documented endpoint and
  semver range;
- the compatibility fallback is present for a legacy client profile;
- two consecutive packager runs produce byte-identical
  artifacts.

#### Scenario: smoke test passes

Given the packager runs
When the operator runs
`python -m unittest tests.test_codex_plugin -v`
Then the test reports `OK`
And the documented assertions hold.

## Phase 6 task coverage

The change covers Phase 6 task 89 (Codex / ChatGPT plugin
packager emitting `dist/codex/plugin.json`,
`dist/codex/mcp.json`, the bundled skill and assets, and
the `.codex-plugin/plugin.json` compatibility fallback,
with a smoke test). Task 94 (plugin supply-chain security
gate) is the verification function the packager calls
before emit.

Out of scope:

- the MCP server — Phase 6 task 85 (`mcp-server`);
- the canonical Agent Skill content — Phase 6 task 87
  (`agent-skill-canonical`);
- the version handshake — Phase 6 task 88
  (`version-compatibility-handshake`);
- the Claude Code plugin package — Phase 6 task 90
  (`claude-code-plugin-package`);
- the OpenCode plugin package — Phase 6 task 91
  (`opencode-plugin-package`);
- the generic agent bundle — Phase 6 task 92
  (`generic-agent-bundle`);
- the agent adapter contract — Phase 6 task 93
  (`agent-adapter-contract`);
- the plugin supply-chain security gate — Phase 6 task
  94 (`plugin-supply-chain-security`);
- the Wiki maintenance and archive — Phase 6 task 95
  (`phase-6-wiki-archive`);
- A2A integration — Phase 10 tasks 119-123.