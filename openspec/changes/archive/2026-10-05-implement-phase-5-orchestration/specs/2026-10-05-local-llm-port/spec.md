# local-llm-port Specification delta

Covers architecture section §35 (Small Local LLM) and the §5.4
model-license inventory contract. The `LocalLLMPort` exposes
a pluggable local LLM surface that the Phase 5
`QueryOrchestrator` consumes for L1 contextualisation when
the capability is available; the port is opt-in and the
default container ships without a model binding.

The `LocalLLMPort` is NOT the main coding / architecture model.
It is the small, commercially-licensed, CPU-capable companion
that performs the §35 sub-tasks (query classification, query
rewriting, contextualisation, entity / relation extraction,
short summarisation, lightweight reranking, context
compression, simple Q&A).

## ADDED Requirements

### Requirement: LocalLLMPort contract

The platform MUST expose a `LocalLLMPort` abstract class in
`pi_platform/ports/orchestration/local_llm.py` with the
following operations:

- `complete(prompt: str, *, max_tokens: int = 256,
  temperature: float = 0.0) -> str` — return a deterministic
  completion for a prompt; `temperature=0.0` is the default
  per the §35 determinism requirement;
- `is_available() -> bool` — return `True` when the
  underlying LLM runtime is registered and the model weights
  are present, `False` otherwise. The default container
  returns `False`;
- `model_version() -> str` — return the opaque model-version
  string the platform records for capability discovery;
- `license_id() -> str` — return the SPDX identifier of the
  LLM model and runtime (see §5.4 model-license inventory);
- `family() -> str` — return the LLM family
  (`"stub"`, `"llama-cpp"`, `"transformers"`, ...);
- `stats() -> Mapping[str, int]` — operational counters
  including `calls`, `errors`, `tokens_in`, `tokens_out`.

#### Scenario: default container exposes no LLM

Given the default container without a local LLM runtime
When the orchestrator initialises
Then `LocalLLMPort.is_available()` returns `False`
And the orchestrator falls back to L0 / L2 escalation only
And `CapabilityDescriptor.features.localLlm == False`.

#### Scenario: LLM completion is bounded

Given an available `LocalLLMPort`
When `complete(prompt, max_tokens=256)` runs
Then the returned string length does not exceed
`max_tokens * 4` characters (the documented 4-character-per-
token upper bound)
And the completion is finite (no `None`, no exception
escape).

### Requirement: deterministic LLM behaviour

The default `LocalLLMPort` adapter MUST run on a CPU-only
machine without a dedicated GPU. The active model family
MUST be selected through
`project-context.yaml:orchestrator.local_llm.family`
configuration. When the configured family is not available
the platform MUST fall back to a deterministic stub adapter
that returns an empty completion and reports
`is_available() == False`.

#### Scenario: LLM default adapter is the stub

Given a host without a local LLM runtime (or with the
`orchestrator.local_llm.family` set to `"stub"`)
When the platform initialises the `LocalLLMPort`
Then the stub adapter registers
And `is_available() == False`
And `complete("anything")` returns `""`.

#### Scenario: configured family registers when present

Given the `llama-cpp` Python package is installed
AND `orchestrator.local_llm.family == "llama-cpp"`
When the platform initialises the `LocalLLMPort`
Then the llama-cpp adapter is registered
And `is_available() == True`
And `model_version()` returns the model id
And `license_id()` returns the SPDX identifier.

### Requirement: CPU-capable deployment

The default `LocalLLMPort` adapter (the stub) MUST be
executable on a commodity CPU-only machine. Opt-in adapters
(llama-cpp, transformers) MAY require a GPU; the
`CapabilityDescriptor` reports the actual capability set per
deployment.

#### Scenario: stub starts on CPU-only hardware

Given a host without a GPU
When the platform initialises
Then the stub `LocalLLMPort` registers successfully
And `is_available() == False`.

### Requirement: commercially-usable license

The opt-in `LocalLLMPort` adapter MUST use a model and
runtime whose license satisfies the §5.1 preferred license
policy OR the §5.5 `LicenseGate` approval process for
review-required licenses. The model and runtime license
SPDX identifiers MUST appear in
`distribution/licenses/dependency-inventory.json` before the
adapter is registered. The default stub adapter ships
under `Apache-2.0`.

#### Scenario: LicenseGate blocks a non-commercial LLM

Given a proposed adapter whose `license_id()` returns a
license containing `Non-Commercial` or `Research Only`
When `LicenseGate` runs
Then the gate fails with a clear message
And the adapter is NOT registered.

#### Scenario: stub adapter is registered without review

Given the default stub `LocalLLMPort`
When `LicenseGate` runs
Then the gate passes (`Apache-2.0` is on the allow list)
And the stub is registered as the default.

### Requirement: orchestrator skips the LLM when unavailable

The `QueryOrchestrator` MUST skip the L1 LLM step when
`LocalLLMPort.is_available() == False`. The orchestrator
MUST NOT raise an error; it MUST escalate to L2 when L1
cannot produce a completion.

#### Scenario: L1 skipped when LLM unavailable

Given `LocalLLMPort.is_available() == False`
When the orchestrator processes an L1 query
Then `result.level` is `2`
And `result.llm_completion is None`
And `result.task_context is not None`.

### Requirement: bounded LLM usage

The `LocalLLMPort.complete` call MUST be bounded by
`max_tokens`. The orchestrator MUST pass a bounded
`max_tokens` value so the LLM cannot monopolise the agent
budget. The `stats()["tokens_out"]` counter MUST report the
approximate token count of the returned completion.

#### Scenario: bounded tokens

Given a prompt of 1000 characters
When `complete(prompt, max_tokens=128)` runs
Then the returned string length does not exceed
`128 * 4 = 512` characters
And `stats()["tokens_out"]` reports the bounded value.

## Phase 5 task coverage

The change covers Phase 5 task 80 (LocalLLMPort behind a
stable interface; do not bind a specific model in the default
container; declare the local-LLM capability as optional in
capability discovery). Task 79 (QueryOrchestrator) consumes
the port for the L1 step.

Out of scope:

- the QueryOrchestrator implementation — Phase 5 task 79
  (`query-orchestrator`);
- the TaskContextBuilder implementation — Phase 5 task 81
  (`task-context-builder`);
- the CapabilityDiscovery implementation — Phase 5 task 82
  (`capability-discovery`);
- the §83 retrieval-first policy regression test — Phase 5
  task 83 (`retrieval-first-policy`);
- the MCP server exposing the LLM port — Phase 6 task 85
  (`mcp-server`);
- the control plane, security, distribution, A2A — Phase 7+
  tasks 96-123.