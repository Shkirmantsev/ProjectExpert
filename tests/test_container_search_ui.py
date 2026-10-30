"""Container search regressions, with controlled embeddings (no model quality claim)."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import urllib.request
import urllib.error

from pi_platform.adapters.ui.composition import build_ui_service
from pi_platform.adapters.ui.http_server import UiHttpServer
from pi_platform.adapters.ui.openai_compat import OpenAiCompatShim
from pi_platform.cli.main import _bootstrap_and_index_target
from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
from pi_platform.core.sync.version_monitor import read_project_version
from pi_platform.ports.ui.rest_api import UiActor, RetrieveRequest, QueryRequest


class ContainerSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'PI_STARTUP_PROFILE':'minimal',
            'PI_EMBEDDING_MODEL':'hashing','PI_DENSE_INDEX':'flat','PI_DOCLING_ENABLED':'0'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.actor = UiActor('human','test','viewer')

    def test_published_sources_and_local_inbox_follow_search_generation(self):
        (self.root/'README.md').write_text('# Project\nTrade analysis and portfolio reports.')
        inbox = self.root/'tmp/local/source/customer'
        inbox.mkdir(parents=True)
        note = inbox/'brief.md'
        note.write_text('# Quasar policy\nQuasar requires evidence for portfolio reconciliation.')
        (self.root/'tmp/local/cache.md').write_text('Must not be indexed')
        service, ready = build_ui_service(repo_root=self.root, defer_runtime=True)
        _bootstrap_and_index_target(self.root,service=service,readiness=ready)
        self.assertTrue(ready.is_ready())
        hits = service.retrieve(self.actor,RetrieveRequest('Quasar')).results
        local = [h for h in hits if h.metadata.sourcePath.endswith('/tmp/local/source/customer/brief.md')]
        self.assertTrue(local)
        self.assertEqual(local[0].metadata.policy,'LOCAL_ONLY')
        catalog = service.sources(self.actor).sources
        self.assertIn('repo:README.md',{s.id for s in catalog})
        self.assertIn('tmp/local/source/customer/brief.md',{s.metadata['path'] for s in catalog})
        before = read_project_version(self.root)
        note.write_text('# Nebula\nRevised policy.')
        self.assertNotEqual(before,read_project_version(self.root))
        note.unlink()
        _bootstrap_and_index_target(self.root,service=service,readiness=ready)
        self.assertFalse(any(h.metadata.sourcePath.endswith('brief.md') for h in service.retrieve(self.actor,RetrieveRequest('Quasar')).results))
        self.assertFalse(any(s.id.endswith('brief.md') for s in service.sources(self.actor).sources))
        self.assertFalse((self.root/'project-knowledge/wiki').exists())

    def test_inbox_pdf_uses_its_larger_limit_and_skips_symlink_trees(self):
        inbox = self.root/'tmp/local/source'
        inbox.mkdir(parents=True)
        (inbox/'large.pdf').write_bytes(b'%PDF-' + b'0'*(6*1024*1024))
        outside = self.root/'outside'; outside.mkdir()
        (outside/'hidden.md').write_text('outside')
        (inbox/'linked').symlink_to(outside,target_is_directory=True)
        paths = RepositorySourceDiscovery().discover(self.root).paths()
        self.assertIn('tmp/local/source/large.pdf',paths)
        self.assertNotIn('tmp/local/source/linked/hidden.md',paths)

    def test_indexing_excludes_inbox_from_git_and_supports_configured_path(self):
        import subprocess
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        subprocess.run(['git','-C',str(self.root),'-c','user.name=Test','-c','user.email=test@example.com','commit','--allow-empty','-qm','init'],check=True)
        config=self.root/'project-knowledge/project-context.yaml'
        config.parent.mkdir()
        config.write_text('sources:\n  localInbox:\n    path: private-documents\n')
        inbox=self.root/'private-documents';inbox.mkdir()
        (inbox/'brief.md').write_text('# Private evidence\nPortfolio reconciliation.')
        service,ready=build_ui_service(repo_root=self.root,defer_runtime=True)
        _bootstrap_and_index_target(self.root,service=service,readiness=ready)
        ignored=subprocess.run(['git','-C',str(self.root),'check-ignore','private-documents/brief.md'],capture_output=True,text=True)
        self.assertEqual(ignored.returncode,0)
        self.assertTrue(any(s.policy=='LOCAL_ONLY' and s.id.endswith('brief.md') for s in service.sources(self.actor).sources))

    def test_unready_http_preserves_actual_failure(self):
        service, ready = build_ui_service(repo_root=self.root,defer_runtime=True)
        ready.record_failure('Embedding server refused connection'); ready.end_refresh()
        server = UiHttpServer(service,readiness=ready.is_ready).start_background()
        self.addCleanup(server.stop)
        req = urllib.request.Request(server.address+'/api/v1/retrieve',data=b'{"text":"test"}',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as ctx: urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code,503)
        self.assertIn('Embedding server refused connection',ctx.exception.read().decode())

    def test_sse_search_is_usable_without_chat_model(self):
        result = SimpleNamespace(answer=None,results=(SimpleNamespace(snippet='Quasar policy',metadata=SimpleNamespace(sourcePath='brief.md')),))
        shim = OpenAiCompatShim(lambda _:result)
        server = UiHttpServer(SimpleNamespace(_repo_root=self.root),readiness=lambda:True,openai_compat=shim).start_background()
        self.addCleanup(server.stop)
        req = urllib.request.Request(server.address+'/v1/chat/completions',data=json.dumps({'stream':True,'messages':[{'role':'user','content':'Quasar'}]}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:
            self.assertIn('text/event-stream',response.headers['Content-Type'])
            body = response.read().decode()
        self.assertIn('Quasar policy',body)
        self.assertIn('brief.md',body)
        self.assertTrue(body.endswith('data: [DONE]\n\n'))

    def test_delegation_cannot_report_success_for_retrieval_only(self):
        service, _ = build_ui_service(repo_root=self.root,defer_runtime=True)
        from pi_platform.ports.ui.rest_api import AgentDelegationRequest
        with patch.object(service,'_authorise'), patch.object(service._egress,'evaluate',return_value=SimpleNamespace(allowed=True)):
            result=service.agent_delegation(self.actor,AgentDelegationRequest(task='Explain project'))
        self.assertEqual(result.status,'unavailable')


@unittest.skipUnless(os.environ.get('PI_RUN_INBOX_MODEL_TESTS') == '1',
                     'requires managed Gemma endpoint and cached Docling assets')
class RealInboxModelTests(unittest.TestCase):
    def test_pdf_in_ignored_inbox_is_searchable_with_real_embeddings(self):
        from scripts.generate_pdf_fixtures import build_pdf
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            pdf=root/'tmp/local/source/reports/brief.pdf'
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(build_pdf(page_count=1,title='QUASAR PORTFOLIO RECONCILIATION'))
            original=pdf.read_bytes()
            service,ready=build_ui_service(repo_root=root,defer_runtime=True)
            summary=_bootstrap_and_index_target(root,service=service,readiness=ready)
            self.assertTrue(summary['ready'])
            self.assertEqual(summary['source_failures'],[])
            self.assertGreater(summary['new_vectors'],0)
            hits=service.retrieve(UiActor('human','test','viewer'),RetrieveRequest('Quasar portfolio reconciliation')).results
            self.assertTrue(hits)
            self.assertTrue(any(h.metadata.sourcePath.endswith('brief.pdf') for h in hits))
            self.assertTrue(all(h.metadata.policy=='LOCAL_ONLY' for h in hits))
            self.assertEqual(pdf.read_bytes(),original)
            self.assertFalse((root/'project-knowledge/wiki').exists())
