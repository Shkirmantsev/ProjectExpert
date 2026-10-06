# Design — implement-phase-6-agent-integration

The design lives in
[`openspec/changes/prepare-phase-6-agent-integration/design.md`](../../prepare-phase-6-agent-integration/design.md).
This file is the implementation-side reference; it
records the trade-off matrix, the per-packager
implementation notes and the risk register.

The thin reference covers:

- the Phase 6 module map;
- the port surfaces (McpServer, SkillDistributionPlane,
  VersionCompatibilityPolicy, AgentIntegrationAdapter,
  PluginPackager, PluginSupplyChainSecurityGate);
- the default adapter implementations;
- the 9-version-dimension matrix;
- the per-packager shape;
- the per-vendor entry points;
- the distribution manifest schema;
- the deterministic-build expectation;
- the plugin-supply-chain gate checks;
- the architecture decision trade-off matrix;
- the Phase 1-5 invariant impact;
- the risks and mitigations.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| MCP SDK version drift breaks the typed tool surface | Pin the `mcp==1.30.0` SDK; record the dependency in `distribution/licenses/dependency-inventory.json`; verify the FastMCP decorator contract through a smoke test. |
| Skill SHA-256 collision breaks determinism | The SHA-256 is the canonical content hash; the gate rejects mismatches. Two runs with the same skill content produce byte-identical artifacts. |
| Hidden auto-install in a third-party skill bypasses the gate | The gate scans every bundled file for shell-script auto-install patterns; the packager refuses to emit when a violation is detected. |
| Version-range syntax diverges between the MCP server and the plugin packagers | The handshake uses a single deterministic parser in `VersionCompatibilityPolicy`; the parser is the single source of truth. |
| OpenCode plugin adapter introduces a TypeScript / JavaScript runtime the default container does not carry | The runtime is opt-in; the implementation change confirms the SPDX-tracked entry in `distribution/licenses/dependency-inventory.json` before emitting the OpenCode package. |
| Phase 6 module map violates the canonical / runtime separation invariants | The MCP server is a thin adapter; it composes the Phase 3 stack and the Phase 4 / Phase 5 surface without introducing a new runtime store. The §17 ANN-vs-knowledge-graph separation is preserved. |
| Plugin distribution manifest schema drifts across vendors | The packagers share the manifest schema; the deterministic-build expectation enforces byte-identity across two runs. |
| `tools/mcp/project-context-mcp/` confusion with the platform's `pi_platform/mcp/` package | The Wiki documents the two MCP servers as separate deliverables; the implementation change ships the platform's `pi_platform/mcp/` package without modifying the harness-side MCP server. |