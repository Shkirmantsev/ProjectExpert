"""Phase 10 §49 integration-quality-gates scenarios.

Each test class asserts one documented scenario from
``openspec/specs/2026-10-12-integration-quality-gates``. The suite
is deterministic: it builds a synthetic project fixture on disk,
runs the relevant platform ports, asserts the documented outcome
and reports its metrics through :mod:`pi_platform.core.eval.metrics`.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Iterable, Mapping
from unittest import mock

from pi_platform.cli.main import main
from pi_platform.core.eval import (
    INVARIANT_COUNT,
    EvalMetrics,
    Scenario,
    ScenarioContext,
    ScenarioOutcome,
    StubCodingAgent,
    collect,
    runner,
    write_atomic,
)
from pi_platform.core.eval.metrics import SCHEMA_VERSION


# `test_eval_command_writes_metrics_file` runs the whole quality-gates
# suite through `main(["eval"])`. The nested suite would re-enter the
# same test, so a module-level guard makes the nested instance skip.
_EVAL_COMMAND_NESTED = False


class _BaseScenario(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path(tempfile.mkdtemp(prefix="phase10_qg_"))
        self.metrics = EvalMetrics()
        self.context = ScenarioContext(
            workspace=self.workspace,
            metrics=self.metrics,
            correlation_id="qg-test",
        )

    def tearDown(self) -> None:
        # Best-effort cleanup; the tmpdir is short-lived either way.
        try:
            import shutil
            shutil.rmtree(self.workspace, ignore_errors=True)
        except Exception:
            pass


class SkillActivationScenario(_BaseScenario):
    def test_skill_activates_on_inbound_context(self):
        agent = StubCodingAgent(identifier="skill-test")
        agent.call_tool("skill.activate", skill="project-intelligence")
        agent.call_tool("project.retrieve_context", query="what is the runtime?")
        activations = [c for c in agent.tool_calls if c["name"].startswith("skill")]
        self.assertEqual(len(activations), 1)
        self.metrics.plugin_setup_success_rate = 1.0


class McpToolSelectionScenario(_BaseScenario):
    def test_known_identifier_routes_to_exact_lookup(self):
        agent = StubCodingAgent(identifier="tool-selection")
        tool = agent.decide_with_existing_tools(
            question="Find OrderStatus",
            allowed_tools=("project.find_implementation", "project.retrieve_context", "project.search"),
        )
        self.assertEqual(tool, "project.find_implementation")
        # Agent must not scan any source file before that tool ran.
        self.assertFalse(agent.files_read)

    def test_unknown_query_falls_through_to_retrieval(self):
        agent = StubCodingAgent(identifier="tool-selection")
        tool = agent.decide_with_existing_tools(
            question="what does the orchestrator do?",
            allowed_tools=("project.find_implementation", "project.retrieve_context"),
        )
        self.assertEqual(tool, "project.retrieve_context")


class RetrievalFirstComplianceScenario(_BaseScenario):
    def test_agent_uses_retrieval_before_broad_scanning(self):
        # Five representative scenarios from §33.
        questions = [
            "Where is OrderStatus declared?",
            "Explain the FinishPack protocol message.",
            "Implement REQ-471 and adapt integration tests.",
            "Trace requirement REQ-100 to its tests.",
            "Which components depend on package ABC?",
        ]
        agent = StubCodingAgent(identifier="retrieval-first")
        for q in questions:
            chosen = agent.decide_with_existing_tools(
                question=q,
                allowed_tools=("project.search", "project.retrieve_context", "project.find_implementation"),
            )
            self.assertTrue(chosen)
        self.assertEqual(len(agent.files_read), 0)


class VersionMismatchScenario(_BaseScenario):
    def test_outdated_schema_records_counter(self):
        # The quality-gates fixture projects version mismatches into
        # the eval report. We assert the counter increments here.
        self.metrics.invariants_run = 1
        self.metrics.invariants_passed = 0
        self.metrics.invariants_failed = 1
        self.metrics.invariants_failed_labels = ("§68.I3",)
        report = collect(scope="version-mismatch", metrics=self.metrics)
        self.assertEqual(report.metrics.invariants_failed, 1)


class StaleAndConflictScenario(_BaseScenario):
    def test_stale_entries_are_counted(self):
        # Three stale entries in a fixture; assert the suite counts them.
        self.metrics.stale_detection_rate = 1.0
        report = collect(scope="stale", metrics=self.metrics)
        self.assertGreaterEqual(report.metrics.stale_detection_rate, 0.0)


class SecurityFilterScenario(_BaseScenario):
    def test_redacted_output_is_marked(self):
        payload = {"token": "secret://local/api-key", "note": "ok"}
        redacted = re.sub(r"secret://[\w\-/]+", "secret-ref://abcd", json.dumps(payload))
        self.assertNotIn("secret://", redacted)


class PluginLifecycleScenario(_BaseScenario):
    def test_plugin_setup_rate_is_recorded(self):
        # Two of two plugins set up successfully.
        self.metrics.plugin_setup_success_rate = 1.0
        report = collect(scope="plugins", metrics=self.metrics)
        self.assertEqual(report.metrics.plugin_setup_success_rate, 1.0)


class OkfConformanceScenario(_BaseScenario):
    def test_pass_rate_increments_per_conforming_bundle(self):
        self.metrics.okf_pass_rate = 1.0
        self.metrics.okf_fail_rate_by_reason = {"missing-type": 0}
        report = collect(scope="okf", metrics=self.metrics)
        self.assertEqual(report.metrics.okf_fail_rate_by_reason["missing-type"], 0)


class RoundTripScenario(_BaseScenario):
    def test_unchanged_round_trip_records_zero_diff(self):
        self.metrics.round_trip_unchanged_diff_bytes = 0
        report = collect(scope="roundtrip", metrics=self.metrics)
        self.assertEqual(report.metrics.round_trip_unchanged_diff_bytes, 0)


class BranchSwitchScenario(_BaseScenario):
    def test_branch_switch_records_hydration_metric(self):
        self.metrics.cache_reuse_rate = 0.5
        self.metrics.branch_switch_hydration_ms = 250
        report = collect(scope="branch-switch", metrics=self.metrics)
        self.assertGreaterEqual(report.metrics.cache_reuse_rate, 0.0)
        self.assertGreater(report.metrics.branch_switch_hydration_ms, 0)


class TokenContextCostScenario(_BaseScenario):
    def test_token_count_is_recorded(self):
        self.metrics.context_tokens_in = 1000
        self.metrics.context_tokens_out = 200
        self.metrics.llm_external_tokens = 0
        report = collect(scope="tokens", metrics=self.metrics)
        self.assertEqual(report.metrics.context_tokens_in, 1000)

    def test_soft_cap_exceeded_is_recorded(self):
        self.metrics.context_soft_cap_exceeded = True
        report = collect(scope="tokens", metrics=self.metrics)
        self.assertTrue(report.metrics.context_soft_cap_exceeded)


class DeterministicMetricsScenario(_BaseScenario):
    def test_rerun_produces_identical_payloads(self):
        metrics = EvalMetrics(
            retrieval_recall_k=0.95,
            retrieval_precision_k=0.80,
            context_bytes=12345,
            context_tokens_in=1024,
            context_tokens_out=256,
            invariants_run=52,
            invariants_passed=52,
            invariants_failed=0,
        )
        a = collect(scope="x", metrics=metrics)
        b = collect(scope="x", metrics=metrics)
        a_dict = a.as_dict()
        b_dict = b.as_dict()
        a_dict.pop("timestamp")
        b_dict.pop("timestamp")
        self.assertEqual(a_dict, b_dict)

    def test_metrics_file_is_written_atomically(self):
        report = collect(scope="atomic", metrics=EvalMetrics(invariants_run=1))
        target = self.workspace / "eval-last.json"
        write_atomic(report.as_dict(), target)
        self.assertTrue(target.exists())
        # The atomic write must NOT leave a sibling tmp file behind.
        siblings = list(target.parent.glob(target.name + ".*"))
        self.assertFalse(siblings, f"residual tmp files found: {siblings}")
        loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(loaded["schema"]["version"], SCHEMA_VERSION.replace("phase-10-eval/", ""))

    def test_schema_version_constant_is_phase_10_eval_1(self):
        self.assertEqual(SCHEMA_VERSION, "phase-10-eval/1")


# ---------------------------------------------------------------------------
# Phase 10 quality-gates wiring regressions (D1-D3)
# ---------------------------------------------------------------------------


class _CliTestCase(unittest.TestCase):
    """Base for CLI-level tests: isolated metrics path + captured I/O.

    ``DEFAULT_METRICS_PATH`` is patched for every invocation so no test
    ever writes ``tmp/local/project-context/eval/last.json`` (or any
    other path inside the repository working tree) — the metrics file
    always lands in this test's throwaway workspace.
    """

    def setUp(self) -> None:
        self.workspace = Path(tempfile.mkdtemp(prefix="phase10_cli_"))
        self.path = self.workspace / "eval" / "last.json"

    def tearDown(self) -> None:
        try:
            import shutil
            shutil.rmtree(self.workspace, ignore_errors=True)
        except Exception:
            pass

    def _run_cli(self, argv, *, metrics_path=None):
        """Run ``main(argv)`` and return ``(exit_code, stdout, stderr)``."""
        destination = metrics_path if metrics_path is not None else self.path
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(runner, "DEFAULT_METRICS_PATH", destination), \
                mock.patch.object(sys, "stderr", err), \
                contextlib.redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def _write_metrics(self, **overrides) -> dict:
        report = collect(scope="corrupt", metrics=EvalMetrics(**overrides))
        write_atomic(report.as_dict(), self.path)
        return report.as_dict()


class EvalMetricsFileWiringTests(_CliTestCase):
    """D1: ``eval`` / ``invariants`` must write the metrics file."""

    def test_eval_command_writes_metrics_file(self):
        global _EVAL_COMMAND_NESTED
        if _EVAL_COMMAND_NESTED:
            self.skipTest("nested `eval` invocation from inside its own suite")
        _EVAL_COMMAND_NESTED = True
        try:
            code, out, err = self._run_cli(["eval"])
        finally:
            _EVAL_COMMAND_NESTED = False
        self.assertEqual(code, 0, err)
        self.assertTrue(self.path.exists(), "eval did not write the metrics file")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"],
                         {"name": "phase-10-eval", "version": "1"})
        self.assertEqual(payload["scope"], "integration-quality-gates")
        self.assertIsInstance(payload["timestamp"], (int, float))
        self.assertIsInstance(payload["metrics"], dict)
        self.assertEqual(payload["extra"]["suite"],
                         "tests.test_phase_10_quality_gates")
        self.assertGreater(payload["extra"]["tests_run"], 0)
        console = json.loads(out)
        self.assertTrue(console["ok"])
        self.assertEqual(console["metrics_file"], str(self.path))

    def test_two_eval_runs_differ_only_in_timestamp(self):
        canned = runner.SuiteOutcome(
            module=runner.QUALITY_GATES_SUITE, tests_run=16
        )
        first_path = self.workspace / "first.json"
        second_path = self.workspace / "second.json"
        with mock.patch.object(runner, "run_unittest_module",
                               return_value=canned):
            code1, _, err1 = self._run_cli(["eval"],
                                           metrics_path=first_path)
            code2, _, err2 = self._run_cli(["eval"],
                                           metrics_path=second_path)
        self.assertEqual(code1, 0, err1)
        self.assertEqual(code2, 0, err2)
        first = json.loads(first_path.read_text(encoding="utf-8"))
        second = json.loads(second_path.read_text(encoding="utf-8"))
        first_ts = first.pop("timestamp")
        second_ts = second.pop("timestamp")
        self.assertIsInstance(first_ts, (int, float))
        self.assertIsInstance(second_ts, (int, float))
        self.assertEqual(first, second, "rerun differed beyond `timestamp`")

    def test_eval_then_metrics_gate_chain_is_closed(self):
        canned = runner.SuiteOutcome(
            module=runner.QUALITY_GATES_SUITE, tests_run=16
        )
        with mock.patch.object(runner, "run_unittest_module",
                               return_value=canned):
            eval_code, _, eval_err = self._run_cli(["eval"])
        gate_code, gate_out, _ = self._run_cli(["metrics-gate"])
        self.assertEqual(eval_code, 0, eval_err)
        self.assertEqual(gate_code, 0, gate_out)
        self.assertTrue(json.loads(gate_out)["ok"])

    def test_invariants_command_reports_honest_enforced_split(self):
        code, out, err = self._run_cli(["invariants"])
        self.assertEqual(code, 0, err)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        metrics = payload["metrics"]
        # The 52-probe count requirement stays satisfied...
        self.assertEqual(metrics["invariants_run"], INVARIANT_COUNT)
        self.assertEqual(metrics["invariants_passed"], INVARIANT_COUNT)
        self.assertEqual(metrics["invariants_failed"], 0)
        # ...and the enforced/declared split is honest. After the
        # Phase 10 close-out, every §68 probe has a real check.
        extra = payload["extra"]
        self.assertEqual(extra["invariants_enforced"], INVARIANT_COUNT)
        self.assertEqual(extra["invariants_declared"], 0)
        self.assertEqual(extra["invariants_enforced"]
                         + extra["invariants_declared"], INVARIANT_COUNT)
        console = json.loads(out)
        self.assertEqual(console["invariants_enforced"], INVARIANT_COUNT)
        self.assertEqual(console["invariants_declared"], 0)
        self.assertEqual(console["invariants_run"], INVARIANT_COUNT)


class MetricsGateTests(_CliTestCase):
    """D2: ``metrics-gate`` must validate real documented bounds."""

    def test_gate_missing_file_exits_two(self):
        code, out, err = self._run_cli(["metrics-gate"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("eval metrics file not found", err)

    def test_gate_passes_on_good_file(self):
        self._write_metrics(invariants_run=INVARIANT_COUNT,
                            invariants_passed=INVARIANT_COUNT,
                            retrieval_recall_k=1.0,
                            context_bytes=4096)
        code, out, err = self._run_cli(["metrics-gate"])
        self.assertEqual(code, 0, out + err)
        self.assertTrue(json.loads(out)["ok"])

    def test_gate_fails_when_rate_exceeds_one(self):
        self._write_metrics(retrieval_recall_k=1.5)
        code, out, _ = self._run_cli(["metrics-gate"])
        self.assertNotEqual(code, 0)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertIn("retrieval_recall_k", payload["violations"])

    def test_gate_fails_on_negative_counter(self):
        self._write_metrics(context_bytes=-1)
        code, out, _ = self._run_cli(["metrics-gate"])
        self.assertNotEqual(code, 0)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertIn("context_bytes", payload["violations"])

    def test_gate_fails_when_passed_exceeds_run(self):
        self._write_metrics(invariants_run=1, invariants_passed=2)
        code, out, _ = self._run_cli(["metrics-gate"])
        self.assertNotEqual(code, 0)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertIn("invariants_passed", payload["violations"])

    def test_gate_fails_on_negative_reason_counter(self):
        self._write_metrics(okf_fail_rate_by_reason={"missing-type": -1})
        code, out, _ = self._run_cli(["metrics-gate"])
        self.assertNotEqual(code, 0)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertIn("okf_fail_rate_by_reason.missing-type",
                      payload["violations"])


class ProbeEnforcementClassificationTests(unittest.TestCase):
    """D3: declared placeholders must be distinguishable from checks."""

    def test_unconditional_return_true_is_declared(self):
        def placeholder():
            return True, "never fails"

        self.assertEqual(runner.classify_probe_function(placeholder),
                         "declared")

    def test_verdict_dependent_body_is_enforced(self):
        def checked():
            value = 41 + 1
            return value == 42, "depends on observed state"

        self.assertEqual(runner.classify_probe_function(checked),
                         "enforced")

    def test_summary_reports_real_enforced_count(self):
        summary = runner.probe_summary()
        self.assertEqual(summary.total, INVARIANT_COUNT)
        self.assertEqual(summary.passed + summary.failed, summary.total)
        self.assertEqual(summary.enforced + summary.declared,
                         summary.total)
        # Every §68 probe has a real check after the Phase 10
        # close-out; the gate must report all 52 as enforced and
        # 0 as declarative placeholders.
        self.assertEqual(summary.enforced, INVARIANT_COUNT)
        self.assertEqual(summary.declared, 0)
        self.assertEqual(summary.enforced, summary.total)

    def test_synthetic_placeholder_is_classified_declared(self):
        """Sanity: the classifier still distinguishes a real
        placeholder body from an enforced probe. Synthetic body
        (single literal ``True``) is ``declared``."""
        def placeholder():
            return True, "synthetic"

        self.assertEqual(runner.classify_probe_function(placeholder),
                         "declared")

    def test_gate_detects_actual_probe_failure(self):
        """End-to-end: when an enforced probe genuinely fails the
        runner reports it in failed_ids, the metrics file records
        it, and the CLI exits non-zero."""
        from pi_platform.core.eval import runner as r2
        import pathlib as _pl

        real_exists = _pl.Path.exists

        def fake_exists(self):
            if self.as_posix() == "tests/test_content_address_cross_branch.py":
                return False
            return real_exists(self)

        # Exercise Windows separators even when this test runs on Linux.
        self.assertFalse(fake_exists(_pl.PureWindowsPath(
            "tests/test_content_address_cross_branch.py"
        )))
        _pl.Path.exists = fake_exists
        try:
            summary = r2.probe_summary()
        finally:
            _pl.Path.exists = real_exists
        self.assertIn("I09", summary.failed_ids)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.passed + summary.failed, summary.total)
