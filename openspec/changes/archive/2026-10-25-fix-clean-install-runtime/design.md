# Design

Keep the before/after content guard: edits during indexing must never publish mixed generations. Retry failures without requiring a subsequent edit, including explicit requests on unchanged trees. Exclude only known generated distribution/SBOM output, preserving unrelated distribution source documents.

Use stateless Streamable HTTP: POST returns JSON, accepted notifications return empty 202, GET returns 405 because server-initiated SSE is not supported. Negotiate supported protocol versions and publish standard serverInfo plus complete input schemas shared with SDK registration.

Status reads the published runtime and readiness identity, distinguishing canonical cache records from semantic chunks. Q4 artifact identity includes immutable revision and checksum and invalidates old vector namespaces. Deployment defaults select the GGUF CPU sidecar; GPU overrides select an explicit device. PDF assets load on demand. Preserve explicit native PyTorch configurations.

Verify with isolated external repositories, real HTTP clients, failure/retry tests, launcher matrix, dependency gates and harness checks. Do not claim physical GPU validation without execution.
