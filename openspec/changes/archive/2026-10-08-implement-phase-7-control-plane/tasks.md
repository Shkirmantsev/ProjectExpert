# Tasks — implement-phase-7-control-plane

This tasks file mirrors the Phase 7 tasks 96-104 from
the canonical
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md).
The implementation work executes the tasks defined by the
[`prepare-phase-7-control-plane/tasks.md`](../prepare-phase-7-control-plane/tasks.md)
file; this file lists the tasks in execution order with
the concrete verification commands.

The eight Phase 7 capability specs under
[`specs/`](specs) are the authoritative behavioural
contract.

## Phase 7 — Control plane (implementation)

### 7.1 — Feature / Plugin Registry (task 96)

- [ ] 96. Implement the Feature / Plugin Registry per the
  [`control-registry`](../prepare-phase-7-control-plane/specs/2026-10-08-control-registry/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane -v`
    MUST report `OK`;
  - the registry MUST reject an invalid manifest with the
    typed `ManifestValidationError`;
  - the registry MUST transition through the seven §59
    lifecycle states in the documented order;
  - `enable` / `disable` MUST consult the `PolicyEngine`
    and record an audit entry;
  - two consecutive `serialise()` calls MUST return
    byte-identical JSON.

### 7.2 — Hook Runtime (task 97)

- [ ] 97. Implement the Hook Runtime per the
  [`hook-runtime`](../prepare-phase-7-control-plane/specs/2026-10-08-hook-runtime/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane -v`
    MUST report `OK`;
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

- [ ] 98. Implement the Policy Engine per the
  [`policy-engine`](../prepare-phase-7-control-plane/specs/2026-10-08-policy-engine/spec.md)
  capability spec and the cross-cutting
  [`capabilities`](../prepare-phase-7-control-plane/specs/2026-10-08-capabilities/spec.md)
  spec.
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane -v`
    MUST report `OK`;
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

- [ ] 99. Implement the Secret Provider per the
  [`secret-provider`](../prepare-phase-7-control-plane/specs/2026-10-08-secret-provider/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane -v`
    MUST report `OK`;
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

- [ ] 100. Implement the Audit Log / Operational Log per the
  [`audit-log`](../prepare-phase-7-control-plane/specs/2026-10-08-audit-log/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane -v`
    MUST report `OK`;
  - an audit record MUST contain the §59.13 fields;
  - the Audit Log MUST NOT contain a raw secret value
    even when the calling subsystem requested
    `secret.resolve`;
  - the Operational Log MUST NOT receive an audit
    record;
  - two consecutive `flush()` calls MUST return
    byte-identical JSONL.

### 7.6 — Feature Flags (task 101)

- [ ] 101. Implement Feature Flags per the
  [`feature-flags`](../prepare-phase-7-control-plane/specs/2026-10-08-feature-flags/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane -v`
    MUST report `OK`;
  - the flag registry MUST resolve the most specific
    scope (user > deploymentProfile > branch > project
    > machine);
  - an `experimental` flag MUST default to `disabled`
    unless the project explicitly enables it;
  - two consecutive `serialise()` calls MUST return
    byte-identical JSON.

### 7.7 — UI Extension Registry (task 102)

- [ ] 102. Implement the UI Extension Registry per the
  [`ui-extension`](../prepare-phase-7-control-plane/specs/2026-10-08-ui-extension/spec.md)
  capability spec.
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane -v`
    MUST report `OK`;
  - the validator MUST reject any descriptor carrying
    JavaScript, `onclick`, `onerror`, `eval`, `Function`
    or any field outside the documented schema;
  - the registry MUST accept the documented descriptor
    shapes (`settingsPanel`, `statusPanel`,
    `dashboardWidget`, `menuItem`);
  - two consecutive `serialise()` calls MUST return
    byte-identical JSON.

### 7.8 — Focused regression tests (task 103)

- [ ] 103. Author `tests/test_phase_7_control_plane.py`
  covering every Phase 7 fixture above and extend
  `tests/test_phase_6_quality_gates.py` with the Phase 7
  quality gates (policy allow / deny / require-approval,
  hook failure policy, audit redaction, secret redaction,
  UI extension validation).
  Verification:
  - `python -m unittest tests.test_phase_7_control_plane -v`
    MUST report `OK`;
  - `python -m unittest tests.test_phase_6_quality_gates -v`
    MUST continue to report `OK` after the Phase 7
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
  - `python harness.py wiki-validate` MUST report `OK`;
  - `python harness.py openspec-check` MUST report `OK`;
  - `python harness.py check` MUST report `PASS`;
  - `python scripts/artifact_manifest.py verify` MUST
    report `OK`;
  - `python -m pi_platform.cli license-gate` MUST
    report `OK`;
  - `python -m unittest discover -s tests -v` MUST
    report `OK` on every supported Python version.