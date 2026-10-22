# 2026-10-18-production-runtime-configuration-resolver Specification

Covers plan §2, §19, §20, §61, §63 (PR 1 of §79).

## Purpose

Define how every user-facing entry point resolves into one runtime
configuration, how the three public startup profiles
(`production`, `minimal`, `development`) behave, and how the platform
reports component availability truthfully. A production run never
silently falls back to hashing and never presents a stub as available.

## Requirements

### Requirement: single configuration precedence chain

The platform SHALL resolve runtime configuration through exactly one
precedence chain: command-line argument, then environment variable, then
local runtime settings, then project context defaults, then built-in
default. Every entry point (CLI, environment, local settings file,
project configuration, web control plane, make wrapper, container
wrapper) MUST feed this same chain and MUST NOT keep separate resolution
logic.

#### Scenario: precedence chain resolves deterministically (verifies: single configuration precedence chain)

Given a command-line model argument, an environment model variable, a local settings value and a built-in default that all disagree
When the platform resolves the embedding model
Then the command-line value wins
And the same resolution order is applied to device, dense backend, cache location and document processing

### Requirement: documented selection variables

The platform MUST honour documented selection variables for the
embedding model, the execution device, the dense backend, the model
cache location and document processing enablement, and the effective
resolved values MUST be visible in logs and in the web control plane.

#### Scenario: effective configuration is visible (verifies: documented selection variables)

Given environment variables set a device and a model cache location
When the platform has resolved the runtime configuration
Then the log output and the web control plane show the effective values

### Requirement: local settings stay out of canonical knowledge

The platform MUST store the user's local model and device preference in
a Git-ignored runtime settings file under the runtime cache directory and
MUST NOT write that preference into canonical project knowledge by
default. Project configuration MAY declare allowed profiles,
a recommended project profile and policy constraints; environment and
local selection still win for execution.

#### Scenario: local preference does not touch Git knowledge (verifies: local settings stay out of canonical knowledge)

Given a user selects a different embedding model in local settings
When the preference is persisted
Then it is stored under the Git-ignored runtime cache settings file
And canonical project knowledge files are unchanged

### Requirement: three public startup profiles

The platform SHALL expose exactly three public startup profiles:
`production`, `minimal` and `development`. `production` is the default
and uses real semantic embeddings, the real native dense backend and
real document processing. `minimal` MUST be selected explicitly and
permits hashing embeddings and the flat dense backend for diagnostics.
`development` MAY add test doubles, fault injection and extra
diagnostics. The platform MUST NOT silently select `minimal`.

#### Scenario: minimal profile allows hashing when explicitly selected (verifies: three public startup profiles)

Given the operator explicitly selects the `minimal` startup profile
When the platform resolves the embedding backend
Then the hashing backend is permitted
And the capability report labels the run as minimal

#### Scenario: minimal is never selected silently (verifies: three public startup profiles)

Given no startup profile is specified anywhere in the precedence chain
When the platform resolves the startup profile
Then the resolved profile is `production`

### Requirement: no silent hashing fallback in production

In the `production` profile the platform MUST NOT substitute a hashing
embedding backend, a flat-memory dense stand-in, a synthetic document
adapter or any other stub when the selected production component is
unavailable. Startup MUST fail with a human-readable, actionable error
naming the selected model and the command that installs it.

#### Scenario: selected production model missing fails startup (verifies: no silent hashing fallback in production)

Given the startup profile is `production`
And the selected embedding model runtime is not installed
When the operator starts the platform
Then startup fails with an actionable error naming the selected
model and the missing runtime
And the error text names the command that pulls or installs the
model
And no hashing embedding backend is used as a fallback

### Requirement: truthful capability reporting

The platform MUST report every production-relevant component in exactly
one of the states real-and-available, real-and-not-installed, or
disabled, together with its model identifier, immutable revision,
output dimension and execution device where applicable. The platform
MUST NOT report a stub component as available.

#### Scenario: capability report never claims a stub (verifies: truthful capability reporting)

Given an embedding binding that is present in code but raises a not-bound error when used
When the platform renders the capability report
Then the binding is reported as real-and-not-installed or disabled
And no field claims it is available
