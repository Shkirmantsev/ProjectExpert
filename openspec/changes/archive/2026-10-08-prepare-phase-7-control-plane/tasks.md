# Tasks — prepare-phase-7-control-plane

This tasks file mirrors the Phase 7 tasks 96-104 from the
canonical
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md).
The tasks below are the future implementation work; they
will be executed by the future
`implement-phase-7-control-plane` change. This change ships
zero production code.

The eight Phase 7 capability specs under
[`specs/`](specs) are the authoritative behavioural
contract for the implementation work. The future change
implements and verifies these proposed deltas before
adoption. Tasks 96-104 remain unchecked until their
implementation and close-out are verified; preparation
completion alone does not adopt or implement these
requirements.

Verification commands referenced below:

- `python -m unittest tests.<module> -v` — focused
  regression tests;
- `openspec validate implement-phase-7-control-plane
  --type change --strict` (future change),
  `openspec validate --all --strict` (canonical harness
  check);
- `python harness.py check` — configuration / session,
  Wiki, OpenSpec, tests and artifact manifest gate; run
  `license-gate` separately;
- `python harness.py wiki-validate` — Wiki Markdown
  validation;
- `python scripts/artifact_manifest.py verify` — artifact
  manifest gate;
- `python -m pi_platform.cli license-gate` — license
  inventory gate;
- `PATH="$PWD/tmp/local/bin:$PATH" python3 harness.py
  check` and the GitHub CI jobs (unit ubuntu+windows
  3.11/3.13, full-linux, full-windows, codeql) MUST pass
  before push.

## Phase 7 — Control plane (preparation only)

### 7.1 — Feature / Plugin Registry (task 96)

- [ ] 96. Implement `FeatureRegistry` and `PluginRegistry`
  with the documented §59 lifecycle states
  (`installed / enabled / disabled / failed / incompatible /
  blocked-by-policy / update-available`), manifest
  validation (license, capabilities, compatibility,
  content hash), dependency resolution and the controlled
  enable / disable / configure surface. The registry is the
  single source of truth every other control-plane
  subsystem consults; built-in and installed features share
  the same lifecycle vocabulary.
  → `pi_platform/ports/control/registry.py` (new),
    `pi_platform/core/control/registry.py` (new),
    `pi_platform/adapters/control/registry_sinks.py` (new).
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane
    -v` MUST report `OK`;
  - the registry MUST reject an invalid manifest with the
    typed `ManifestValidationError`;
  - the registry MUST transition through the seven §59
    lifecycle states in the documented order;
  - `enable` / `disable` MUST consult the `PolicyEngine`
    and record an audit entry;
  - two consecutive `serialise()` calls MUST return
    byte-identical JSON.

### 7.2 — Hook Runtime (task 97)

- [ ] 97. Implement `HookRuntime` with the documented §59
  lifecycle events, bounded timeout, cancellation,
  structured result, correlation ID, audit record,
  bounded retries if explicitly configured and the
  documented failure policies (`FAIL_OPEN`,
  `FAIL_CLOSED`, `WARN_ONLY`, `DISABLE_PLUGIN`).
  Security-sensitive hooks fail closed;
  observability-only hooks may fail open. A failed hook
  MUST NOT silently deadlock MCP / retrieval execution.
  → `pi_platform/ports/control/hooks.py` (new),
    `pi_platform/core/control/hooks.py` (new),
    `pi_platform/adapters/control/hook_workers.py` (new).
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane
    -v` MUST report `OK`;
  - a `FAIL_CLOSED` hook timeout MUST abort the calling
    data-plane action and record an audit entry;
  - a `WARN_ONLY` hook timeout MUST record a warning and
    continue;
  - a `DISABLE_PLUGIN` hook failure MUST transition the
    plugin to `failed` in the `PluginRegistry`;
  - cancellation MUST propagate to the running hook;
  - correlation IDs MUST be deterministic and unique per
    dispatch.

