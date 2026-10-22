# one-command-production-ux Specification delta

Covers plan §15, §16, §17, §18, §55, §56, §57, §58, §59, §60, §73,
§84, §85, §86, §87, §99 (PR 11 of §79).

## Purpose

Define the user-facing production experience: one `start` command,
one `models` command group, a first-start wizard in the web UI, a
Makefile product surface, a Docker compose production profile, a
persistent model volume, a model-switch state machine and an
administrative runtime configuration API. The user MUST be able to
start the platform against a mounted target repository with one
command and one model choice; model switching MUST NOT require
re-cloning the repository or re-embedding unchanged content.

## ADDED Requirements

### Requirement: single `start` command

The platform MUST expose a `project-intelligence start` command that
accepts the target repository path, the selected embedding model
alias and the execution device. The command MUST handle
initialisation, model provisioning, hydration, reconciliation,
discovery, ingestion, embedding, index build and readiness
sequentially, starting the HTTP control plane early and exposing
bootstrap progress.

#### Scenario: a fresh user starts with one command (verifies: single `start` command)

Given an empty machine with Docker and network
And a target repository mounted at `/repo`
When the operator runs `make pi-up TARGET=/repo MODEL=gemma`
Then the platform starts the control plane within seconds
And the platform pulls the EmbeddingGemma 2 weights into the
persistent volume if absent
And the platform performs discovery, ingestion, embedding and index
build in the background
And the control plane reports bootstrap progress
And readiness becomes true after validation
And the operator can open the browser URL printed by the command

### Requirement: model command group

The platform MUST expose a `project-intelligence models` command
group with at minimum `list`, `status`, `pull <alias>`, `verify
<alias>` and `use <alias>` sub-commands. The default `start` flow
MUST NOT require the user to run any of them explicitly.

#### Scenario: models command group exposes the documented sub-commands (verifies: model command group)

Given the platform CLI is installed
When the operator runs `project-intelligence models --help`
Then the help output lists `list`, `status`, `pull`, `verify` and
`use` sub-commands
And the default `start` flow does not require invoking any of them
explicitly

### Requirement: first-start wizard

When the runtime cache has no model selection, the web control
plane MUST display a first-start wizard with the target repository
confirmation, the embedding model choice (EmbeddingGemma 2 or Qwen3
Embedding 0.6B), the execution device (auto, CPU, GPU) and the
document processing toggle. The wizard MUST end with a single
"initialise and build search index" action.

#### Scenario: first-start wizard offers two model choices (verifies: first-start wizard)

Given the runtime cache has no model selection
When the operator opens the web control plane root URL
Then a first-start wizard renders
And the wizard offers EmbeddingGemma 2 and Qwen3-Embedding-0.6B
And the wizard offers Auto, CPU and GPU device choices
And the wizard offers a Docling toggle
And a single action initiates initialisation and indexing

### Requirement: model switch UX

The platform MUST support switching the active embedding model at
runtime through the web control plane, an administrative API, the
CLI `models use` command or a documented Makefile target. The
switch MUST reuse the active Git version, MUST prepare the new
vector namespace, MUST build or reuse the new dense generation and
MUST atomically activate it. Canonical Git knowledge MUST NOT be
rewritten for a model switch.

#### Scenario: model switch reuses the Git version (verifies: model switch UX)

Given the platform is ready and serving on Gemma
When the operator runs `make pi-model MODEL=qwen`
Then the canonical Git knowledge is unchanged
And the platform prepares the Qwen vector namespace
And the platform reuses unchanged source and chunk knowledge
And the platform builds the Qwen dense generation
And the platform atomically activates Qwen
And the previous Gemma generation remains available for an immediate
switch back

### Requirement: Makefile product surface

The repository MUST expose a documented `pi-help` target and at
minimum `pi-up`, `pi-model`, `pi-status`, `pi-reindex`, `pi-doctor`
and `pi-down` Makefile targets. The product targets MUST NOT
require the user to understand internal index paths, profile hashes
or schema migrations.

#### Scenario: Makefile product surface lists the documented targets (verifies: Makefile product surface)

Given the repository Makefile is present
When the operator runs `make pi-help`
Then the help output lists at least `pi-up`, `pi-model`, `pi-status`,
`pi-reindex`, `pi-doctor` and `pi-down`
And each target runs without the operator needing to know index paths,
profile hashes or schema migrations

### Requirement: Docker compose production profile

The repository MUST ship a documented `production` Docker compose
profile that binds the control plane to `127.0.0.1` by default,
mounts a persistent named volume for the model cache and honours
the documented environment variables. The compose file MUST refuse
to start when a sensitive remote exposure is requested without an
explicit operator opt-in.

#### Scenario: production compose profile binds to localhost by default (verifies: Docker compose production profile)

Given the documented `production` Docker compose profile is present
When the operator runs `docker compose --profile production up`
without overriding the host binding
Then the control plane listens on `127.0.0.1`
And the model cache is mounted from a persistent named volume
And requesting a remote exposure without the documented opt-in env
var causes the compose project to refuse to start

### Requirement: HTTP starts before indexing

The control plane HTTP server MUST start before the bootstrap worker
completes. While readiness is false the control plane MUST report
the bootstrap status and MUST refuse retrieval with a structured
refreshing or not-ready result.

#### Scenario: control plane stays available during indexing (verifies: HTTP starts before indexing)

Given the platform has just been started
When the operator opens the control plane URL
Then the control plane returns a non-error response
And the response shows a not-ready or refreshing status
And retrieval endpoints return a structured refreshing result
And no stale branch data is served

### Requirement: offline model staging

The `models pull` command MUST support pre-staging the selected
model into the persistent cache so an operator can prepare an
offline environment. The OCI image MUST remain separate from the
model data.

#### Scenario: offline model staging works (verifies: offline model staging)

Given the operator runs `project-intelligence models pull qwen` on
a machine with network access
When the command finishes
Then the Qwen model weights are present in the persistent cache
And a subsequent run on an offline machine can build the index
without re-downloading the weights

### Requirement: administrative API

The platform MUST expose administrative endpoints
(`GET/PUT /api/v1/admin/retrieval`, `POST /api/v1/admin/models/pull`,
`POST /api/v1/admin/reindex`, `GET /api/v1/admin/jobs/<id>`) and
MUST require an administrator capability to invoke them. Ordinary
coding agents MUST NOT be allowed to switch models.

#### Scenario: ordinary agent cannot switch models (verifies: administrative API)

Given an ordinary coding agent capability
When the agent calls `PUT /api/v1/admin/retrieval` to switch models
Then the request is denied
And the response carries a structured authorisation error
