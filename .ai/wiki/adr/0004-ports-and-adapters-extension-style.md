---
id: adr.ports-and-adapters-extension-style
title: Hexagonal / ports-and-adapters + micro-kernel extension style
kind: adr
status: accepted
summary: Adopt the hexagonal/ports-and-adapters architecture combined with a micro-kernel plugin extension surface for the platform core.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md
maintenance:
  mode: authored
---

# Hexagonal / ports-and-adapters + micro-kernel extension style

## Context

The v0.8 architecture (§59) requires the platform to remain modular,
deployable as one container by default, and to support optional
extensions (plugins, hooks, source adapters, secret providers,
observability providers, UI extensions, agent adapters) without
coupling them to internal runtime tables. The architecture also
requires capability-based authorization, a central Policy Engine,
and stable extension APIs.

## Decision

The platform core will be organised as a hexagonal/ports-and-adapters
application: business logic depends on ports, adapter implementations
live in `platform/adapters/`. Optional capabilities are registered
through stable extension APIs
(`Plugin`, `FeatureProvider`, `HookProvider`, `SourceProvider`,
`SecretProvider`, `PolicyProvider`, `AgentAdapter`, `UiExtension`,
`ObservabilityProvider`, `Exporter`) and become a plugin only when
they have coherent capability, independent lifecycle/configuration
and meaningful enable/disable value.

The default deployable remains one process; one optional UI/runtime
sidecar is allowed. Microservice-style splitting is explicitly
rejected for the core.

## Alternatives considered

- Microservices-style splitting. Rejected because it would force the
  default deployment to require an orchestration stack and would
  duplicate authorization policy across services.
- A monolithic plugin loader that allows arbitrary code injection.
  Rejected because it removes the capability/permission layer and
  makes the platform's security policy unenforceable.
- A separate microservice per adapter (one for embeddings, one for
  graphs, etc.). Rejected because it does not match the documented
  "single modular deployable" goal.

## Consequences

- Phase 7 implements the registry, hooks, capabilities, secret
  provider and policy engine on top of this style.
- Phases 2/3/4/5/6/8/9/10 all add adapters behind ports rather than
  touching the core domain.
- The control plane and the data plane both call the same Policy
  Engine for authorization decisions.

## Verification

`openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md`
(`plan-v0-8-platform-architecture` change) includes Phase 7 tasks
96-103 (registry, hooks, policy engine, secret provider, audit,
feature flags, UI extension, regression tests) that exercise this
decision.