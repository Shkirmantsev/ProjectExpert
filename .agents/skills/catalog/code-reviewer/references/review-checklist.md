# Review Checklist

Use the smallest subset that matches the artifact. Do not force every section into every review.

## Scope and Intent
- What artifact is under review: diff, file, folder, ADR, chart, Terraform module, Flux app, Makefile?
- What behavior or operational outcome is intended?
- What interfaces, consumers, environments, or upgrade paths must remain compatible?

## Correctness
- Are invariants, edge cases, and failure paths handled?
- Do docs, comments, examples, and tests match the actual behavior?
- Are ordering, reconciliation, idempotency, and retry assumptions explicit where they matter?

## Security
- Are secrets absent from code, values, examples, logs, and generated outputs?
- Are authn/authz boundaries enforced in the correct layer?
- Are inputs validated and dangerous shell, template, SQL, HTML, or command expansions controlled?
- Are defaults least-privilege and network exposure intentional?

## Compatibility and Actuality
- Does the approach still match current upstream guidance, APIs, provider behavior, or platform versions?
- Are deprecated APIs, stale patterns, or outdated examples being introduced?
- Do version constraints, API versions, and feature gates line up across the reviewed files?
- If the answer depends on current external behavior, did you verify it with primary sources?

## Maintainability and Consistency
- Do names, structure, and abstractions match intent?
- Are similar concepts represented consistently across code, docs, values, and automation?
- Is duplicated logic or configuration likely to drift?
- Are typos, inconsistent terminology, or misleading comments likely to confuse maintainers or operators?

## Operations and Reliability
- Are health checks, retries, timeouts, resource limits, lifecycle hooks, and rollback behavior sensible?
- Are observability, logging, and error messages useful without leaking sensitive data?
- Could this change create hidden drift, partial rollout failure, or unsafe destruction?

## Tests and Verification
- Do tests or validation steps cover risky behavior and failure modes?
- Is there a practical way to verify the change locally, in CI, or with plan/template/render output?
- Are missing tests acceptable, or do they leave the change under-validated?

## Artifact Prompts

### ADRs and Docs
- Is the status, date, and owner clear when relevant?
- Are alternatives and consequences documented honestly?
- Do commands, paths, versions, and examples still work?

### Helm and Kubernetes Config
- Do values map cleanly to templates?
- Are API versions, selectors, labels, probes, resources, and security contexts coherent?
- Are upgrade and override behaviors safe?

### Flux
- Are dependencies, ordering, health checks, prune behavior, and source references explicit?
- Could reconciliation produce destructive or confusing drift?

### Terraform
- Are version constraints and provider assumptions explicit?
- Could the change force replacement, drift, or unsafe lifecycle behavior?
- Are variables, outputs, and module contracts stable and documented?

### Makefiles and Scripts
- Are targets deterministic, discoverable, and safe by default?
- Do shell assumptions, environment handling, and error propagation behave as intended?
