"""Observable precedence, aliases and fail-closed startup constraints."""
import json
from pathlib import Path
import tempfile
import unittest
from pi_platform.adapters.config.runtime_configuration_resolver import RuntimeConfigurationResolver, ConfigurationError


class RuntimeConfigurationTests(unittest.TestCase):
    def test_project_file_local_environment_and_cli_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'project-context.yaml').write_text('runtime:\n  embedding_model: qwen\n  embedding_device: cpu\n')
            settings = root / '.project-intelligence-cache/settings.json'
            cfg = RuntimeConfigurationResolver(env={}, local_settings_path=settings).resolve()
            self.assertEqual(cfg.embedding_model, 'qwen')
            self.assertEqual(cfg.sources['embedding_model'], 'project-context')
            settings.parent.mkdir()
            settings.write_text(json.dumps({'embedding_model': 'gemma'}))
            self.assertEqual(RuntimeConfigurationResolver(env={}, local_settings_path=settings).resolve().embedding_model, 'gemma')
            self.assertEqual(RuntimeConfigurationResolver(env={'PI_EMBEDDING_MODEL':'qwen'}, local_settings_path=settings).resolve().embedding_model, 'qwen')
            cfg = RuntimeConfigurationResolver(env={'PI_EMBEDDING_MODEL':'qwen'}, local_settings_path=settings, cli_overrides={'embedding_model':'gemma'}).resolve()
            self.assertEqual(cfg.embedding_model, 'gemma')
            self.assertEqual(cfg.sources['embedding_model'], 'cli')

    def test_minimal_is_explicit_and_does_not_select_optional_dependencies(self):
        cfg = RuntimeConfigurationResolver(env={'PI_STARTUP_PROFILE':'minimal'}).resolve()
        self.assertEqual((cfg.embedding_model,cfg.dense_index,cfg.docling_enabled), ('hashing','flat',False))
        self.assertEqual(RuntimeConfigurationResolver(env={}).resolve().startup_profile, 'production')

    def test_production_refuses_hashing_and_flat(self):
        for env in [{'PI_EMBEDDING_MODEL':'hashing'}, {'PI_DENSE_INDEX':'flat'}]:
            with self.assertRaises(ConfigurationError):
                RuntimeConfigurationResolver(env=env).resolve()

    def test_legacy_production_alias_resolves_canonically(self):
        self.assertEqual(RuntimeConfigurationResolver(env={'PI_EMBEDDING_MODEL':'qwen3'}).resolve().embedding_model, 'qwen')
