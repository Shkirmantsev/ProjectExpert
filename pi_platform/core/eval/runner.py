"""Phase 10 quality-gates suite runner and metrics-file wiring.

This module closes the loop between the ``make eval`` / ``make
invariants`` CLI handlers and the documented metrics file
``tmp/local/project-context/eval/last.json`` (schema
``phase-10-eval/1``):

- :func:`run_unittest_module` executes one ``unittest`` module and
  returns a deterministic :class:`SuiteOutcome` record of its inputs
  and outputs (counts and failing test ids only — no timings, so a
  rerun against the same inputs is byte-identical modulo
  ``timestamp``);
- :func:`eval_report` / :func:`invariants_report` turn an outcome
  into an :class:`pi_platform.core.eval.metrics.EvalReport`;
- :func:`write_report` publishes it through the existing atomic
  writer :func:`pi_platform.core.eval.writer.write_atomic`;
- :func:`probe_summary` executes every §68 probe and — critically —
  splits the probe count into **enforced** probes (whose verdict can
  depend on observed state) and **declared** placeholders (whose
  entire body is an unconditional literal ``return True``) so the
  report never claims 52 enforced invariants when fewer are.

Every function that writes the metrics file honours the module-level
:data:`DEFAULT_METRICS_PATH` global resolved *at call time*, so tests
can redirect the write with ``unittest.mock.patch``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Type

from .invariants import InvariantProbe, discover_probes
from .metrics import EvalMetrics, EvalReport, collect
from .writer import write_atomic


# The two ``unittest`` modules the CLI handlers run.
QUALITY_GATES_SUITE = "tests.test_phase_10_quality_gates"
INVARIANTS_SUITE = "tests.test_phase_10_invariants"

# Report scopes (stable strings; part of the deterministic payload).
EVAL_SCOPE = "integration-quality-gates"
INVARIANTS_SCOPE = "phase-10-invariants"

# The one and only destination for eval reports. Relative to the
# repository root; ``tmp/local/**`` is gitignored.
DEFAULT_METRICS_PATH = Path("tmp/local/project-context/eval/last.json")

# Human-readable description of the enforced/declared classification,
# recorded verbatim in the invariants report so the numbers in the
# metrics file are self-describing.
ENFORCEMENT_RULE = (
    "declared: the probe body is a single unconditional literal "
    "`return True` and can never fail; enforced: any other body "
    "whose verdict can depend on observed state"
)


def resolve_metrics_path(path: Optional[Path] = None) -> Path:
    """Return the metrics destination.

    ``path`` wins when given; otherwise the current value of
    :data:`DEFAULT_METRICS_PATH` is read at call time so tests can
    patch the module global.
    """
    if path is None:
        return Path(DEFAULT_METRICS_PATH)
    return Path(path)


# ---------------------------------------------------------------------------
# Suite execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SuiteOutcome:
    """Deterministic record of one ``unittest`` module execution.

    Only test ids are recorded for failures/errors (never tracebacks)
    so two runs of the same suite over the same inputs produce
    identical payloads.
    """

    module: str
    tests_run: int
    failures: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    skipped: int = 0

    @property
    def ok(self) -> bool:
        return not self.failures and not self.errors

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1

    @property
    def tests_passed(self) -> int:
        """Tests that neither failed nor errored (skips count as run)."""
        return self.tests_run - len(self.failures) - len(self.errors)

    def as_dict(self) -> dict:
        return {
            "suite": self.module,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "failures": list(self.failures),
            "errors": list(self.errors),
            "skipped": self.skipped,
            "ok": self.ok,
        }


def _test_id(test: Any) -> str:
    try:
        return str(test.id())
    except Exception:  # pragma: no cover - defensive
        return str(test)


def run_unittest_module(module_name: str, *, stream: Any = None) -> SuiteOutcome:
    """Run a single ``unittest`` module in-process and summarise it.

    The runner stays zero-dependency (stdlib ``unittest`` only) and
    never shells out, so the caller's environment stays inside the
    same process tree. ``stream`` defaults to ``sys.stderr`` resolved
    at call time (test-patchable).
    """
    import unittest

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(module_name)
    if stream is None:
        stream = sys.stderr
    runner = unittest.TextTestRunner(verbosity=1, stream=stream)
    result = runner.run(suite)
    return SuiteOutcome(
        module=module_name,
        tests_run=result.testsRun,
        failures=tuple(_test_id(t) for t, _ in result.failures),
        errors=tuple(_test_id(t) for t, _ in result.errors),
        skipped=len(result.skipped),
    )


# ---------------------------------------------------------------------------
# §68 probe enforcement classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeSummary:
    """Honest split of a §68 probe run into enforced vs declared."""

    total: int
    passed: int
    failed: int
    failed_ids: tuple[str, ...]
    enforced: int
    declared: int
    enforced_ids: tuple[str, ...]
    declared_ids: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "invariants_run": self.total,
            "invariants_passed": self.passed,
            "invariants_failed": self.failed,
            "invariants_failed_ids": list(self.failed_ids),
            "invariants_enforced": self.enforced,
            "invariants_declared": self.declared,
            "invariants_enforced_ids": list(self.enforced_ids),
            "invariants_declared_ids": list(self.declared_ids),
        }


def _unwrap_probe_function(probe_cls: Type[InvariantProbe]) -> Optional[Callable[[], Any]]:
    """Return the inner probe function captured by the probe factory.

    Probes generated by ``tests.test_phase_10_invariants._probe``
    wrap the module-level ``_iNN`` function in a closure; the class's
    ``probe`` method therefore holds it in ``__closure__``.
    """
    probe = getattr(probe_cls, "probe", None)
    for cell in (getattr(probe, "__closure__", None) or ()):
        value = cell.cell_contents
        if inspect.isfunction(value):
            return value
    return None


def _is_literal_true(node: ast.AST) -> bool:
    """True when ``node`` is ``True`` (optionally first tuple element)."""
    if isinstance(node, ast.Constant):
        return node.value is True
    if isinstance(node, ast.Tuple) and node.elts:
        return _is_literal_true(node.elts[0])
    return False


def _return_depends_on_locals(stmt: ast.Return, local_names: set[str]) -> bool:
    """True when the return value references any locally-bound name.

    Used to distinguish ``return (cache and True, "...")`` (enforced:
    depends on ``cache``) from ``return (True, "...")`` with a
    dead-code ``cache = ...`` assignment above (declared).
    """
    if stmt.value is None:
        return False
    for sub in ast.walk(stmt.value):
        if isinstance(sub, ast.Name) and sub.id in local_names:
            return True
    return False


def _classify_function(fn: Callable[[], Any]) -> str:
    """Classify a probe body as ``"enforced"`` or ``"declared"``.

    The check is source-level (AST) because behaviour alone cannot
    distinguish a genuine check from an unconditional ``return True``:

    - ``"declared"`` — every ``return`` in the body returns a literal
      that does not depend on any name bound in the body. Such a
      probe can never fail.
    - ``"enforced"`` — at least one ``return`` returns a value that
      depends on a name bound in the body, or the body has no
      ``return`` and may raise.

    Conservative on doubt: if the source cannot be read or parsed the
    probe is reported ``"declared"`` — this module must never
    overstate enforcement.
    """
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return "declared"
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return "declared"
    if not tree.body:
        return "declared"
    node = tree.body[0]
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "declared"
    statements = list(node.body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    # Collect names bound anywhere in the body, and every Return
    # node regardless of nesting (so we can see inside ``if`` /
    # ``try`` / ``for`` / ``while`` blocks). Imports count too:
    # a probe that branches on `Port is not None` references the
    # import, and the import can fail (ImportError) or the binding
    # can be shadowed.
    local_names: set[str] = set()
    for s in ast.walk(node):
        if isinstance(s, ast.Assign):
            for tgt in s.targets:
                if isinstance(tgt, ast.Name):
                    local_names.add(tgt.id)
        elif isinstance(s, (ast.AnnAssign, ast.AugAssign)):
            tgt = s.target
            if isinstance(tgt, ast.Name):
                local_names.add(tgt.id)
        elif isinstance(s, ast.For):
            if isinstance(s.target, ast.Name):
                local_names.add(s.target.id)
        elif isinstance(s, ast.With):
            for item in s.items:
                if item.optional_vars is not None and isinstance(item.optional_vars, ast.Name):
                    local_names.add(item.optional_vars.id)
        elif isinstance(s, ast.Import):
            for alias in s.names:
                local_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(s, ast.ImportFrom):
            for alias in s.names:
                local_names.add(alias.asname or alias.name)
    returns: list[ast.Return] = [s for s in ast.walk(node) if isinstance(s, ast.Return)]
    if not returns:
        return "enforced"  # body may raise
    # If ANY return references a local name (including f-strings and
    # string formatting), the verdict can depend on observed state
    # — enforced. We treat imports and module-level names the same
    # way: a probe that does ``Path("...").exists()`` depends on
    # the ``pathlib.Path`` binding (which can be shadowed or fail to
    # import) and on the filesystem; either way, it is not a
    # unconditional ``return True`` placeholder.
    for ret in returns:
        if _return_depends_on_locals(ret, local_names):
            return "enforced"
        if _return_references_any_name(ret):
            return "enforced"
    return "declared"


def _return_references_any_name(ret: ast.Return) -> bool:
    """True when ``ret.value`` references any bare ``ast.Name``.

    Probes whose return values contain *any* bare name (not just
    locals) cannot be unconditional ``return True`` placeholders:
    a name reference is an observation that can fail or be
    shadowed.
    """
    for sub in ast.walk(ret.value):
        if isinstance(sub, ast.Name):
            return True
    return False


def classify_probe(probe_cls: Type[InvariantProbe]) -> str:
    """Return ``"enforced"`` or ``"declared"`` for a probe class."""
    fn = _unwrap_probe_function(probe_cls)
    if fn is not None:
        return _classify_function(fn)
    # No closure to unwrap: inspect the class's own ``probe`` method
    # when it defines one, otherwise stay conservative.
    method = probe_cls.__dict__.get("probe")
    if method is not None and inspect.isfunction(method):
        return _classify_function(method)
    return "declared"


def classify_probe_function(fn: Callable[[], Any]) -> str:
    """Classify a bare probe function (exposed for direct testing)."""
    return _classify_function(fn)


def probe_summary(module_name: str = INVARIANTS_SUITE) -> ProbeSummary:
    """Execute every §68 probe in ``module_name`` and summarise it.

    ``total``/``passed``/``failed`` describe what actually ran;
    ``enforced``/``declared`` describe how many of those probes can
    genuinely fail. Both pairs are reported because a run of 52 probes
    of which only 24 contain real checks must not be presented as 52
    enforced invariants.
    """
    module = importlib.import_module(module_name)
    probes = discover_probes(vars(module))
    passed = 0
    failed = 0
    failed_ids: list[str] = []
    enforced_ids: list[str] = []
    declared_ids: list[str] = []
    for probe_cls in probes:
        try:
            ok, _detail = probe_cls().probe()
        except Exception:  # pragma: no cover - factory already traps
            ok = False
        if ok:
            passed += 1
        else:
            failed += 1
            failed_ids.append(probe_cls.invariant_id)
        if classify_probe(probe_cls) == "enforced":
            enforced_ids.append(probe_cls.invariant_id)
        else:
            declared_ids.append(probe_cls.invariant_id)
    return ProbeSummary(
        total=len(probes),
        passed=passed,
        failed=failed,
        failed_ids=tuple(failed_ids),
        enforced=len(enforced_ids),
        declared=len(declared_ids),
        enforced_ids=tuple(enforced_ids),
        declared_ids=tuple(declared_ids),
    )


# ---------------------------------------------------------------------------
# Report construction and publication
# ---------------------------------------------------------------------------


def _suite_extra(outcome: SuiteOutcome) -> dict:
    return {
        "suite": outcome.module,
        "tests_run": outcome.tests_run,
        "tests_passed": outcome.tests_passed,
        "failures": list(outcome.failures),
        "errors": list(outcome.errors),
        "skipped": outcome.skipped,
        "exit_code": outcome.exit_code,
    }


def eval_report(outcome: SuiteOutcome) -> EvalReport:
    """Build the ``phase-10-eval/1`` report for a quality-gates run.

    The scenario suites assert their domain rates internally; the
    report records the suite identity and its outcome. Metric values
    stay at their documented zero defaults, which are within bounds by
    construction.
    """
    return collect(scope=EVAL_SCOPE, metrics=EvalMetrics(), extra=_suite_extra(outcome))


def invariants_report(outcome: SuiteOutcome, summary: ProbeSummary) -> EvalReport:
    """Build the ``phase-10-eval/1`` report for a §68 probe run.

    ``metrics.invariants_*`` record the real executed counts and
    ``extra.invariants_enforced`` / ``extra.invariants_declared``
    record the honest enforcement split — the report never claims more
    enforced invariants than the probe bodies justify.
    """
    metrics = EvalMetrics(
        invariants_run=summary.total,
        invariants_passed=summary.passed,
        invariants_failed=summary.failed,
        invariants_failed_labels=tuple(summary.failed_ids),
    )
    extra = _suite_extra(outcome)
    extra.update(
        {
            "invariants_enforced": summary.enforced,
            "invariants_declared": summary.declared,
            "invariants_enforced_ids": list(summary.enforced_ids),
            "invariants_declared_ids": list(summary.declared_ids),
            "enforcement_rule": ENFORCEMENT_RULE,
        }
    )
    return collect(scope=INVARIANTS_SCOPE, metrics=metrics, extra=extra)


def write_report(report: EvalReport, path: Optional[Path] = None) -> Path:
    """Atomically publish ``report`` to the metrics file and return its path."""
    destination = resolve_metrics_path(path)
    write_atomic(report.as_dict(), destination)
    return destination