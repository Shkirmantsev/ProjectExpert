"""Tests for the first-start wizard (open spec change PR 11).

Covers the ``one-command-production-ux`` spec delta:

* the wizard renders only while ``bootstrap_state == "not-started"``;
* the schema offers the two production models (EmbeddingGemma 2 and
  Qwen3-Embedding-0.6B), the auto/CPU/GPU device choices, the Docling
  toggle and a single ``initialise_and_build_index`` action;
* ``submit`` rejects an unknown model and returns valid settings for
  a valid form.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from pi_platform.core.control.retrieval_settings import (
    RetrievalSettings,
    load_retrieval_settings,
    save_retrieval_settings,
)
from pi_platform.core.retrieval.first_start_wizard import (
    INITIALISE_ACTION,
    FirstStartWizard,
    WizardValidationError,
)


class FirstStartWizardTestBase(unittest.TestCase):
    """Shared temp-repo fixture."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="first-start-wizard-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.wizard = FirstStartWizard()

    def _set_state(self, state: str) -> None:
        save_retrieval_settings(
            RetrievalSettings(bootstrap_state=state), self.tmp,
        )


class WizardRenderTests(FirstStartWizardTestBase):
    """The wizard renders only before initialisation."""

    def test_renders_on_fresh_install(self) -> None:
        schema = self.wizard.render(self.tmp)
        self.assertTrue(schema["visible"])
        self.assertTrue(self.wizard.should_render(self.tmp))

    def test_does_not_render_after_bootstrap_started(self) -> None:
        for state in ("provisioning", "hydrating", "indexing", "ready", "error"):
            with self.subTest(state=state):
                self._set_state(state)
                schema = self.wizard.render(self.tmp)
                self.assertFalse(schema["visible"])
                self.assertIsNone(schema["action"])
                self.assertEqual(schema["bootstrap_state"], state)
                self.assertFalse(self.wizard.should_render(self.tmp))

    def test_schema_contains_both_production_models(self) -> None:
        schema = self.wizard.render(self.tmp)
        model_ids = [c["model_id"] for c in schema["model_choices"]]
        self.assertEqual(
            model_ids,
            ["google/embeddinggemma-2", "Qwen/Qwen3-Embedding-0.6B", "openmycel/Qwen3-Embedding-0.6B-GGUF", "ggml-org/embeddinggemma-2-GGUF"],
        )
        labels = [c["label"] for c in schema["model_choices"]]
        self.assertIn("EmbeddingGemma 2", labels)
        self.assertIn("Qwen3 Embedding 0.6B", labels)

    def test_schema_device_toggle_and_single_action(self) -> None:
        schema = self.wizard.render(self.tmp)
        self.assertEqual(schema["device_choices"], ["auto", "cpu", "cuda", "vulkan"])
        self.assertIn("document_processing_enabled", schema)
        self.assertTrue(schema["document_processing_enabled"])
        self.assertIn("document_processing_available", schema)
        self.assertEqual(schema["action"], INITIALISE_ACTION)
        self.assertEqual(schema["target_repo"], str(self.tmp))


class WizardSubmitTests(FirstStartWizardTestBase):
    """``submit`` validates the form and returns valid settings."""

    def test_submit_returns_valid_settings(self) -> None:
        settings = self.wizard.submit({
            "model": "Qwen/Qwen3-Embedding-0.6B",
            "device": "cpu",
            "document_processing_enabled": False,
        })
        self.assertIsInstance(settings, RetrievalSettings)
        self.assertEqual(settings.embedding_model_alias, "qwen")
        self.assertEqual(settings.device, "cpu")
        self.assertFalse(settings.document_processing_enabled)
        self.assertEqual(settings.bootstrap_state, "not-started")
        # The returned value must be persistable as-is.
        save_retrieval_settings(settings, self.tmp)
        self.assertEqual(load_retrieval_settings(self.tmp), settings)

    def test_submit_accepts_alias_and_defaults(self) -> None:
        settings = self.wizard.submit({"model": "gemma"})
        self.assertEqual(settings.embedding_model_alias, "gemma")
        self.assertEqual(settings.device, "auto")
        self.assertTrue(settings.document_processing_enabled)

    def test_submit_rejects_unknown_model(self) -> None:
        with self.assertRaises(WizardValidationError) as ctx:
            self.wizard.submit({"model": "meta/llama-70b"})
        self.assertIn("unknown model", str(ctx.exception))

    def test_submit_rejects_missing_or_invalid_fields(self) -> None:
        for form in (
            {},
            {"model": "gemma", "device": "tpu"},
            {"model": "gemma", "document_processing_enabled": "yes"},
            "not-a-mapping",
        ):
            with self.subTest(form=form):
                with self.assertRaises(WizardValidationError):
                    self.wizard.submit(form)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()