# 2026-10-11-one-click-distribution Specification delta

Covers plan §23, §23.1, §24, §31.

## ADDED Requirements

### Requirement: minimal profile remains lightweight

The minimal profile MUST remain functional without
any optional dependencies (`documents`,
`semantic-embeddings`, `ann`, `reranking`,
`accelerator`, `multimodal`). The default container
MUST boot with only `pip install -e .` and the
hashing backend; the optional dependency groups
MUST NOT be required for a minimal deployment.

#### Scenario: minimal container boots without optional dependencies

Given a fresh `pip install -e .` install
When the operator starts the container with the
`minimal` profile
Then the platform boots successfully
And the hashing backend is the active embedding
backend
And the BM25-light fallback is the active reranker.

### Requirement: host accelerator is an optional deployment profile

The host-side embedding accelerator
(`accelerator/`) MUST be an optional deployment
profile, not a core requirement. The one-container
CPU path MUST remain the default. The accelerator
MUST expose a minimal HTTP API
(`GET /health`, `GET /v1/capabilities`,
`POST /v1/embeddings`) with an allow-listed model
registry, pinned model revisions, an ephemeral
bearer token stored outside Git, local / private
bind, request size limit, timeout, and concurrency
limit (plan §23.1). The accelerator MUST NOT
expose arbitrary model loading or command
execution.

#### Scenario: accelerator absent falls back to CPU

Given a deployment with no accelerator running
When the platform starts
Then the platform detects the missing accelerator
And falls back to the container CPU backend
And the active profile reports `fallback = true`
in Control Plane diagnostics.

### Requirement: optional dependency groups and model licensing

The platform MUST declare the optional dependency
groups `documents`, `semantic-embeddings`, `ann`,
`reranking`, `accelerator`, `multimodal` in
`pyproject.toml` and MUST record the pinned model
revisions in
`distribution/licenses/model-licenses.json`. Every
optional dependency and model MUST pass the
existing License Gate.

#### Scenario: optional dependencies are genuinely optional

Given a clean `pyproject.toml` install
When the operator runs `pip install -e .`
Then no optional dependency is installed
And the platform still boots.

#### Scenario: model revisions are license-recorded

Given a `semantic-cpu` profile with
`EmbeddingGemma 2` at revision `R1`
When the platform starts
Then `distribution/licenses/model-licenses.json`
records the model ID, revision, and license terms
And the License Gate accepts the entry.

## MODIFIED Requirements

None. The existing one-click-distribution
`Requirements` are extended additively; their
bodies are not rewritten.
