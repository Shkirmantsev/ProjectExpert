"""Opt-in real Q4/USearch acceptance; requires the pinned llama.cpp runtime."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('PI_RUN_GGUF_TESTS') == '1', 'set PI_RUN_GGUF_TESTS=1 with the pinned Q4 endpoint')
class Q4RuntimeTests(unittest.TestCase):
    def test_external_repository_java_index_search_and_restart(self):
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.ports.ui.rest_api import UiActor, RetrieveRequest
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {
            'PI_STARTUP_PROFILE':'production', 'PI_EMBEDDING_MODEL':'qwen-gguf',
            'PI_EMBEDDING_DEVICE':'cpu', 'PI_DENSE_INDEX':'usearch',
            'PI_DOCLING_ENABLED':'1', 'PI_PREPARE_DOCLING':'1',
            'PI_DOCLING_CACHE':str(Path(raw)/'unused-document-assets'),
        }):
            root = Path(raw)
            (root/'README.md').write_text('# Billing\nThe billing service reconciles invoices and authorizes refunds.')
            (root/'RefundService.java').write_text('package billing; public class RefundService { public int refundInvoice() { return 1; } }')
            service, readiness = build_ui_service(repo_root=root, defer_runtime=True)
            started = time.monotonic()
            first = _bootstrap_and_index_target(root, service=service, readiness=readiness)
            first_elapsed = time.monotonic()-started
            self.assertTrue(first['ready'])
            self.assertGreater(first['new_vectors'], 0)
            self.assertEqual(service._retrieval.runtime.extra['source_failures'], [])
            self.assertFalse((root/'unused-document-assets').exists())
            actor = UiActor(actor_type='human', actor_id='test', role='viewer')
            result = service.retrieve(actor, RetrieveRequest(text='How are invoice refunds handled?'))
            self.assertTrue(result.results)
            self.assertGreater(service.indexing_status(actor).indexes['cache_entries'], 0)
            # A fresh composition reuses persisted vectors rather than embedding again.
            restarted, restarted_readiness = build_ui_service(repo_root=root, defer_runtime=True)
            second = _bootstrap_and_index_target(root, service=restarted, readiness=restarted_readiness)
            self.assertTrue(second['ready'])
            self.assertEqual(second['new_vectors'], 0)
            self.assertGreater(second['reused_vectors'], 0)
            (root/'README.md').write_text('# Billing\nUpdated refund policy requires a billing approval.')
            third = _bootstrap_and_index_target(root, service=restarted, readiness=restarted_readiness)
            self.assertTrue(third['ready'])
            self.assertGreater(third['new_vectors'], 0)
            print(f'Q4 acceptance: first indexing {first_elapsed:.2f}s; {first["new_vectors"]} vectors; restart reused {second["reused_vectors"]}; edit refresh ready')
