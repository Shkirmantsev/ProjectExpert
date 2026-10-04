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
