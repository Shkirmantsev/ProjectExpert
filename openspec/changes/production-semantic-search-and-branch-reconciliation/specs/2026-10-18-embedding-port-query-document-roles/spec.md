# embedding-port-query-document-roles Specification delta

Covers plan §7, §8, §11 (PR 2 of §79).

## Purpose

Define the role-aware embedding contract that replaces the text-only
embedding surface: every embedding call carries an explicit role
(query or document) and a retrieval task, optional title metadata
travels with the request, and exactly one underlying semantic contract
serves all callers. The profile descriptor gains an instruction version
that participates in profile identity so prompt-policy changes cannot
silently reuse incompatible vectors.

## ADDED Requirements

### Requirement: explicit role on every embedding call

The platform SHALL require every embedding request to carry an explicit
role of query or document and MUST reject requests without a role
instead of assuming a default. All callers, including retrieval,
indexing, evaluation and diagnostics, MUST declare the role explicitly.

#### Scenario: request without role is rejected (verifies: explicit role on every embedding call)

Given an embedding request that omits the role field
When the platform processes the request
Then the request is rejected with a clear error
And no vector is produced

#### Scenario: query and document roles produce different vectors (verifies: explicit role on every embedding call)

Given a deterministic test backend
When the platform encodes the same text with query role and with document role
Then the two vectors differ

### Requirement: retrieval task is part of the request

The platform MUST let each embedding request declare a retrieval task
of search, code retrieval or question answering, defaulting to search,
and MUST let the request carry an optional document title. The task and
title MUST influence encoding according to the selected model's policy.

#### Scenario: task influences encoding (verifies: retrieval task is part of the request)

Given a deterministic test backend
When the platform encodes the same text with search task and with code retrieval task
Then the two vectors differ

### Requirement: one underlying semantic contract

The platform MUST expose exactly one underlying embedding semantic
contract. Convenience entry points for query or document embedding MAY
exist, but they MUST delegate to that single contract and MUST NOT
introduce divergent formatting behaviour.

#### Scenario: convenience entry points agree with the contract (verifies: one underlying semantic contract)

Given a query convenience entry point and the underlying contract
When the platform encodes the same request through both
Then the resulting vectors are identical

### Requirement: model prompt policy stays in adapters

The platform MUST keep model-specific prompt syntax inside each model
binding. The retrieval pipeline and its callers MUST NOT construct
model-specific prompts.

#### Scenario: pipeline never formats model prompts (verifies: model prompt policy stays in adapters)

Given a retrieval query processed through the pipeline with any bound model
When the encoding completes
Then the pipeline passed role, task and text to the binding
And the pipeline did not add model-specific prompt text

### Requirement: deterministic test backend honours roles

The hashing embedding backend used for tests and the minimal profile
MUST remain deterministic and MUST produce role-dependent,
task-dependent output so that role misuse is detectable in tests.

#### Scenario: deterministic backend produces role-dependent output (verifies: deterministic test backend honours roles)

Given a deterministic hashing embedding backend configured for the
minimal profile
When the platform encodes the same text with query role and with
document role
Then the two vectors differ
And encoding with different retrieval tasks also produces different
vectors
And the difference is observable in unit tests without any model
weights

### Requirement: instruction version participates in profile identity

The platform MUST include a profile instruction version in the
embedding profile identity, and a change to that version MUST change the
identity so that vectors produced under an older instruction policy are
never mixed with new ones.

#### Scenario: instruction version change isolates vectors (verifies: instruction version participates in profile identity)

Given an embedding profile with instruction version v1 and stored vectors
When the profile instruction version changes to v2
Then the computed profile identity differs from the v1 identity
And v1 vectors are not inserted into the v2 namespace
