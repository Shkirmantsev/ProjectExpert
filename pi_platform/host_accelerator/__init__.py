"""Host accelerator package (Change Package G).

Implements the optional host-side embedding accelerator
described in plan §23 and the
``openspec/.../specs/2026-10-04-one-click-distribution/spec.md``
delta. The accelerator is a separate process (outside the
default container) that exposes a small HTTP API
(``GET /health``, ``GET /v1/capabilities``,
``POST /v1/embeddings``) with a strict security contract:

- fixed inference operations only (no model loading, no
  command execution)
- model IDs from an explicit allow-list
- pinned model revisions
- ephemeral bearer token (rotatable, stored outside Git)
- local / private bind by default; wide binds require
  ``allow_wide_bind=True`` AND a private RFC1918 / RFC4193
  / loopback address
- request size limit
- per-request timeout
- concurrency limit
- JSONL audit log that records health / model identity but
  never payload contents

The package is organised as:

- :mod:`pi_platform.host_accelerator.port` — the abstract
  contract (port) and value types
- :mod:`pi_platform.host_accelerator.config` — runtime
  configuration
- :mod:`pi_platform.host_accelerator.security` — token
  store and model allow-list
- :mod:`pi_platform.host_accelerator.audit` — JSONL audit log
- :mod:`pi_platform.host_accelerator.bootstrap` — token /
  audit / allow-list file bootstrap
- :mod:`pi_platform.host_accelerator.server` — stdlib HTTP
  server implementation
- :mod:`pi_platform.adapters.retrieval.host_embedding_client`
  — the container-side HTTP client
"""