### 7.3 — Policy Engine (task 98)

- [ ] 98. Implement `PolicyEngine` with capability-based
  authorization, the §59 capability vocabulary, the role
  defaults (`Viewer`, `Developer`, `Maintainer`,
  `Administrator`), the `ALLOW / DENY / REQUIRE_APPROVAL`
  decision contract, the typed `PolicyDecision` value
  and the typed `ApprovalRequired` exception. The engine
  replaces the Phase 1 `PolicyDecisionStub` behind the
  existing Phase 1 `PolicyDecisionPort`; the Phase 1
  `MaterialiseService` approval boundary and the Phase 1
  `TrustedApprovalBoundary` remain in force.
  → `pi_platform/ports/control/policy.py` (new),
    `pi_platform/core/control/policy.py` (new),
    `pi_platform/adapters/control/policy_engine.py` (new).
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane
    -v` MUST report `OK`;
  - the documented read-only coding-agent capability set
    from §59.8 MUST authorise `knowledge.read`,
    `retrieval.query`, `config.read`, `audit.write` and
    MUST deny `knowledge.write`, `knowledge.materialize`,
    `config.write`, `git.write`, `secret.resolve`;
  - a `materialize_knowledge` request from a `Viewer`
    MUST return `REQUIRE_APPROVAL`;
  - a `materialize_knowledge` request from a `Maintainer`
    with an explicit approval token MUST return `ALLOW`;
  - the engine MUST replace the Phase 1
    `PolicyDecisionStub` without changing the Phase 1
    `MaterialiseService` approval contract.

### 7.4 — Secret Provider (task 99)

- [ ] 99. Implement `SecretProvider` with the `secret://`
  and `env://` reference vocabulary, mandatory redaction
  in MCP responses, A2A payloads (unless explicitly
  authorized), audit payloads and LLM context, the
  `SecretReference` value type and the typed
  `SecretResolutionError`. The runtime database MUST NOT
  become a plain-text secret vault.
  → `pi_platform/ports/control/secrets.py` (new),
    `pi_platform/core/control/secrets.py` (new),
    `pi_platform/adapters/control/secret_backends.py`
    (new).
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane
    -v` MUST report `OK`;
  - the redaction filter MUST replace every resolved
    secret in MCP responses, A2A payloads, audit
    payloads and LLM context;
  - the runtime database MUST NOT contain a plain-text
    secret value;
  - an unresolvable reference MUST raise the typed
    `SecretResolutionError` and the calling consumer
    MUST translate it into `DENY` if the calling
    capability is `secret.resolve`.

### 7.5 — Audit Log (task 100)

- [ ] 100. Implement `AuditLog` and `OperationalLog` as two
  strictly separated streams. The Audit Log records the
  §59.13 fields. Secret values and unnecessary source
  contents MUST never be written into audit records.
  The Operational Log remains the diagnostics /
  performance / health surface; the two streams MUST
  NOT share a sink or a writer.
  → `pi_platform/ports/control/audit.py` (new),
    `pi_platform/core/control/audit.py` (new),
    `pi_platform/adapters/control/audit_sinks.py` (new).
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane
    -v` MUST report `OK`;
  - an audit record MUST contain the §59.13 fields;
  - the Audit Log MUST NOT contain a raw secret value
    even when the calling subsystem requested
    `secret.resolve`;
  - the Operational Log MUST NOT receive an audit
    record;
  - two consecutive `flush()` calls MUST return
    byte-identical JSONL.

### 7.6 — Feature Flags (task 101)

