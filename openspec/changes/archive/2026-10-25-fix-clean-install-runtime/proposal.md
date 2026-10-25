# Fix clean installation runtime reliability

## Why
External-repository installation reported refresh starvation, invalid MCP handshake and tool schemas, misleading status, unnecessary downloads, absent Java parsing, and difficult GPU startup. Current source already retries changed candidates; retain and extend that contract instead of removing stale-version protection.

## What changes
Repair MCP Streamable HTTP and schemas; cover stable-tree retry and generated artifacts; report published runtime status; default the deployment kit to checksum-pinned Q4 Qwen GGUF with lazy document assets; include Java parser; make GPU device selection and diagnostics explicit.

## Impact
Runtime monitor, MCP/HTTP, UI projections, deployment kit, production dependencies, and installation documentation. Native model aliases remain selectable. Physical GPU acceptance is separate from configuration tests.
