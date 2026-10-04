# license-governance Specification

## Purpose
Ensure every bundled library, framework, model runtime, parser,
database component, plugin, hook, UI extension and agent adapter has
its license explicitly tracked, validated and gated so the platform
remains suitable for commercial use, redistribution and large-
enterprise deployment.

## Requirements

### Requirement: explicit license identification for every dependency

The platform MUST identify the license of every bundled dependency
and record the SPDX identifier in a generated dependency inventory.

A dependency is any library, framework, parser, runtime engine,
embedding model, reranker model, frontend bundle, plugin, hook package,
UI extension or agent adapter shipped or dynamically loaded by the
platform.

#### Scenario: dependency inventory is generated

Given a build of the platform
When the build runs
Then it emits a dependency inventory file under
`distribution/licenses/dependency-inventory.json`
And the file lists every dependency, its version, its SPDX
identifier and the declared license source.

#### Scenario: missing license fails the build

Given a build with one declared dependency whose SPDX identifier
cannot be determined
When the license gate runs
Then the build fails with a clear error naming the missing license
And no release artifact is produced.

### Requirement: preferred permissive license policy

By default, the platform MUST accept dependencies whose declared
license is one of the following permissive OSI-approved licenses:

- Apache-2.0 (preferred where practical because it includes an
  explicit patent grant);
- MIT;
- BSD-2-Clause;
- BSD-3-Clause;
- ISC.

The accepted set MUST be configurable through
`licensing.allow` in `project-knowledge/project-context.yaml`.

#### Scenario: MIT dependency passes the gate

Given a dependency with SPDX `MIT`
When the license gate runs against the default policy
Then the dependency passes and is recorded as `allow`.

#### Scenario: non-allowlisted permissive dependency is rejected

Given a dependency with SPDX `Zlib` and an empty
`licensing.allow` override
When the license gate runs
Then the dependency is rejected with a clear instruction to add the
license to `licensing.allow` if the operator intends to accept it.

### Requirement: review-required licenses must be explicitly accepted

Dependencies whose license carries reciprocal, file-level copyleft,
linking conditions or other distribution obligations MUST NOT be
introduced without operator acceptance. The platform MUST maintain a
`licensing.review` list whose initial entries include at least:

- MPL-2.0;
- EPL-2.0;
- LGPL-2.1-only;
- LGPL-3.0-only.

A dependency whose SPDX identifier is on the `licensing.review` list
MUST require an explicit operator acceptance token before being
bundled.

#### Scenario: LGPL dependency is held for review

Given a dependency with SPDX `LGPL-2.1-only` and no operator
acceptance token recorded
When the license gate runs
Then the dependency is held and the build waits for an acceptance
decision before continuing.

#### Scenario: LGPL dependency is accepted once

Given a previously rejected LGPL-2.1-only dependency and an
operator acceptance token recorded against its exact coordinate
identity (groupId, artifactId, version)
When the license gate runs again
Then the dependency passes for that coordinate identity only.

### Requirement: restricted and non-commercial licenses are denied by default

Dependencies whose terms prohibit or materially restrict commercial
use, redistribution, SaaS use, modification, use by companies or
resale MUST NOT enter the default dependency stack unless explicitly
approved by the operator. The platform MUST recognise as restricted at
least the patterns:

- `*-NC-*`;
- `research-only`;
- `non-commercial`;
- `source-available-restricted`.

#### Scenario: non-commercial license is denied

Given a dependency whose SPDX identifier matches `*-NC-*`
When the license gate runs
Then the dependency is denied and the build fails with a clear
explanation.

### Requirement: model licenses are tracked separately

The license of model weights, tokenizer, training artifacts,
inference runtime, embedding model and reranker MUST be tracked
separately from the underlying library licenses because they often
differ. The platform MUST emit a `distribution/licenses/model-
licenses.json` artefact listing every bundled model asset, its
source, its version and its license identifier.

#### Scenario: Apache-2.0 library with non-permissive weights is held

Given a Python library licensed `Apache-2.0` whose bundled model
weights are licensed under a non-permissive identifier
When the license gate runs
Then the library itself passes
And the model weights are tracked in `model-licenses.json`
And the platform refuses to ship the default build with those
weights bundled unless an operator acceptance token is recorded.

### Requirement: SBOM and NOTICE generation

The platform MUST generate a Software Bill of Materials (SBOM) and a
NOTICE file from the dependency inventory. The SBOM MUST use a
documented SBOM format (CycloneDX or SPDX) and MUST be emitted under
`distribution/sbom/`.

#### Scenario: SBOM is emitted for the default bundle

When the build completes successfully
Then `distribution/sbom/project-intelligence-platform.spdx.json` (or
equivalent) is present
And the SBOM lists every dependency with its version and SPDX
identifier.

