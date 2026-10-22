"""Tests for the retrieval settings module (open spec change PR 11).

Covers the ``one-command-production-ux`` spec delta: the model
selection lives in ``.project-intelligence-cache/retrieval-settings.json``
(never in canonical Git), defaults to the documented production
values, round-trips through save/load, rejects malformed payloads and
is written atomically so a crash mid-write can never leave a
truncated file behind.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pi_platform.core.control.retrieval_settings import (
    BOOTSTRAP_STATES,
    CACHE_DIR_NAME,
    DEFAULT_BOOTSTRAP_STATE,
    DEFAULT_DEVICE,
    DEFAULT_MODEL_ALIAS,
    DEVICE_CHOICES,
    PRODUCTION_MODEL_CHOICES,
    SETTINGS_FILE_NAME,
    RetrievalSettings,
    RetrievalSettingsError,
    load_retrieval_settings,
    retrieval_settings_path,
    save_retrieval_settings,
    validate_retrieval_settings,
)


class RetrievalSettingsTestBase(unittest.TestCase):
    """Shared temp-repo fixture."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="retrieval-settings-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.settings_file = retrieval_settings_path(self.tmp)


class LoadDefaultsTests(RetrievalSettingsTestBase):
    """A fresh install falls back to the documented defaults."""

    def test_load_defaults_when_file_absent(self) -> None:
        settings = load_retrieval_settings(self.tmp)
        self.assertEqual(settings.embedding_model_alias, DEFAULT_MODEL_ALIAS)
        self.assertEqual(settings.model_id, "google/embeddinggemma-2")
        self.assertEqual(settings.device, DEFAULT_DEVICE)
        self.assertTrue(settings.document_processing_enabled)
        self.assertEqual(settings.bootstrap_state, "not-started")
        self.assertFalse(self.settings_file.exists())

    def test_defaults_are_the_production_documented_values(self) -> None:
        settings = RetrievalSettings()
        self.assertIn(settings.embedding_model_alias, ("gemma", "qwen"))
        self.assertIn(settings.model_id, PRODUCTION_MODEL_CHOICES)
        self.assertIn(settings.device, DEVICE_CHOICES)
        self.assertIn(settings.bootstrap_state, BOOTSTRAP_STATES)


class SaveLoadTests(RetrievalSettingsTestBase):
    """Save is atomic and the save/load round trip is lossless."""

    def test_save_writes_atomically_without_temp_residue(self) -> None:
        settings = RetrievalSettings(
            embedding_model_alias="qwen",
            device="cpu",
            document_processing_enabled=False,
            bootstrap_state="provisioning",
        )
        path = save_retrieval_settings(settings, self.tmp)

        self.assertEqual(path, self.settings_file)
        self.assertTrue(self.settings_file.is_file())
        tmp_file = self.settings_file.with_name(
            self.settings_file.name + ".tmp",
        )
        self.assertFalse(tmp_file.exists())
        payload = json.loads(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(payload, settings.as_dict())

    def test_load_after_save_round_trips(self) -> None:
        settings = RetrievalSettings(
            embedding_model_alias="qwen",
            device="cuda",
            document_processing_enabled=False,
            bootstrap_state="indexing",
        )
        save_retrieval_settings(settings, self.tmp)
        loaded = load_retrieval_settings(self.tmp)
        self.assertEqual(loaded, settings)
        self.assertEqual(loaded.model_id, "Qwen/Qwen3-Embedding-0.6B")

    def test_model_id_input_is_normalised_to_alias(self) -> None:
        settings = RetrievalSettings(
            embedding_model_alias="Qwen/Qwen3-Embedding-0.6B",
        )
        self.assertEqual(settings.embedding_model_alias, "qwen")
        save_retrieval_settings(settings, self.tmp)
        self.assertEqual(
            load_retrieval_settings(self.tmp).embedding_model_alias, "qwen",
        )

    def test_crash_mid_write_leaves_previous_settings_unchanged(
        self,
    ) -> None:
        original = RetrievalSettings(device="cpu")
        save_retrieval_settings(original, self.tmp)
        before = self.settings_file.read_text(encoding="utf-8")

        # Crash exactly at the commit point: the .tmp payload exists
        # but os.replace never runs.
        with mock.patch(
            "pi_platform.core.control.retrieval_settings.os.replace",
            side_effect=OSError("simulated crash before commit"),
        ):
            with self.assertRaises(RetrievalSettingsError):
                save_retrieval_settings(
                    RetrievalSettings(device="cuda"), self.tmp,
                )
        self.assertEqual(
            self.settings_file.read_text(encoding="utf-8"), before,
        )
        self.assertFalse(
            self.settings_file.with_name(
                self.settings_file.name + ".tmp",
            ).exists()
        )

        # Crash while flushing the temporary file (partial write).
        with mock.patch(
            "pi_platform.core.control.retrieval_settings.os.fsync",
            side_effect=OSError("simulated crash mid-write"),
        ):
            with self.assertRaises(RetrievalSettingsError):
                save_retrieval_settings(
                    RetrievalSettings(device="cuda"), self.tmp,
                )
        self.assertEqual(
            self.settings_file.read_text(encoding="utf-8"), before,
        )
        self.assertEqual(load_retrieval_settings(self.tmp), original)


class SchemaValidationTests(RetrievalSettingsTestBase):
    """Malformed payloads are rejected instead of silently defaulted."""

    def test_validate_rejects_unknown_keys(self) -> None:
        with self.assertRaises(RetrievalSettingsError) as ctx:
            validate_retrieval_settings({"colour": "blue"})
        self.assertIn("unknown retrieval settings keys", str(ctx.exception))

    def test_validate_rejects_unknown_model_device_and_state(self) -> None:
        for patch in (
            {"embedding_model_alias": "llama-70b"},
            {"device": "tpu"},
            {"bootstrap_state": "booting"},
            {"document_processing_enabled": "yes"},
        ):
            with self.subTest(patch=patch):
                with self.assertRaises(RetrievalSettingsError):
                    validate_retrieval_settings(patch)

    def test_validate_rejects_non_object_payload(self) -> None:
        for payload in ("not-json-object", 42, None, ["gemma"]):
            with self.subTest(payload=payload):
                with self.assertRaises(RetrievalSettingsError):
                    validate_retrieval_settings(payload)

    def test_load_raises_on_corrupt_file(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text("{not json", encoding="utf-8")
        with self.assertRaises(RetrievalSettingsError):
            load_retrieval_settings(self.tmp)

    def test_load_raises_on_invalid_file_instead_of_resetting(self) -> None:
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(
            json.dumps({"embedding_model_alias": "llama-70b"}),
            encoding="utf-8",
        )
        with self.assertRaises(RetrievalSettingsError):
            load_retrieval_settings(self.tmp)

    def test_settings_path_is_under_the_runtime_cache(self) -> None:
        path = retrieval_settings_path(self.tmp)
        self.assertEqual(path.parent.name, CACHE_DIR_NAME)
        self.assertEqual(path.name, SETTINGS_FILE_NAME)


if __name__ == "__main__":
    unittest.main()