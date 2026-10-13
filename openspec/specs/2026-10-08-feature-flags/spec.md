# feature-flags Specification delta

## Purpose

Expose the Feature Flag registry with the documented scope vocabulary and the documented lifecycle states.

## Requirements


### Requirement: Feature Flag registry exposes the documented scope vocabulary

The Feature Flag registry MUST expose the documented §59.15
scope vocabulary:

```text
machine
project
branch
user
deploymentProfile
```

Every flag MUST be scoped by at least one of the five
scopes. A flag with no scope MUST be rejected with the typed
`InvalidFeatureFlagScopeError`. The registry MUST resolve the
most specific scope in the documented order
(user > deploymentProfile > branch > project > machine).

#### Scenario: registry resolves the most specific scope

Given a flag is declared as `enabled` for the
`deploymentProfile="production"` scope
and `disabled` for the `machine` scope
When the operator queries the flag for
`deploymentProfile="production"` on that machine
Then the registry returns `enabled`.

#### Scenario: registry rejects a flag with no scope

Given a flag declaration omits the scope
When the registry attempts to register the flag
Then the registry raises `InvalidFeatureFlagScopeError`.

### Requirement: Feature Flag lifecycle states match the documented vocabulary

The Feature Flag registry MUST support the documented §59.15
lifecycle states: `disabled`, `enabled`, `experimental`,
`deprecated`. An illegal transition MUST raise the typed
`IllegalFeatureFlagTransitionError`. The documented
transition graph:

```text
disabled     -> enabled, experimental
enabled      -> disabled, deprecated
experimental -> enabled, disabled, deprecated
deprecated   -> disabled
```

The registry MUST treat `experimental` flags as
`disabled` by default unless the project explicitly enables
them; the registry MUST record an audit entry every time it
applies the default.

#### Scenario: experimental flag returns disabled by default

Given a flag is declared as `experimental` at the
`project` scope
and no override exists at a more specific scope
When the operator queries the flag
Then the registry returns `disabled`
And the registry records an audit entry with
`operation=flag.resolve`, `result=default_experimental_disabled`.

### Requirement: Git-versioned feature declarations and local overrides remain distinct

The Feature Flag registry MUST keep Git-versioned feature
declarations and local overrides in separate sources. The
registry MUST NOT mix Git-versioned and local override
sources when resolving a flag; the registry MUST record an
audit entry when a local override shadows a Git-versioned
declaration.

#### Scenario: local override shadows a Git-versioned declaration

Given a flag is declared as `enabled` in the
Git-versioned source
and `disabled` in the local override source
When the operator queries the flag
Then the registry returns `disabled`
And the registry records an audit entry with
`operation=flag.override_applied`, `result=allowed`.

### Requirement: Feature Flag registry serialise is byte-stable

The Feature Flag registry serialise MUST be byte-stable. Two
consecutive `serialise()` calls on the same registry
MUST return byte-identical JSON. The serialised form MUST
include every registered flag with its `id`, `version`,
`state`, `scope` and the resolved value for the current
context. The serialised form MUST NOT include resolved
secret values.

#### Scenario: serialise is byte-stable

Given the registry has registered three flags across two
scopes
When the operator invokes `serialise()` twice
Then the two returned JSON strings are byte-identical.
And neither string contains a resolved secret value.