### Requirement: CI license gate is blocking

The platform MUST integrate the license gate into the CI pipeline so
that a release artifact cannot be produced when the gate fails.

#### Scenario: license gate fails on introduced dependency

Given a CI build with a newly added dependency whose SPDX identifier
is unknown
When the CI license gate runs
Then the CI job fails with the offending dependency named
And no release artifact is uploaded.

### Requirement: dynamic plugins and hooks are license-checked before activation

The platform MUST verify the license identity and the compatibility
policy of every plugin, hook package, UI extension and agent adapter
before enabling it. A plugin MUST NOT be enabled until its license
identity is known and compatible with the active policy.

#### Scenario: plugin with unknown license stays disabled

Given a plugin with an unknown license
When the operator installs the plugin
Then the plugin is registered as `installed` but `blocked-by-policy`
And the platform refuses to enable it
And the control plane UI surfaces the blocking reason.

### Requirement: LicensePolicy contract

The Phase 1 implementation MUST provide
`pi_platform.core.licensing.policy.LicensePolicy` with an
`evaluate(dependency)` method that returns one of
`allow`, `review`, `deny` and an
`evaluate_all(dependencies)` method that returns the roll-up.

The policy MUST consume the documented allow/review lists and the
deny patterns from `project-knowledge/project-context.yaml`. When
the file is absent, the documented default lists apply:

- allow: `Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`,
  `ISC`;
- review: `MPL-2.0`, `EPL-2.0`, `LGPL-2.1-only`,
  `LGPL-3.0-only`;
- denyPatterns: `*-NC-*`, `research-only`, `non-commercial`,
  `source-available-restricted`.

#### Scenario: license policy evaluates MIT as allow

Given a `Dependency` with SPDX `MIT`
When `LicensePolicy.evaluate` is called
Then it returns `allow`.

#### Scenario: license policy evaluates LGPL-2.1 as review

Given a `Dependency` with SPDX `LGPL-2.1-only`
When `LicensePolicy.evaluate` is called with no operator acceptance
token
Then it returns `review`.

### Requirement: LicenseGate contract

The Phase 1 implementation MUST provide
`pi_platform.core.licensing.gate.LicenseGate` with a `run(...)`
method that returns `(passed: bool, findings: list[Finding])`.
The gate is build-blocking: a `False` return fails the CI license
gate step.

#### Scenario: gate fails on unknown SPDX

Given a `Dependency` with SPDX `UnknownLicense`
When `LicenseGate.run` is called
Then it returns `(False, ...)` with a `Finding` naming the
missing SPDX identifier.

#### Scenario: gate passes when allow-listed

Given a `Dependency` with SPDX `Apache-2.0`
When `LicenseGate.run` is called
Then it returns `(True, ...)` with a `Finding` recording `allow`.

### Requirement: DependencyInventory contract

The Phase 1 implementation MUST provide
`pi_platform.core.licensing.inventory.DependencyInventory` and
`ModelLicenseInventory`. The `DependencyInventory` loads
`distribution/licenses/dependency-inventory.json`; the
`ModelLicenseInventory` loads
`distribution/licenses/model-licenses.json` when present.

The stub inventory generated by `init-project` MUST list every
Python standard-library module dependency as `system` with SPDX
`NOASSERTION` and MUST NOT block the license gate because the
gate ignores `system` entries.

#### Scenario: stub inventory allows the build

Given a freshly initialised target repository
When `LicenseGate.run` is called
Then the gate passes with no findings
Because the stub inventory contains only `system` entries.

### Requirement: SBOM and NOTICE emitter

The Phase 1 implementation MUST provide
`pi_platform.core.licensing.sbom.emit_spdx_sbom` and
`emit_notice_file`. The SBOM MUST be SPDX-2.3-compatible JSON.
The NOTICE file MUST contain one line per `allow`-listed dependency
in the format `<name>:<version> - SPDX:<license-id> - <source>`.

#### Scenario: SBOM is emitted to the documented path

Given a dependency inventory with one Apache-2.0 entry
When `emit_spdx_sbom` is called with the documented output root
Then `distribution/sbom/PROJECT-INTELLIGENCE.sbom.json` exists
And contains the documented entry.

### Requirement: stub CI license gate target

The Phase 1 implementation MUST add a `make license-gate` target
that invokes `python -m pi_platform.cli license-gate --target <repo>`
and exits non-zero when the gate fails. The target is documented
as the Phase 1 CI gate; Phase 2 wires the inventory generator.

#### Scenario: license gate target exits non-zero

Given a target repository whose stub inventory declares one
dependency with SPDX `GPL-3.0-only` and no operator acceptance
token
When the operator runs `make license-gate TARGET=<repo>`
Then the command exits with a non-zero status
And the message names the offending dependency.
