# agent-skill-canonical Specification delta

Covers architecture section §37 (Versioned Agent Skill
Distributed with the MCP Server) and §39 (Protocol and
Artifact Version Compatibility). The canonical Agent
Skill is the single source of truth for how compatible
agents use the platform's MCP server efficiently and
safely. The skill lives at
`distribution/skills/project-intelligence/SKILL.md` and
ships with progressive-disclosure references under
`references/`.

The skill is part of the public integration contract.
The skill MUST follow the Agent Skills open format and
MUST declare the documented metadata (`name`,
`description`, `license`, optional `compatibility`,
version and protocol metadata). The MCP server ships the
skill content verbatim to clients that consume the
`project-intelligence://skills/<name>/<version>/...`
URIs (task 86) and to vendor plugin packagers that
snapshot the skill at install time.

## ADDED Requirements

### Requirement: canonical Agent Skill package layout

The platform MUST ship the canonical Agent Skill at
`distribution/skills/project-intelligence/SKILL.md` with
the documented layout:

```text
distribution/skills/project-intelligence/
├── SKILL.md
├── references/
│   ├── MCP-TOOLS.md
│   ├── RETRIEVAL-POLICY.md
│   ├── VERSIONING.md
│   ├── OKF-PROFILE.md
│   └── SECURITY.md
├── scripts/      (optional)
│   └── doctor.*
└── assets/
    └── config-examples/
```

The primary `SKILL.md` MUST remain concise and MUST
rely on progressive disclosure. Detailed MCP tool
descriptions, examples and compatibility data MUST
belong to the referenced files rather than bloating the
base skill.

#### Scenario: skill layout matches §37

Given the canonical Agent Skill is shipped
When the operator inspects
`distribution/skills/project-intelligence/`
Then the layout matches the §37 package structure
And every documented `references/` file is present.

#### Scenario: SKILL.md stays concise

Given the canonical Agent SKILL.md is shipped
When the operator measures the size of `SKILL.md`
Then the file MUST be smaller than the documented soft
limit (≤ 8 KB) and MUST NOT duplicate content already
in `references/`.

### Requirement: SKILL.md metadata contract

The canonical `SKILL.md` MUST carry the documented
YAML frontmatter with the documented keys:

- `name` — the canonical skill name
  (`project-intelligence`);
- `description` — a one-paragraph description of when
  to use the skill;
- `license` — the skill license (Apache-2.0);
- `compatibility` — optional; documents the supported
  coding-agent version and the documented MCP API range;
- `metadata.author` — the skill author;
- `metadata.version` — the skill semver version;
- `metadata.mcp-api` — semver range the skill
  understands;
- `metadata.knowledge-schema` — semver range the skill
  understands;
- `metadata.okf-profile` — OKF profile the skill
  understands;
- `metadata.distribution-schema` — distribution schema
  version the skill understands.

All custom metadata values MUST remain strings for
Agent Skills portability.

#### Scenario: SKILL.md metadata matches the §37 example

Given the canonical Agent Skill is shipped
When the operator parses the YAML frontmatter of
`SKILL.md`
Then the documented keys are present
And skill/API/schema versions and ranges use the declared semantic syntax
And OKF/distribution identifiers use the declared identifier format
And author and other descriptive metadata remain strings, not semver values.

### Requirement: 10-step behaviour contract

The canonical Agent Skill MUST teach the documented
10-step behaviour contract to compatible coding agents:

1. Inspect project / version capabilities.
2. Prefer project MCP retrieval over broad repository
   scanning.
3. Use exact / symbol search when identifiers are
   known.
4. Use hybrid `retrieve_context` for semantic
   questions.
5. Follow requirement / spec / graph links instead of
   opening unrelated files.
6. Request bounded `TaskContext` for implementation
   tasks.
7. Open raw source only for selected evidence or when
   retrieval is insufficient.
8. Preserve version / security filters.
9. Cite provenance returned by the server.
10. Materialize durable knowledge only through explicit
    approved workflow.

The skill MUST teach the contract in the documented
order; it MUST NOT add additional steps to the contract
that contradict the §33 retrieval-first escalation
policy.

#### Scenario: SKILL.md teaches the 10 steps

Given the canonical Agent Skill is shipped
When the operator reads the `SKILL.md` body
Then the 10 documented behaviour steps are enumerated
in order
And the order matches the §37 / §33 escalation order.

### Requirement: when-not-to-use guidance

The canonical Agent Skill MUST define when a coding
agent should NOT use a specific MCP tool. The guidance
MUST cover at least: do not use `project.refresh_sources`
or `project.materialize_knowledge` without an explicit
approval artefact; do not use raw-source tools before
retrieval; do not use `project.search` for exact-identifier
queries when an exact-lookup tool would answer.

#### Scenario: SKILL.md defines when-not-to-use guidance

