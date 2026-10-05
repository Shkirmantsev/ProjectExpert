---
id: modules.llm-port
title: Phase 5 local LLM port module map
kind: modules
status: active
summary: Phase 5 §35 LocalLLMPort — opt-in local LLM surface with a deterministic stub default that ships in the default container.
sourceRefs:
  - pi_platform/ports/orchestration/local_llm.py
  - pi_platform/core/orchestration/local_llm.py
  - pi_platform/adapters/orchestration/stub_local_llm.py
  - openspec/specs/2026-10-05-local-llm-port/spec.md
maintenance:
  mode: authored
related:
  - modules.orchestrator
  - interfaces.capability-discovery
---

# Phase 5 local LLM port modules

The §35 local LLM is the optional small companion the
Phase 5 `QueryOrchestrator` consumes for L1
contextualisation. The local LLM is NOT the main coding
/ architecture model; it is the small, commercially-
licensed, CPU-capable companion that performs the §35
sub-tasks (query classification, query rewriting,
contextualisation, entity / relation extraction, short
summarisation, lightweight reranking, context
compression, simple Q&A).

The default container ships with the deterministic stub
`StubLocalLLMAdapter`; opt-in LLM backends
(`llama-cpp`, `transformers`, `external-llm`) are
registered as additional adapters when the
corresponding Python package is installed AND
`project-context.yaml:orchestrator.local_llm.family` is
set to the family's name.

## Port (`pi_platform/ports/orchestration/local_llm.py`)

- `LocalLLMPort` — abstract base with the `complete`,
  `is_available`, `model_version`, `license_id`,
  `family` and `stats` operations.
- `LocalLLMError` — raised when the local LLM cannot
  satisfy a request.

## Core (`pi_platform/core/orchestration/local_llm.py`)

- `StubLocalLLMCore` — deterministic stdlib-only stub
  LLM port. `is_available() == False`,
  `complete(...)` returns `""`,
  `model_version() == "stub-1.0.0"`,
  `license_id() == "Apache-2.0"`,
  `family() == "stub"`. The stub ships under Apache-2.0
  with no new runtime dependency.

## Adapter (`pi_platform/adapters/orchestration/stub_local_llm.py`)

- `StubLocalLLMAdapter` — registry-friendly wrapper
  around `StubLocalLLMCore`. The default adapter
  selected by `llm-status`; satisfies the §35 default
  adapter scenario.

## Opt-in backends

The opt-in LLM backends land as additional adapters
when:

- the corresponding Python package is installed
  (`llama-cpp`, `transformers`); and
- `project-context.yaml:orchestrator.local_llm.family`
  is set to the family's name.

When a configured family is unavailable, the platform
falls back to the stub and reports
`is_available() == False`; the §47 capability descriptor
records `features.localLlm: false` accordingly.

## CLI surface

- `python -m pi_platform.cli llm-status` — reports the
  active backend, `is_available`, `family`, model
  version, license identifier, the opt-in family
  list and the configuration note.