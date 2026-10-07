---
id: interfaces.trusted-approval-boundary
title: Trusted approval boundary contract
kind: interfaces
status: active
summary: Phase 6 prerequisite 1 — HMAC-signed, scoped, time-bounded approval tokens for write / materialise operations; rejected DENY; typed ApprovalRejected.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#48
  - pi_platform/ports/__init__.py
  - pi_platform/core/sync/trusted_approval.py
  - pi_platform/core/sync/materialise.py
maintenance:
  mode: authored
related:
  - interfaces.mcp-tools
  - interfaces.plugin-supply-chain
---

# Trusted approval boundary contract

The trusted approval boundary is the gate every
write / materialise operation crosses before any
durable change. It replaces the prior stub
implementation that accepted any non-empty token.

## Token semantics

An `ApprovalRequest` carries:

- `action` ∈ `materialise`, `refresh_sources`, …
- `repo_root` (canonical path);
- `change_ids` (allowed change set);
- `issued_at` (unix seconds, default = now).

The boundary signs the token with HMAC-SHA-256 against
an operator key. The token binds action, repo, change
ids, issued-at, not-before and not-after.

## Verification

`verify()` enforces, in order:

1. token presence and HMAC authenticity;
2. action match;
3. repository match;
4. change-superset relation (`change_ids ⊆ grant.change_ids`);
5. validity window (`now ∈ [nbf, exp)`).

A violation raises `ApprovalRejected` with a typed
`reason` from the documented set
(`missing_token`, `policy_denied`, `forged_signature`,
`expired`, `not_yet_valid`, `wrong_action`,
`wrong_repository`, `change_superset_mismatch`,
`malformed_token`, `no_issuer_key`).

## DENY rejection

`deny_if_denied(policy, action)` is invoked BEFORE any
token work so the prior gap where DENY was silently
skipped is closed.

## Closed default

The default `MaterialiseService` constructor wires
`ClosedTrustedApprovalBoundary` — every token is
rejected. The platform fails closed until an operator
key is configured via `HmacTrustedApprovalBoundary(key=...)`
or the `PI_OPERATOR_APPROVAL_KEY` environment variable.