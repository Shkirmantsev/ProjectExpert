---
id: interfaces-a2a
kind: interface
title: A2A interface
status: active
pi_phase: 10
pi_section: "§50"
pi_capability: a2a-adapter
---

# A2A interface

The A2A interface is the inbound surface of the Phase 10 A2A
adapter. It is the wire contract other agents use to call the
platform as a peer agent.

## Protocol surface

| Method | Path | Direction | Notes |
|---|---|---|---|
| `GET`  | `/.well-known/agent-card.json` | inbound | served when `a2a-inbound` is enabled |
| `POST` | `/a2a/v1/tasks:send` | inbound | JSON-RPC envelope documented below |
| `POST` | `/a2a/v1/tasks:send` (out) | outbound | reverse delegation through the official interfaces of external agents |

## Wire envelope

```json
{
  "wireVersion": "1",
  "taskId": "<id>",
  "sessionId": "<session>",
  "messages": [
    {"role": "user", "parts": [{"kind": "text", "text": "..."}]}
  ],
  "metadata": {}
}
```

The envelope is translated into the `A2aTask` value type at the
adapter boundary (`pi_platform.adapters.a2a.envelope`); the core
domain model never sees a JSON dict.

## Agent Card

The Agent Card is built from the capability discovery descriptor
plus a redactor that strips `secret://...` references. The card
exposes the platform name, version, supported protocols, skills
and capabilities. The `streaming` capability is `not-supported` for
v1.0.

## Capability handshake

The capability descriptor advertises the A2A surface through
`protocols.a2a` and the supported external agents through
`reverseDelegation.supportedAgents`. When `a2a-inbound` is
disabled, the `protocols.a2a` block is omitted and the Agent Card
returns 404.

## Failure mode translation

| Internal | HTTP |
|---|---|
| `A2aVersionIncompatible` | 410 |
| `A2aForbidden` (policy DENY) | 403 |
| `A2aUnauthorized` (missing capability) | 401 |
| `A2aLimitExceeded` | 429 |
| `A2aUnsupported` (flag off) | 404 |
| invalid envelope | 400 |

## Security composition

Every request passes:

1. **Authentication** — bearer token when configured.
2. **Authorisation** — central policy engine, action `a2a.invoke`.
3. **Capability** — `mcp.invoke` or `a2a.invoke` is required.
4. **Egress** — outbound reverse delegations consult the egress
   classifier; an egress DENY blocks the call.
5. **Audit** — every decision writes one audit record.
6. **Redaction** — outgoing delegations run through the Phase 8
   `RedactionPipeline`.

## Related

- `kb://modules.a2a`
- `kb://modules.eval`
- `kb://interfaces.reverse-delegation`
- `openspec/specs/2026-10-12-a2a-adapter/spec.md`
