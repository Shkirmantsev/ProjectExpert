---
name: architecture-design
description: Design or review production architecture with explicit boundaries, trade-offs, compatibility, failure modes, operational concerns, ADR impact, and verification.
---

# Architecture design

1. Ground the design in current requirements, implementation, constraints, and relevant ADR/Wiki evidence.
2. State boundaries, responsibilities, data ownership, interfaces, runtime flows, failure/recovery semantics, security and operability.
3. Compare alternatives and trade-offs; do not add infrastructure without a concrete requirement.
4. For behavior changes, integrate with the active OpenSpec design/context-impact artifacts.
5. Record durable decisions as ADRs and update affected architecture Wiki pages.
6. Define verification and migration/rollback where applicable.
