"""External-repository regressions: real HTTP transport and stable-tree recovery."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from pi_platform.adapters.ui.http_server import UiHttpServer
from pi_platform.core.sync.version_monitor import PollingProjectVersionMonitor, read_project_version
from pi_platform.mcp.server import McpServer
from tests.test_mcp_server import _build_context


class CleanInstallTests(unittest.TestCase):
    def test_explicit_failed_refresh_retries_same_version(self):
        with tempfile.TemporaryDirectory() as raw:
            calls = []
            def refresh(event):
                calls.append(event)
                if len(calls) == 2:
                    raise RuntimeError('transient')
            monitor = PollingProjectVersionMonitor(Path(raw), on_change=refresh)
            monitor.poll_once()
            monitor.request_refresh()
            with self.assertRaises(RuntimeError):
                monitor.poll_once()
            self.assertIsNotNone(monitor.poll_once())
            self.assertEqual(len(calls), 3)
            self.assertIsNone(monitor.poll_once())

    def test_generated_sbom_does_not_invalidate_source_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / 'distribution/sbom').mkdir(parents=True)
            (root / 'distribution/source.md').write_text('real project content')
            before = read_project_version(root)
            (root / 'distribution/sbom/PROJECT-INTELLIGENCE.sbom.json').write_text('{"created":"now"}')
            self.assertEqual(before, read_project_version(root))
            (root / 'distribution/source.md').write_text('changed source')
            self.assertNotEqual(before, read_project_version(root))

    def test_protocol_and_schemas_over_real_http(self):
        with tempfile.TemporaryDirectory() as raw:
            mcp = McpServer(context=_build_context())
            server = UiHttpServer(SimpleNamespace(_repo_root=Path(raw)), mcp_server=mcp).start_background()
            self.addCleanup(server.stop)
            def request(body=None):
                req = urllib.request.Request(server.address + '/mcp',
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={'Content-Type':'application/json', 'Accept':'application/json, text/event-stream'})
                try:
                    response = urllib.request.urlopen(req)
                except urllib.error.HTTPError as exc:
                    response = exc
                with response:
                    return response.status, response.read()
            status, body = request({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26'}})
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)['result']['serverInfo']['version'])
            self.assertEqual(request({'jsonrpc':'2.0','method':'notifications/initialized'}), (202,b''))
            self.assertEqual(request()[0], 405)
            status, body = request({'jsonrpc':'2.0','id':2,'method':'tools/list'})
            tools = {t['name']:t for t in json.loads(body)['result']['tools']}
            for name, key in [('project.search','text'),('project.retrieve_context','text'),('project.get_entity','entity_id'),('project.build_task_context','goal')]:
                schema = tools[name]['inputSchema']
                self.assertIn(key, schema['required'])
                self.assertEqual(schema['properties'][key]['type'], 'string')
            status, body = request({'jsonrpc':'2.0','id':3,'method':'tools/call', 'params':{'name':'project.describe_capabilities','arguments':{}}})
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(body)['result']['isError'])

    def test_unknown_protocol_is_negotiated_not_echoed(self):
        result = McpServer(context=_build_context()).handle_jsonrpc({'id':1,'method':'initialize','params':{'protocolVersion':'9999-01-01'}})
        self.assertNotEqual(result['result']['protocolVersion'], '9999-01-01')

    def test_clean_repository_published_status_and_retry_after_edit(self):
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.core.orchestration.repository_indexing import index_repository
        from pi_platform.ports.ui.rest_api import UiActor
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {
            'PI_STARTUP_PROFILE':'minimal', 'PI_EMBEDDING_MODEL':'hashing',
            'PI_DENSE_INDEX':'flat', 'PI_DOCLING_ENABLED':'0',
        }):
            root = Path(raw)
            source = root / 'service.py'
            source.write_text('def refund(): return "first"')
            service, readiness = build_ui_service(repo_root=root, defer_runtime=True)
            def refresh(event):
                _bootstrap_and_index_target(root, service=service, readiness=readiness)
            monitor = PollingProjectVersionMonitor(root, on_change=refresh)
            # Simulate an agent editing after the candidate has read the source.
            def editing_index(**kwargs):
                runtime = index_repository(**kwargs)
                source.write_text('def refund(): return "updated"')
                return runtime
            with patch('pi_platform.core.orchestration.repository_indexing.index_repository', side_effect=editing_index):
                with self.assertRaisesRegex(RuntimeError, 'version changed'):
                    monitor.poll_once()
            self.assertFalse(readiness.is_ready())
            monitor.poll_once()
            self.assertTrue(readiness.is_ready())
            self.assertIsNone(monitor.poll_once())
            actor = UiActor(actor_type='user', actor_id='test', role='viewer')
            version = service.project_version(actor)
            self.assertEqual(version.fingerprint, read_project_version(root).working_tree_fingerprint)
            self.assertTrue(version.embedding_model_version)
            status = service.indexing_status(actor)
            self.assertGreater(status.indexes['cache_entries'], 0)
            self.assertEqual(status.indexes['canonical_cache_entries'], 0)
            self.assertTrue(status.ready)

class OfficialMcpClientTests(unittest.TestCase):
    def test_streamable_http_client_initializes_lists_and_calls(self):
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError:
            self.skipTest('optional official MCP SDK unavailable')
        import asyncio
        with tempfile.TemporaryDirectory() as raw:
            server = UiHttpServer(SimpleNamespace(_repo_root=Path(raw)), mcp_server=McpServer(context=_build_context())).start_background()
            self.addCleanup(server.stop)
            async def check():
                async with streamable_http_client(server.address + '/mcp') as (read, write, _):
                    async with ClientSession(read, write) as session:
                        initialized = await session.initialize()
                        self.assertTrue(initialized.serverInfo.version)
                        listed = await session.list_tools()
                        self.assertIn('text', next(t for t in listed.tools if t.name == 'project.search').inputSchema['required'])
                        result = await session.call_tool('project.describe_capabilities', {})
                        self.assertFalse(result.isError)
            asyncio.run(check())


class ModelCacheTests(unittest.TestCase):
    def test_cleanup_preserves_recent_locked_and_complete_downloads(self):
        from pi_platform.adapters.retrieval.model_cache import prune_incomplete
        try:
            from filelock import FileLock
        except ImportError:
            self.skipTest('optional model runtime dependency filelock unavailable')
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            blobs = root / 'hub/models--test/blobs'
            blobs.mkdir(parents=True)
            for name in ('old.incomplete', 'active.incomplete', 'recent.incomplete', 'complete'):
                (blobs / name).write_bytes(b'1234')
                os.utime(blobs / name, (0, 0))
            os.utime(blobs / 'recent.incomplete', (100000,100000))
            lock = root / 'hub/.locks/models--test/active.lock'
            lock.parent.mkdir(parents=True)
            with FileLock(str(lock)):
                result = prune_incomplete(root, now=100000)
            self.assertEqual(result['reclaimed_bytes'], 4)
            self.assertFalse((blobs / 'old.incomplete').exists())
            for name in ('active.incomplete','recent.incomplete','complete'):
                self.assertTrue((blobs / name).exists())


class GgufDocumentTests(unittest.TestCase):
    def test_gguf_documents_use_pinned_native_tokenizer(self):
        from pi_platform.adapters.pdf.real_docling import _resolve_tokenizer_id
        from pi_platform.adapters.retrieval.gguf_artifacts import MODEL_ID
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_resolve_tokenizer_id(MODEL_ID), 'Qwen/Qwen3-Embedding-0.6B')
            self.assertEqual(_resolve_tokenizer_id('ggml-org/embeddinggemma-2-GGUF'), 'google/embeddinggemma-2')

    def test_code_only_production_does_not_download_pdf_assets(self):
        from pi_platform.core.orchestration.repository_indexing import index_repository
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        from pi_platform.core.control.retrieval_settings import load_retrieval_settings
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {
            'PI_STARTUP_PROFILE':'production','PI_EMBEDDING_MODEL':'qwen-gguf',
            'PI_DENSE_INDEX':'usearch','PI_DOCLING_ENABLED':'1','PI_PREPARE_DOCLING':'1',
        }):
            root = Path(raw)
            (root/'service.py').write_text('def refund(): return 1')
            # Stop at retrieval composition; parsing/setup before it must not fetch PDF assets.
            with patch('pi_platform.adapters.pdf.real_docling._pinned_pdf_assets') as assets, patch('pi_platform.core.orchestration.repository_indexing.build_production_retrieval_runtime', side_effect=RuntimeError('composition reached')):
                with self.assertRaisesRegex(RuntimeError, 'composition reached'):
                    index_repository(target=root, cache_root=root/'.project-intelligence-cache', inventory=RepositorySourceDiscovery().discover(root), previous_inventory=None, settings=load_retrieval_settings(root))
            assets.assert_not_called()


if __name__ == '__main__':
    unittest.main()
