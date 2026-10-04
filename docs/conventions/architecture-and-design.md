# Architecture and design conventions

- Describe current state from evidence before proposing change.
- Separate required behavior from implementation choice.
- Prefer dependency flow toward business/domain logic and keep framework/infrastructure at outer boundaries where practical.
- Do not perform broad architectural rewrites of brownfield systems without an explicit requirement.
- Cover data ownership, interfaces, transactions, concurrency, retries, idempotency, failure recovery, compatibility, observability, security, migration and rollback when relevant.
- Keep diagrams focused on the decision/flow being discussed.
- Durable cross-change decisions belong in ADRs; change-specific design belongs in the active OpenSpec change.
- Avoid introducing infrastructure or abstractions without a concrete problem they solve.
