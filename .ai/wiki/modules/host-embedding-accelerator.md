---
id: modules.host-embedding-accelerator
title: Host-side embedding accelerator service and client
kind: modules
status: active
summary: Optional host-side HTTP service (pi_platform/host_accelerator/) with loopback bind, ephemeral bearer token, pinned model allow-list, payload-redacted JSONL audit log, and container-side HostEmbeddingClient with automatic CPU fallback.
sourceRefs:
  - pi_platform/host_accelerator/port.py
  - pi_platform/host_accelerator/config.py
  - pi_platform/host_accelerator/security.py
  - pi_platform/host_accelerator/audit.py
  - pi_platform/host_accelerator/bootstrap.py
  - pi_platform/host_accelerator/server.py
  - pi_platform/adapters/retrieval/host_embedding_client.py
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-11-one-click-distribution/spec.md
maintenance:
  mode: authored
related:
  - architecture.embedding-profile-identity
  - interfaces.embedding-profile
  - modules.embeddings
  - modules.security
---

# Host-side embedding accelerator service and client

Change Package G adds an optional host-side HTTP service (`pi_platform/host_accelerator/`) and container-side client (`pi_platform/adapters/retrieval/host_embedding_client.py`) so GPU-capable hosts can accelerate embedding generation while keeping the single-container CPU path as the default.

## Endpoints and security contract

- `GET /health` — liveness probe.
- `GET /v1/capabilities` — bearer-authenticated device, memory, and allow-listed model report.
- `POST /v1/embeddings` — bearer-authenticated embedding endpoint restricted to `ModelAllowList` (pinned `EmbeddingProfile` identities only).
- **Security controls**: loopback bind (`127.0.0.1`) by default; private bind requires `ACCELERATOR_ALLOW_WIDE_BIND=1`; public IP binds are unconditionally rejected. Ephemeral token (`secrets.token_urlsafe(32)`, mode `0o600`) verified via `hmac.compare_digest`. `AuditLog` records request metadata (`timestamp`, `request_id`, `endpoint`, `model_id`, `embedding_profile_hash`, `status`, `duration_ms`) and never logs payload text or vectors.
- **CPU fallback**: `HostEmbeddingClient` falls back cleanly to the container-side CPU `EmbeddingModelPort` whenever the accelerator is absent, unreachable, or times out.

[EmbeddingProfile identity](../architecture/embedding-profile-identity.md) ·
[Security module](security.md)
