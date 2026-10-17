# 2026-10-05-capability-discovery Specification delta

Covers plan §24, §32.

## ADDED Requirements

### Requirement: profile and execution introspection

The `CapabilityDiscoveryPort` MUST expose the active
deployment profile, the model IDs and revisions of
every bound embedding and reranker adapter, the
active device (CPU / GPU / accelerator), the RAM /
VRAM capability result, the fallback state, the
embedding index compatibility
(`embedding_profile_hash`), and the reranker status.

The introspection MUST be available to the Control
Plane diagnostics and to the MCP `retrieve_context`
tool output.

#### Scenario: Control Plane exposes the active profile

Given a `semantic-cpu` profile with
`EmbeddingGemma 2 / dim 512 / normalize: true`
When an operator opens Control Plane diagnostics
Then the panel shows the active profile, the
embedding model ID and revision, the device, the
RAM / VRAM capability result, the fallback state,
the index compatibility, and the reranker status.

#### Scenario: MCP retrieve_context output includes profile metadata

Given the same active profile
When an MCP client calls `retrieve_context`
Then the tool output includes the active profile,
the model ID, the device, the index compatibility,
and the reranker status.

## MODIFIED Requirements

None. The existing capability-discovery
`Requirements` are extended additively; their
bodies are not rewritten.
