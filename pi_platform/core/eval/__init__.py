"""Phase 10 §49 + §120 integration-quality-gates evaluation core.

The :mod:`pi_platform.core.eval` package ships:

- :mod:`metrics` — the structured `phase-10-eval/1` metric schema and
  the deterministic collector helpers used by every scenario;
- :mod:`writer` — atomic write helper for
  ``tmp/local/project-context/eval/last.json``;
- :mod:`scenarios` — base classes that the Phase 10 test suites use
  to keep their structure uniform;
- :mod:`invariants` — the §68 acceptance suite probe base class and
  helpers;
- :mod:`migration_guard` — the schema-version migration guard
  helpers used by the hydration driver and the
  :class:`SchemaVersionMismatchScenario` tests.

The package implements no production policy; it is the
regression-grade harness for §49 quality gates and §120 invariant
checks.
"""

from .metrics import (
    EvalMetrics,
    EvalReport,
    MetricSchema,
    SCHEMA_VERSION,
    collect,
)
from .writer import write_atomic
from .scenarios import (
    Scenario,
    ScenarioContext,
    ScenarioOutcome,
    StubCodingAgent,
)
from .invariants import (
    InvariantProbe,
    InvariantReport,
    discover_probes,
    INVARIANT_COUNT,
)
from .migration_guard import (
    IdentityInvalid,
    Incompatible,
    MigrationRequired,
    WorkingTreeMismatch,
    RuntimeSchemaVersions,
    check_schema_identity,
)

__all__ = [
    # metrics
    "EvalMetrics",
    "EvalReport",
    "MetricSchema",
    "SCHEMA_VERSION",
    "collect",
    # writer
    "write_atomic",
    # scenarios
    "Scenario",
    "ScenarioContext",
    "ScenarioOutcome",
    "StubCodingAgent",
    # invariants
    "InvariantProbe",
    "InvariantReport",
    "discover_probes",
    "INVARIANT_COUNT",
    # migration guard
    "IdentityInvalid",
    "Incompatible",
    "MigrationRequired",
    "WorkingTreeMismatch",
    "RuntimeSchemaVersions",
    "check_schema_identity",
]
