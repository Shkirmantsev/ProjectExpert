# 2026-10-11-okf-wiki-profile-distribution Specification

## Purpose
Turn the §10 Open Knowledge Format v0.2 compatibility profile into an enforced,
distributable behaviour: validate a Wiki bundle deterministically before any
durable commit, keep the internal knowledge model isolated from OKF revisions,
and ship the profile adapter with the platform instead of shipping project
knowledge.

## Requirements

### Requirement: Validation before durable commit

The materialisation pipeline MUST run deterministic OKF validation before any
durable commit. An invalid bundle MUST abort the commit and leave canonical
knowledge unchanged.

#### Scenario: invalid bundle aborts materialisation

Given a Wiki page without parseable frontmatter
When materialisation runs OKF validation
Then the commit is rejected and no canonical file is changed.

#### Scenario: valid bundle is materialised

Given a conforming OKF v0.2 bundle
When materialisation runs OKF validation
Then the commit proceeds normally.

### Requirement: Declared OKF version at the bundle root

The bundle root MUST declare the targeted OKF version, and validation MUST
reject a bundle whose declared version is not supported by the running platform.

#### Scenario: unsupported declared version is rejected

Given a bundle root declaring an unsupported OKF version
When validation runs
Then validation fails with an explicit version error.

### Requirement: Mandatory concept type

Every non-reserved concept Markdown file MUST contain parseable YAML frontmatter
and a non-empty `type`. A file with a missing or empty `type` MUST fail
validation.

#### Scenario: missing type fails validation

Given a concept file whose frontmatter omits `type`
When validation runs
Then validation reports the missing mandatory `type`.

### Requirement: Reserved file semantics

Validation MUST preserve the OKF reserved semantics of `index.md` and `log.md`
and MUST NOT require a concept `type` for them.

#### Scenario: reserved files validate without a concept type

Given reserved `index.md` and `log.md` files without a `type`
When validation runs
Then both files validate without a concept-type error.

### Requirement: Platform extension fields

Platform-specific metadata MUST use the stable `pi_` prefix so that OKF readers
can ignore unknown fields, and validation MUST report a known platform
extension field that violates its expected shape.

#### Scenario: malformed platform extension field is reported

Given a platform extension field whose value is not a string
When validation runs
Then validation reports that specific field.

### Requirement: Runtime data is out of scope

Validation MUST reject runtime or binary artefacts found inside the OKF bundle,
because dense vectors, ANN indexes, runtime database pages and model caches are
derived state, not portable knowledge.

#### Scenario: runtime artefact inside the bundle is rejected

Given a binary index file inside the Wiki bundle
When validation runs
Then validation rejects it as non-portable runtime data.

### Requirement: Adapter isolates the domain model

The internal knowledge model MUST NOT be coupled to a specific OKF minor
version. All OKF translation MUST go through the OKF adapter.

#### Scenario: model does not embed OKF version rules

Given the internal knowledge model types
When they are inspected
Then no type hard-codes an OKF minor-version rule.

### Requirement: Runtime knowledge is not frozen into the image

The distribution image MUST ship the OKF profile adapter and a template bundle.
It MUST NOT ship project-specific Wiki content, because the mounted repository is
the source of truth.

#### Scenario: image ships the profile, not project knowledge

Given the built distribution image
When its bundled knowledge files are listed
Then it contains the OKF profile and template only, and no project Wiki pages.

### Requirement: Conformance gate is operator-callable

The platform MUST provide an operator-callable command that validates a Wiki
bundle against the configured OKF profile and reports a non-zero exit code on
failure.

#### Scenario: operator command reports failures

Given a bundle that fails validation
When the operator runs the OKF validation command
Then it prints the violations and exits non-zero.
