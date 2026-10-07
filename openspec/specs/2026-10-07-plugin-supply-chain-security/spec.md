# plugin-supply-chain-security Specification delta

## Purpose

TBD - created by archiving change implement-phase-6-agent-integration. Update Purpose after archive.

## Requirements


Covers architecture section §48 (Security and Trust for
Skills and Plugins) and §45 (Plugin Generation
Pipeline). The plugin supply-chain security gate is a
verification function the plugin packagers call before
emit. The gate enforces the §48 release controls and
keeps write / materialisation tools approval-controlled
even when a skill or plugin requests them.

The gate validates:

- pinned version;
- content hash;
- license;
- SBOM (when applicable);
- malware / secret scan;
- deterministic build where practical;
- signature support;
- source repository / provenance metadata;
- clear permissions;
- explicit network requirements;
- the absence of hidden auto-install.

A plugin MUST NOT silently weaken the core platform's
security policy. The gate is the canonical trust
boundary between canonical skill content and a vendor
plugin package.



### Requirement: gate validates pinned version

The plugin supply-chain security gate MUST require a
pinned version on every packaged artifact. The version
MUST be a valid semver; the gate MUST reject unversioned
or floating versions (`latest`, `*`, `main`).

#### Scenario: gate rejects unversioned plugins

Given a vendor plugin declares `version: latest`
When the gate runs
Then the gate raises a documented
`PluginVersionNotPinnedError`
And the packager does NOT emit the artifact.

### Requirement: gate validates content hash

The gate MUST validate canonical skill files against their source hashes and
generated vendor files against the deterministic build inventory of paths and
hashes. Vendor manifests need not be byte-identical across vendors. The gate
MUST reject artifacts whose content hash disagrees
with the canonical SHA-256.

#### Scenario: gate rejects mismatched content hash

Given a vendor plugin bundles a `SKILL.md` whose
SHA-256 disagrees with the canonical skill
When the gate runs
Then the gate raises a documented
`PluginContentHashMismatchError`
And the packager does NOT emit the artifact.

### Requirement: gate validates license

The gate MUST validate the license of every packaged
artifact. The license MUST be SPDX-tracked and MUST
pass `LicenseGate` for the documented allow-list (and
any recorded review-required mechanism). The gate MUST
reject artifacts whose license is not in the
documented allow-list.

#### Scenario: gate rejects unrecognised license

Given a vendor plugin declares `license: unknown`
When the gate runs
Then the gate raises a documented
`PluginLicenseUnknownError`
And the packager does NOT emit the artifact.

### Requirement: gate validates SBOM where applicable

The gate MUST validate the SBOM of every packaged
artifact. The SBOM MUST list every bundled dependency,
model weight, runtime and skill. The gate MUST reject
artifacts whose SBOM is missing required entries or
contains entries whose license is not SPDX-tracked.

#### Scenario: gate rejects missing SBOM entries

Given a vendor plugin omits a transitive dependency in
its SBOM
When the gate runs
Then the gate raises a documented
`PluginSBOMIncompleteError`
And the packager does NOT emit the artifact.

### Requirement: gate scans for malware and secrets

The gate MUST run a malware and secret scan over every
bundled file. The scan MUST reject artifacts that
include shell scripts that attempt to auto-install
unrelated software, network beacons to undisclosed
destinations, embedded credentials or hard-coded
secrets.

#### Scenario: gate rejects hidden auto-install

Given a vendor plugin bundles a shell script that
attempts to download and install a third-party package
When the gate runs
Then the gate raises a documented
`PluginHiddenAutoInstallError`
And the packager does NOT emit the artifact.

#### Scenario: gate rejects embedded secrets

Given a vendor plugin bundles a configuration file
that contains an AWS access key
When the gate runs
Then the gate raises a documented
`PluginSecretLeakError`
And the packager does NOT emit the artifact.

### Requirement: gate enforces deterministic build where practical

The gate MUST verify the packager is deterministic.
Two consecutive packager runs with the same canonical
sources MUST produce byte-identical artifacts. The
gate MUST reject packagers whose output diverges.

