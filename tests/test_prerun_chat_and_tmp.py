"""Pre-run configuration and target-local tmp documents, no model downloads."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class PreRunChatTests(unittest.TestCase):
    def test_cli_configures_before_serve_redacts_key_and_preserves_saved_consent(self):
        from pi_platform.cli.main import main
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ,{
            'LLM_PROVIDER':'openai','LLM_URL':'http://host.docker.internal:1234/v1',
            'LLM_MODEL':'local-chat','LLM_API_KEY':'fixture-secret','LLM_SHARE_CONTEXT':'1','LLM_ENABLED':'1'}):
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(['chat','configure','--from-env','--target',raw]),0)
            self.assertNotIn('fixture-secret',out.getvalue())
            saved=Path(raw)/'.project-intelligence-cache/chat-settings.json'
            data=json.loads(saved.read_text());self.assertTrue(data['enabled']);self.assertTrue(data['share_context'])
            self.assertEqual(data['api_key'],'fixture-secret')
            if os.name == 'posix':
                self.assertEqual(saved.stat().st_mode & 0o777,0o600)
            with patch.dict(os.environ,{'LLM_PROVIDER':'','LLM_URL':'','LLM_MODEL':'','LLM_API_KEY':'','LLM_SHARE_CONTEXT':''}):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['chat','configure','--from-env','--target',raw]),0)
            with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main(['chat','disable','--target',raw]),0)
            self.assertFalse(json.loads(saved.read_text())['enabled'])
            self.assertEqual(json.loads(saved.read_text())['api_key'],'fixture-secret')

    def test_prerun_config_is_visible_and_editable_in_ui(self):
        from pi_platform.cli.main import main
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.adapters.ui.http_server import UiHttpServer
        import urllib.request
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            subprocess.run(['git','init','-q',raw],check=True)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['chat','configure','--target',raw,'--base-url','http://host.docker.internal:1234/v1','--model','before-start','--share-context']),0)
            self.assertEqual(subprocess.run(['git','-C',raw,'check-ignore','.project-intelligence-cache/chat-settings.json'],capture_output=True).returncode,0)
            service,_=build_ui_service(repo_root=root,defer_runtime=True)
            server=UiHttpServer(service).start_background();self.addCleanup(server.stop)
            with urllib.request.urlopen(server.address+'/api/v1/admin/chat') as response:
                data=json.load(response)
            self.assertEqual(data['base_url'],'http://host.docker.internal:1234/v1')
            self.assertEqual(data['model'],'before-start')
            req=urllib.request.Request(server.address+'/api/v1/admin/chat',method='PUT',data=json.dumps({'base_url':'http://updated-server:1234/v1','model':'after-ui'}).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response)['model'],'after-ui')
            out=io.StringIO()
            with contextlib.redirect_stdout(out):self.assertEqual(main(['chat','status','--target',raw]),0)
            self.assertEqual(json.loads(out.getvalue())['base_url'],'http://updated-server:1234/v1')

    @unittest.skipUnless(shutil.which('make'),'make unavailable')
    def test_make_binding_is_prerun_ordered_and_never_prints_keys(self):
        with tempfile.TemporaryDirectory() as raw:
            folder=Path(raw);shutil.copy(ROOT/'distribution/deployment/Makefile',folder/'Makefile')
            fake=folder/'compose';fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\nif [ "$FAIL_BIND" = 1 ]; then exit 7; fi\n');fake.chmod(0o755)
            env={**os.environ,'CALLS':str(folder/'calls'),'LLM_API_KEY':'fixture-secret','FAIL_BIND':'0'}
            def run(*args):return subprocess.run(['make',*args,'COMPOSE='+str(fake),'URL=true'],cwd=folder,env=env,capture_output=True,text=True)
            enabled=run('platform-start','LLM=1','LLM_URL=http://host.docker.internal:1234/v1','LLM_MODEL=local-chat','LLM_SHARE_CONTEXT=1')
            self.assertEqual(enabled.returncode,0,enabled.stderr)
            calls=(folder/'calls').read_text().splitlines()
            self.assertIn('run --rm --no-deps -T',calls[0]);self.assertIn('chat configure',calls[0]);self.assertIn('up -d --wait',calls[1])
            self.assertNotIn('fixture-secret',enabled.stdout+enabled.stderr+'\n'.join(calls))
            (folder/'calls').unlink();self.assertEqual(run('platform-start').returncode,0)
            self.assertNotIn('chat',(folder/'calls').read_text())
            (folder/'calls').unlink();self.assertEqual(run('platform-start','LLM=0').returncode,0)
            self.assertIn('chat disable',(folder/'calls').read_text().splitlines()[0])
            (folder/'calls').unlink();env['FAIL_BIND']='1'
            failed=run('platform-start','LLM=1')
            self.assertNotEqual(failed.returncode,0);self.assertNotIn('up -d',(folder/'calls').read_text())


class TmpInputTests(unittest.TestCase):
    def test_tmp_nested_documents_are_private_large_and_monitorable(self):
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        from pi_platform.core.sync.version_monitor import read_project_version
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            pdf=root/'tmp/reports/nested/big.pdf';pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b'%PDF-'+b'x'*(6*1024*1024))
            (root/'tmp/local').mkdir();(root/'tmp/local/runtime.json').write_text('{}')
            (root/'tmp/.project-intelligence-cache').mkdir();(root/'tmp/.project-intelligence-cache/chat-settings.json').write_text('{}')
            before=read_project_version(root)
            entries={e.path:e for e in RepositorySourceDiscovery().discover(root).entries}
            self.assertIn('tmp/reports/nested/big.pdf',entries)
            self.assertEqual(entries['tmp/reports/nested/big.pdf'].policy,'LOCAL_ONLY')
            self.assertNotIn('tmp/local/runtime.json',entries);self.assertNotIn('tmp/.project-intelligence-cache/chat-settings.json',entries)
            pdf.write_bytes(b'%PDF-changed');self.assertNotEqual(before,read_project_version(root))
            pdf.unlink();self.assertNotIn('tmp/reports/nested/big.pdf',RepositorySourceDiscovery().discover(root).paths())

    def test_tmp_limit_is_not_bypassed_and_tracked_documents_remain_repository_input(self):
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);subprocess.run(['git','init','-q',raw],check=True)
            config=root/'project-knowledge/project-context.yaml';config.parent.mkdir()
            config.write_text('sources:\n  localInbox:\n    maxSourceBytes: 32\n')
            tmp=root/'tmp';tmp.mkdir()
            (tmp/'too-big.md').write_text('x'*64)
            (tmp/'tracked.md').write_text('tracked evidence')
            subprocess.run(['git','-C',raw,'add','tmp/tracked.md'],check=True)
            entries={e.path:e for e in RepositorySourceDiscovery().discover(root).entries}
            self.assertNotIn('tmp/too-big.md',entries)
            self.assertIn('tmp/tracked.md',entries)
            self.assertEqual(entries['tmp/tracked.md'].policy,'')

    def test_tmp_documents_search_and_git_exclusion(self):
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.ports.ui.rest_api import UiActor,RetrieveRequest
        with tempfile.TemporaryDirectory() as raw,patch.dict(os.environ,{'PI_STARTUP_PROFILE':'minimal','PI_EMBEDDING_MODEL':'hashing','PI_DENSE_INDEX':'flat','PI_DOCLING_ENABLED':'0'}):
            root=Path(raw);subprocess.run(['git','init','-q',raw],check=True)
            subprocess.run(['git','-C',raw,'-c','user.name=Test','-c','user.email=t@example.com','commit','--allow-empty','-qm','initial'],check=True)
            p=root/'tmp/notes/brief.md';p.parent.mkdir(parents=True);p.write_text('# Quasar\nQuasar invoices require reconciliation.')
            service,ready=build_ui_service(repo_root=root,defer_runtime=True)
            _bootstrap_and_index_target(root,service=service,readiness=ready)
            hits=service.retrieve(UiActor('human','test','viewer'),RetrieveRequest('Quasar')).results
            self.assertTrue(hits);self.assertTrue(all(h.metadata.policy=='LOCAL_ONLY' for h in hits))
            self.assertEqual(subprocess.run(['git','-C',raw,'check-ignore','tmp/notes/brief.md'],capture_output=True).returncode,0)
