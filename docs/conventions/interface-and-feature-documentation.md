# Interface and feature documentation

For new or materially changed behavior:

1. normative behavior/scenarios belong in OpenSpec when OpenSpec is used;
2. durable current-system explanation belongs in `.ai/wiki/`;
3. changed interfaces should have one stable Wiki page rather than duplicate descriptions.

A feature/module reference should cover purpose, entry points, main flow, data ownership, dependencies, interfaces, failure/retry semantics, configuration/operations, tests/evidence, risks and related Wiki/spec IDs as applicable.

An interface reference should cover owner, protocol/direction, endpoint/topic/contract identity, request/response/message shapes, validation, compatibility, errors/timeouts/retries/order/idempotency, security, producers/consumers, tests and source evidence.

The Wiki explains shipped/current behavior; it must not redefine approved requirements.