- [ ] 101. Implement `FeatureFlags` with the documented
  scope vocabulary (`machine`, `project`, `branch`,
  `user`, `deploymentProfile`) and the documented
  lifecycle states (`disabled`, `enabled`,
  `experimental`, `deprecated`). Git-versioned feature
  declarations and local overrides remain distinct.
  → `pi_platform/ports/control/flags.py` (new),
    `pi_platform/core/control/flags.py` (new),
    `pi_platform/adapters/control/flag_sources.py` (new).
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane
    -v` MUST report `OK`;
  - the flag registry MUST resolve the most specific
    scope (user > deploymentProfile > branch > project
    > machine);
  - an `experimental` flag MUST default to `disabled`
    unless the project explicitly enables it;
  - two consecutive `serialise()` calls MUST return
    byte-identical JSON.

### 7.7 — UI Extension Registry (task 102)

- [ ] 102. Implement `UiExtensionRegistry` with declarative
  UI descriptors, stable identifier contracts and a
  strict no-arbitrary-JavaScript-injection rule.
  Untrusted plugins cannot inject executable code; the UI
  runtime renders only the documented declarative
  descriptors.
  → `pi_platform/ports/control/ui_extensions.py` (new),
    `pi_platform/core/control/ui_extensions.py` (new),
    `pi_platform/adapters/control/ui_extension_validator.py`
    (new).
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane
    -v` MUST report `OK`;
  - the validator MUST reject any descriptor carrying
    JavaScript, `onclick`, `onerror`, `eval`, `Function`
    or any field outside the documented schema;
  - the registry MUST accept the documented descriptor
    shapes (`settingsPanel`, `statusPanel`,
    `dashboardWidget`, `menuItem`);
  - two consecutive `serialise()` calls MUST return
    byte-identical JSON.

### 7.8 — Focused regression tests (task 103)

- [ ] 103. Author
  `tests/test_phase_7_control_plane.py` covering:
  - the registry lifecycle state machine
    (`installed → enabled → disabled → failed →
    incompatible → blocked-by-policy →
    update-available → uninstalled`);
  - the hook runtime timeout / cancellation / failure
    policy contract;
  - the policy engine allow / deny / require-approval
    decision contract and the documented read-only
    coding-agent capability set;
  - the secret provider redaction contract and the
    no-plain-text-secret invariant;
  - the audit log field schema and the no-secret-in-
    audit invariant;
  - the feature flag scope resolution;
  - the UI extension validator's no-arbitrary-JS rule;
  - the cross-cutting quality gates:
    `tests/test_phase_6_quality_gates.py` extended with
    the Phase 7 policy allow / deny / require-approval
    fixture, the Phase 7 hook failure policy fixture,
    the Phase 7 audit redaction fixture, the Phase 7
    secret redaction fixture and the Phase 7 UI
    extension validation fixture.
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane
    -v` MUST report `OK`;
  - `python -m unittest tests.test_phase_6_quality_gates
    -v` MUST continue to report `OK` after the Phase 7
    fixtures are appended;
  - the focused regression suite MUST report every
    Phase 7 fixture as `PASS / FAIL / NOT RUN`
    explicitly.

### 7.9 — Wiki / ADR / archive / CURRENT.md (task 104)

- [ ] 104. Update the Wiki nodes listed in the
  [`context-impact.md`](context-impact.md) file, archive
  the prep change under
  `archive/<actual-archive-date>-prepare-phase-7-control-plane/`,
  archive the implementation change under
  `archive/<actual-archive-date>-implement-phase-7-control-plane/`,
  flip the `plan-v0-8-platform-architecture/tasks.md`
  rows 96-104 to `[x]` and update `openspec/CURRENT.md`
  to add the eight Phase 7 capabilities.
  Verification:
  - `python harness.py wiki-validate` MUST report
    `OK`;
  - `python harness.py openspec-check` MUST report
    `OK`;
  - `python harness.py check` MUST report `PASS`;
  - `python scripts/artifact_manifest.py verify` MUST
    report `OK`;
  - `python -m pi_platform.cli license-gate` MUST
    report `OK`;
  - `python -m unittest discover -s tests -v` MUST
    report `OK` on every supported Python version.