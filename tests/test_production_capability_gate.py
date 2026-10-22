"""Tests for the production-capability gate and its CLI (PR 12).

Covers the ``production-semantic-search-and-branch-reconciliation``
OpenSpec change, spec delta
``specs/2026-10-18-production-capability-and-release-gates/spec.md``:

* ``production-capability gate`` — a production-enabled record whose
  ``revision``/``status`` is ``pinned-stub`` fails the gate and the
  failure message names the record and its profile; records from the
  excluded set (reranker, multimodal figure, OCR engines) never fail
  the gate;
* plan §64 runtime probes — a synthetic Docling path, the
  ``usearch-stub`` backend and a production model adapter that raises
  ``EmbeddingModelError`` unconditionally all fail the gate;
* the CLI contract — pretty JSON with exit code 0 when the gate
  passes, single-line ``--json`` output, exit code 1 on failure.

The inventory contract tests that pin the production-enabled /
excluded boundary documented in
``openspec/changes/production-semantic-search-and-branch-reconciliation/excluded-profiles.md``
are kept from the earlier PRs because the gate reads exactly that
boundary.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import (
    EmbeddingGemma2EmbeddingModel,
)
from pi_platform.cli.production_capability_gate import (
    cmd_production_capability_gate,
)
from pi_platform.core.orchestration.production_capability_gate import (
    run_production_capability_gate,
)
from pi_platform.ports.retrieval.embedding_model import EmbeddingModelError


REPO_ROOT = Path(__file__).resolve().parent.parent
LICENSE_JSON = REPO_ROOT / "distribution" / "licenses" / "model-licenses.json"
_ACTIVE_EXCLUDED_MD = (
    REPO_ROOT
    / "openspec"
    / "changes"
    / "production-semantic-search-and-branch-reconciliation"
    / "excluded-profiles.md"
)
_ARCHIVED_EXCLUDED_MD = (
    REPO_ROOT
    / "openspec"
    / "changes"
    / "archive"
    / "2026-10-20-production-semantic-search-and-branch-reconciliation"
    / "excluded-profiles.md"
)
EXCLUDED_PROFILES_MD = (
    _ACTIVE_EXCLUDED_MD
    if _ACTIVE_EXCLUDED_MD.is_file()
    else _ARCHIVED_EXCLUDED_MD
)
GATE_MODULE = "pi_platform.core.orchestration.production_capability_gate"

GEMMA_MODEL_ID = "google/embeddinggemma-2"
GEMMA_PROFILE = "semantic-cpu"
EXCLUDED_MODEL_ID = "multimodal-figure-512"


def _load_inventory() -> dict:
    with open(LICENSE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


class ModelLicensesInventorySchemaTests(unittest.TestCase):
    """The inventory MUST carry a production_enabled boundary that the
    production-capability-gate reads deterministically."""

    def test_inventory_root_has_models_list(self):
        inventory = _load_inventory()
        self.assertIsInstance(inventory, dict)
        self.assertIsInstance(inventory.get("models"), list)
        self.assertGreater(len(inventory["models"]), 0,
                           "license inventory MUST list at least one model")

    def test_every_record_carries_production_enabled(self):
        inventory = _load_inventory()
        for record in inventory["models"]:
            self.assertIn(
                "production_enabled", record,
                f"record {record.get('model_id')!r} MUST carry a "
                f"production_enabled boolean for the gate"
            )
            self.assertIsInstance(
                record["production_enabled"], bool,
                f"record {record.get('model_id')!r} production_enabled "
                f"MUST be a boolean"
            )

    def test_every_record_has_required_keys(self):
        inventory = _load_inventory()
        required = {
            "model_id", "provider", "revision", "modality",
            "spdx", "profile", "production_enabled", "status",
        }
        for record in inventory["models"]:
            missing = required - set(record.keys())
            self.assertFalse(
                missing,
                f"record {record.get('model_id')!r} is missing keys: "
                f"{sorted(missing)}"
            )


class ProductionEnabledBoundaryTests(unittest.TestCase):
    """The production-enabled set MUST be exactly the documented set.

    The boundary is authoritative for the production-capability-gate:
    records outside it (reranker, multimodal figure, OCR engines)
    MUST NOT fail the gate while they remain ``pinned-stub``.
    """

    def test_production_enabled_set_is_exactly_the_documented_set(self):
        inventory = _load_inventory()
        production_set = {
            r["model_id"] for r in inventory["models"]
            if r.get("production_enabled") is True
        }
        expected = {
            "google/embeddinggemma-2", "Qwen/Qwen3-Embedding-0.6B",
        }
        self.assertEqual(
            production_set, expected,
            "production_enabled set MUST be exactly the documented "
            "set (EmbeddingGemma 2 + Qwen3 Embedding 0.6B). Add a row "
            "to excluded-profiles.md before changing this set."
        )

    def test_excluded_records_have_rationale(self):
        inventory = _load_inventory()
        for record in inventory["models"]:
            if record.get("production_enabled") is False:
                self.assertTrue(
                    record.get("rationale"),
                    f"excluded record {record.get('model_id')!r} MUST "
                    f"carry a rationale string"
                )

    def test_hashing_is_not_production_enabled(self):
        """Hashing is the minimal/test diagnostic backend; it MUST
        NOT be reachable as a production embedding."""
        inventory = _load_inventory()
        for record in inventory["models"]:
            if record["provider"] == "hashing":
                self.assertFalse(
                    record.get("production_enabled"),
                    f"hashing record {record['model_id']!r} MUST NOT "
                    f"be marked production_enabled; the production "
                    f"profile MUST fail closed rather than silently "
                    f"substitute hashing."
                )

    def test_excluded_profiles_md_exists_and_documents_boundaries(self):
        self.assertTrue(
            EXCLUDED_PROFILES_MD.exists(),
            "excluded-profiles.md MUST exist to make the gate's "
            "boundary reviewable"
        )
        content = EXCLUDED_PROFILES_MD.read_text(encoding="utf-8")
        self.assertIn("Production-enabled set", content)
        self.assertIn("Excluded set", content)
        inventory = _load_inventory()
        for record in inventory["models"]:
            if not record.get("production_enabled"):
                self.assertIn(
                    record["model_id"], content,
                    f"excluded record {record['model_id']!r} MUST be "
                    f"documented in excluded-profiles.md"
                )

    def test_no_production_record_is_pinned_stub(self):
        """Release-blocking inventory check: no production-enabled
        record may still be ``pinned-stub``."""
        violations = [
            r["model_id"] for r in _load_inventory()["models"]
            if r.get("production_enabled") is True
            and (
                r.get("status") == "pinned-stub"
                or r.get("revision") == "pinned-stub"
            )
        ]
        self.assertEqual(
            violations, [],
            "production-enabled records still pinned-stub: "
            f"{violations}"
        )


class ProductionCapabilityGateTests(unittest.TestCase):
    """Behavioural tests for :func:`run_production_capability_gate`."""

    def setUp(self):
        # Core CI is independent of optional models. These contract tests
        # inject successful vendor results; the release workflow runs real
        # pinned weights through the unchanged default strict gate.
        import math
        from types import SimpleNamespace
        from pi_platform.adapters.retrieval.qwen3_embedding_model import Qwen3EmbeddingModel
        class Row(list):
            def tolist(self):
                return list(self)
        def build(provider, **kwargs):
            adapter = EmbeddingGemma2EmbeddingModel() if provider == "embeddinggemma2" else Qwen3EmbeddingModel()
            dim = adapter.dimension()
            adapter._model = SimpleNamespace(encode=lambda texts, **kw: [Row([1 / math.sqrt(dim)] * dim) for _ in texts])
            return adapter
        for target, options in [
            (f"{GATE_MODULE}.EmbeddingModelFactory.build", {"side_effect": build}),
            (f"{GATE_MODULE}.is_docling_available", {"return_value": True}),
            (f"{GATE_MODULE}.is_real_usearch_available", {"return_value": True}),
        ]:
            patcher = mock.patch(target, **options)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_failed_real_weight_load_is_release_failure(self):
        adapter = mock.Mock()
        adapter._load_failed = True
        adapter.embed.side_effect = EmbeddingModelError("incomplete or incompatible cached weights")
        with mock.patch(f"{GATE_MODULE}.EmbeddingModelFactory.build", return_value=adapter):
            report = run_production_capability_gate()
        self.assertFalse(report.passed)
        self.assertIn("could not load pinned weights", self._failed_text(report))
        self.assertFalse(any(v.name.startswith("embedding:") for v in report.skipped))

    def test_inventory_only_lane_does_not_claim_runtime_probes(self):
        with mock.patch(f"{GATE_MODULE}.EmbeddingModelFactory.build", side_effect=AssertionError("no runtime loads in core lane")):
            report = run_production_capability_gate(runtime_checks=False)
        self.assertTrue(report.passed)
        self.assertTrue(all(v.name.startswith("inventory:") for v in report.verdicts))

    def _mutated_inventory(self, mutate) -> Path:
        """Write a mutated copy of the license inventory to a temp
        file so the repository file is never modified."""

        inventory = _load_inventory()
        mutate(inventory)
        tmpdir = tempfile.mkdtemp(prefix="gate-inventory-")
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        path = Path(tmpdir) / "model-licenses.json"
        path.write_text(json.dumps(inventory), encoding="utf-8")
        return path

    def _failed_text(self, report) -> str:
        return "\n".join(
            f"{v.name} {v.detail}"
            for v in report.verdicts
            if v.state != "PASS"
        )

    def test_gate_passes_for_real_production_components(self):
        """The current environment provides the real components, so
        the release gate MUST pass."""
        report = run_production_capability_gate()
        self.assertTrue(
            report.passed,
            "gate MUST pass with the real production components: "
            f"{json.dumps(report.as_dict(), indent=2)}",
        )
        self.assertEqual(self._failed_text(report), "")
        names = {v.name for v in report.verdicts}
        self.assertIn("dense-index:usearch", names)
        self.assertIn("documents:docling", names)
        self.assertIn(f"inventory:{GEMMA_MODEL_ID}", names)

    def test_gate_fails_when_pinned_stub_record_present(self):
        """A production-enabled record flipped to ``pinned-stub``
        fails the gate and the failure message names the record and
        its profile (spec scenario)."""

        def mutate(inventory: dict) -> None:
            for record in inventory["models"]:
                if record.get("production_enabled") is True:
                    record["status"] = "pinned-stub"
                    record["revision"] = "pinned-stub"
                    break

        report = run_production_capability_gate(
            inventory_path=self._mutated_inventory(mutate),
        )
        self.assertFalse(report.passed)
        failed = self._failed_text(report)
        self.assertIn(GEMMA_MODEL_ID, failed)
        self.assertIn(GEMMA_PROFILE, failed)
        self.assertIn("pinned-stub", failed)

    def test_gate_ignores_excluded_profiles_pinned_stub(self):
        """An excluded (development-roadmap) record that is
        ``pinned-stub`` MUST NOT fail the gate (spec scenario)."""

        def mutate(inventory: dict) -> None:
            for record in inventory["models"]:
                if record.get("model_id") == EXCLUDED_MODEL_ID:
                    record["status"] = "pinned-stub"
                    record["revision"] = "pinned-stub"

        report = run_production_capability_gate(
            inventory_path=self._mutated_inventory(mutate),
        )
        self.assertTrue(
            report.passed,
            f"excluded record must not fail the gate: "
            f"{json.dumps(report.as_dict(), indent=2)}",
        )
        self.assertNotIn(EXCLUDED_MODEL_ID, self._failed_text(report))
        skipped = "\n".join(f"{v.name} {v.detail}" for v in report.skipped)
        self.assertIn(EXCLUDED_MODEL_ID, skipped)

    def test_gate_fails_on_synthetic_docling_path(self):
        """When the real Docling binding is unavailable the production
        path would fall back to a synthetic adapter — the gate MUST
        fail."""
        with mock.patch(
            f"{GATE_MODULE}.is_docling_available",
            return_value=False,
        ):
            report = run_production_capability_gate()
        self.assertFalse(report.passed)
        failed = self._failed_text(report)
        self.assertIn("documents:docling", failed)
        self.assertIn("synthetic Docling", failed)

    def test_gate_fails_on_usearch_stub_backend(self):
        """When the USearch native package is unavailable the dense
        backend resolves to ``usearch-stub`` — the gate MUST fail."""
        with mock.patch(
            f"{GATE_MODULE}.is_real_usearch_available",
            return_value=False,
        ):
            report = run_production_capability_gate()
        self.assertFalse(report.passed)
        failed = self._failed_text(report)
        self.assertIn("dense-index:usearch", failed)
        self.assertIn("usearch-stub", failed)

    def test_gate_fails_on_embedding_model_raising_embedding_model_error(self):
        """A production model adapter that raises
        ``EmbeddingModelError`` unconditionally (the stub contract)
        MUST fail the gate."""

        with mock.patch.object(
            EmbeddingGemma2EmbeddingModel,
            "embed",
            side_effect=EmbeddingModelError(
                "every embed call raises: the adapter is a stub"
            ),
        ):
            report = run_production_capability_gate()
        self.assertFalse(report.passed)
        failed = self._failed_text(report)
        self.assertIn(f"embedding:{GEMMA_MODEL_ID}", failed)
        self.assertIn("unconditionally", failed)

    def test_cli_pretty_output_returns_exit_zero_when_passing(self):
        """Default output is pretty JSON with ``"passed": true`` and
        exit code 0."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            return_code = cmd_production_capability_gate()
        output = buffer.getvalue()
        self.assertEqual(return_code, 0)
        self.assertIn('"passed": true', output)
        payload = json.loads(output)
        self.assertTrue(payload["passed"])
        self.assertIsInstance(payload["checks"], list)
        self.assertGreater(len(payload["checks"]), 0)
        for check in payload["checks"]:
            self.assertEqual(
                set(check), {"name", "passed", "details"},
                f"check must match the documented shape: {check}",
            )
        self.assertIn("passed", payload["summary"])

    def test_cli_json_output_machine_readable(self):
        """``--json`` prints exactly one line of machine-readable
        JSON."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            return_code = cmd_production_capability_gate(["--json"])
        output = buffer.getvalue()
        self.assertEqual(return_code, 0)
        self.assertEqual(
            len(output.strip().splitlines()), 1,
            "--json output MUST be a single line",
        )
        payload = json.loads(output)
        self.assertTrue(payload["passed"])
        self.assertIn("checks", payload)
        self.assertIn("summary", payload)

    def test_cli_failure_returns_exit_one(self):
        """A failing gate MUST exit 1 and report ``passed: false``."""
        with mock.patch(
            f"{GATE_MODULE}.is_docling_available",
            return_value=False,
        ):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                return_code = cmd_production_capability_gate()
        output = buffer.getvalue()
        self.assertEqual(return_code, 1)
        self.assertIn('"passed": false', output)
        payload = json.loads(output)
        self.assertFalse(payload["passed"])


if __name__ == "__main__":
    unittest.main()