Given the canonical Agent Skill is shipped
When the operator reads the `SKILL.md` body
Then a "When not to use" section is present
And the documented anti-patterns are listed.

### Requirement: stale and conflicting knowledge handling

The canonical Agent Skill MUST teach agents how to
react to stale or conflicting knowledge returned by the
MCP server. The guidance MUST distinguish the four
documented states from §54 (verified, inferred,
assumption, conflicting, stale, unknown), MUST cite
the Phase 3 `KnowledgeState` enum and MUST teach
agents to surface conflicts to the operator rather
than silently picking one side.

#### Scenario: SKILL.md references the KnowledgeState vocabulary

Given the canonical Agent Skill is shipped
When the operator reads the `SKILL.md` body
Then the §54 knowledge states are listed
And the documented stale-handling guidance is present.

### Requirement: incompatible version handling

The canonical Agent Skill MUST teach agents how to
react to a `VersionIncompatibleError` from the MCP
server. The guidance MUST teach agents to read the
`describe_capabilities` response, fall back to the
documented compatible range and surface the upgrade
instructions to the operator.

#### Scenario: SKILL.md teaches version-mismatch handling

Given the canonical Agent Skill is shipped
When the operator reads the `SKILL.md` body
Then the version-mismatch handling section is present
And it references the §39 handshake semantics.

### Requirement: security policy bypass prevention

The canonical Agent Skill MUST teach agents how to
avoid bypassing the project security policy. The
guidance MUST cover at least: do not bypass the
`MaterialiseService` approval gate; do not skip the
`approval_id` requirement on
`project.materialize_knowledge`; do not weaken the
plugin supply-chain security gate.

#### Scenario: SKILL.md teaches security-policy respect

Given the canonical Agent Skill is shipped
When the operator reads the `SKILL.md` body
Then the security-policy section is present
And the documented anti-patterns are listed.

### Requirement: read vs write distinction

The canonical Agent Skill MUST teach agents how to
distinguish read-only retrieval from write /
materialisation actions. The guidance MUST enumerate
the read-only tools (`project.search`,
`project.retrieve_context`, `project.get_*`,
`project.find_*`, `project.trace_*`,
`project.find_references`) and the write / materialise
tools (`project.materialize_knowledge`,
`project.refresh_sources`).

#### Scenario: SKILL.md enumerates read vs write tools

Given the canonical Agent Skill is shipped
When the operator reads the `SKILL.md` body
Then the read-only tools are listed
And the write / materialise tools are listed with their
approval requirements.

### Requirement: progressive disclosure references

The canonical Agent Skill MUST ship the documented
five `references/` files: `MCP-TOOLS.md`,
`RETRIEVAL-POLICY.md`, `VERSIONING.md`,
`OKF-PROFILE.md`, `SECURITY.md`. Each reference MUST
expand on the related section of the base skill.

#### Scenario: references directory matches §37

Given the canonical Agent Skill is shipped
When the operator inspects
`distribution/skills/project-intelligence/references/`
Then the five documented files are present
And each file's heading references the related
section of the base skill.

### Requirement: license declaration

The canonical Agent Skill MUST declare its license
as `Apache-2.0`. The license MUST be present in both
the YAML frontmatter and the `LICENSE` file (or
equivalent) at the skill root. The license MUST be
SPDX-tracked in
`distribution/licenses/dependency-inventory.json` if a
bundled model is part of the skill package.

#### Scenario: license declaration is consistent

Given the canonical Agent Skill is shipped
When the operator parses the YAML frontmatter
Then `license: Apache-2.0` is present
And a `LICENSE` file is present at the skill root.

### Requirement: skill version is semver

The canonical Agent Skill version MUST be a valid
semver string. The version MUST be exposed through the
distribution manifest (`skill.version`) and the
versioned URI namespace
(`project-intelligence://skills/<name>/<version>/...`).

#### Scenario: skill version is semver

Given the canonical Agent Skill is shipped
When the operator parses the YAML frontmatter
Then `metadata.version` is a valid semver string
And the manifest exposes the same version.

## Phase 6 task coverage

The change covers Phase 6 task 87 (canonical Agent Skill
at `distribution/skills/project-intelligence/SKILL.md`
per §37 with progressive disclosure). Task 86 (skill
distribution plane) exposes the skill through MCP
resources; task 88 (version handshake) validates the
skill's declared semver ranges against the server's
capabilities.

Out of scope:

- the MCP server wiring — Phase 6 task 85
  (`mcp-server`);
- the skill distribution plane — Phase 6 task 86
  (`skill-distribution-plane`);
- the version-compatibility handshake — Phase 6 task 88
  (`version-compatibility-handshake`);
- the Codex / ChatGPT plugin package — Phase 6 task 89
  (`codex-plugin-package`);
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