#### Scenario: gate rejects non-deterministic output

Given the packager produces different bytes for two
runs with the same canonical sources
When the gate runs
Then the gate raises a documented
`PluginBuildNotDeterministicError`
And the offending artifact is NOT emitted.

### Requirement: gate validates source provenance

The gate MUST validate the source repository and
provenance metadata of every packaged artifact. The
artifact MUST declare its canonical source repository
URL, its commit hash and its build identity.

#### Scenario: gate rejects missing provenance

Given a vendor plugin does not declare a source
repository URL
When the gate runs
Then the gate raises a documented
`PluginProvenanceMissingError`
And the packager does NOT emit the artifact.

### Requirement: gate enforces permissions and network requirements

The gate MUST validate the documented permissions and
network requirements of every packaged artifact. The
gate MUST reject artifacts that request permissions
inconsistent with their declared scope or that require
network access to undisclosed destinations.

#### Scenario: gate rejects over-broad permissions

Given a vendor plugin declares `permissions: ["*"]`
When the gate runs
Then the gate raises a documented
`PluginPermissionsOverbroadError`
And the packager does NOT emit the artifact.

### Requirement: gate keeps write tools approval-controlled

The gate MUST ensure write / materialisation tools
(`project.materialize_knowledge`,
`project.refresh_sources`) remain approval-controlled
even when a skill or plugin requests them. The gate
MUST NOT silently enable write tools based on a skill
declaration; the agent or operator MUST supply the
documented approval artefact.

#### Scenario: gate rejects write-tool bypass

Given a vendor skill or installer instructs the server to execute
`materialize_knowledge` without validated approval
When the gate runs
Then the gate raises a documented
`PluginWriteToolBypassError`
And the packager does NOT emit the artifact.

### Requirement: gate is invoked by every packager

The gate MUST be invoked by every plugin packager
(tasks 89-92) before emit. The packager MUST NOT emit
an artifact without the gate's `passed` verdict. The
gate MUST record the verdict in the artifact's
provenance metadata.

#### Scenario: gate runs before every emit

Given a packager runs
When the packager is about to emit an artifact
Then the packager invokes the gate
And the gate's verdict is recorded in the artifact's
provenance metadata.

### Requirement: signature support is documented

The gate MUST support optional artifact signature verification.
When the manifest declares a signature, the gate MUST
verify the signature against the configured trusted public key, not a key trusted solely because the artifact supplies it.
The gate MUST reject artifacts whose signature does
not verify.

#### Scenario: gate verifies signature

Given a vendor plugin declares a signature
When the gate runs
Then the gate verifies the signature against the
documented public key
And the gate rejects the artifact when the signature
fails verification.

### Requirement: generated vendor packages agree on shared release identity

The shared packaging build MUST reject disagreement across vendors on skill
package content hash, skill version, MCP API compatibility range, license,
server identity or required capabilities. Determinism MUST compare all output
paths and bytes under fixed build inputs, not only the SKILL.md hash. Failed
gates MUST prevent publication of a partial usable release.

#### Scenario: matching skill hash does not hide endpoint disagreement

Given two vendor bundles contain identical skill bytes but different server identities
When the shared release build runs
Then the build fails before publication with a documented agreement error.

## Phase 6 task coverage

The change covers Phase 6 task 94 (plugin supply-chain
security gate: pinned version, content hash, SBOM,
license / scan, source provenance, signature support,
no hidden auto-install, approval-gated materialise
tools). Tasks 89-92 (plugin packagers) invoke the gate
before emit.

Out of scope:

- the MCP server — Phase 6 task 85 (`mcp-server`);
- the canonical Agent Skill content — Phase 6 task 87
  (`agent-skill-canonical`);
- the version handshake — Phase 6 task 88
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
- the Wiki maintenance and archive — Phase 6 task 95
  (`phase-6-wiki-archive`);
- the Phase 8 enterprise security boundary — Phase 8
  tasks 105-110;
- A2A integration — Phase 10 tasks 119-123.