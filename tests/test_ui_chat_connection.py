"""Optional chat and effective mode regressions using an HTTP provider fixture."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
import urllib.request


class ChatSettingsPortabilityTests(unittest.TestCase):
    def test_save_without_posix_permission_api(self):
        from pi_platform.adapters.orchestration import chat_connection as module
        with tempfile.TemporaryDirectory() as raw:
            connection = module.ChatConnection(raw)
            # Windows 3.11 has no fchmod; Windows modes are not POSIX ACLs.
            windows_os = SimpleNamespace(name='nt', fdopen=os.fdopen,
                replace=os.replace, path=os.path, unlink=os.unlink)
            with patch.object(module, 'os', windows_os):
                result = connection.save({'model': 'portable-model'})
            self.assertEqual(result['model'], 'portable-model')
            self.assertEqual(module.ChatConnection(raw).public_settings()['model'], 'portable-model')
            self.assertEqual(list(Path(raw).glob('.chat-settings-*')), [])

    @unittest.skipUnless(os.name == 'posix', 'POSIX permission failure regression')
    def test_permission_failure_closes_tempfile_and_preserves_saved_settings(self):
        from pi_platform.adapters.orchestration import chat_connection as module
        with tempfile.TemporaryDirectory() as raw:
            connection = module.ChatConnection(raw)
            connection.save({'model': 'original'})
            original = connection.path.read_bytes()
            created = []
            mkstemp = tempfile.mkstemp
            def capture_tempfile(*args, **kwargs):
                result = mkstemp(*args, **kwargs)
                created.append(result)
                return result
            with patch.object(module.tempfile, 'mkstemp', side_effect=capture_tempfile), \
                 patch.object(module.os, 'fchmod', side_effect=PermissionError('fixture denial')):
                with self.assertRaises(PermissionError):
                    connection.save({'model': 'replacement'})
            self.assertEqual(connection.path.read_bytes(), original)
            self.assertEqual(list(Path(raw).glob('.chat-settings-*')), [])
            with self.assertRaises(OSError):
                os.fstat(created[0][0])


class ChatConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.seen=[]
        seen=self.seen
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append((self.path,data,dict(self.headers)))
                if data['model']=='bad':
                    self.send_error(401,'sensitive provider detail');return
                body=({'content':[{'type':'text','text':'Grounded answer [1]'}]} if self.path.endswith('/messages') else {'choices':[{'message':{'content':'Grounded answer [1]'}}]})
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(body).encode())
        self.provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        threading.Thread(target=self.provider.serve_forever,daemon=True).start()
        self.addCleanup(self.provider.server_close);self.addCleanup(self.provider.shutdown)
        self.base=f'http://127.0.0.1:{self.provider.server_port}/v1'

    def connection(self):
        from pi_platform.adapters.orchestration.chat_connection import ChatConnection
        return ChatConnection(self.root)

    def settings(self,**kw):
        return dict(enabled=True,provider='openai',base_url=self.base,model='fixture',share_context=True,api_key='secret-fixture',**kw)

    def test_save_is_persistent_redacted_and_owner_only(self):
        c=self.connection();public=c.save(self.settings())
        self.assertNotIn('secret-fixture',json.dumps(public));self.assertTrue(public['api_key_set'])
        self.assertEqual(self.connection().public_settings()['model'],'fixture')
        if os.name == 'posix':
            self.assertEqual((c.path.stat().st_mode & 0o777),0o600)
        c.save({'model':'updated','api_key':''})
        self.assertTrue(c.public_settings()['api_key_set'])
        c.save({'clear_api_key':True});self.assertFalse(c.public_settings()['api_key_set'])

    def test_provider_payload_and_diagnostic_do_not_expose_keys(self):
        for provider in ('openai','anthropic'):
            c=self.connection();s=self.settings();s['provider']=provider;c.save(s)
            self.assertTrue(c.test()['ok'])
            path,payload,headers=self.seen[-1]
            self.assertEqual(payload['model'],'fixture');self.assertFalse(payload.get('stream',False))
            self.assertEqual(path,'/v1/messages' if provider=='anthropic' else '/v1/chat/completions')
            self.assertEqual(payload['max_tokens'],32)
        c.save({'model':'bad'})
        result=c.test();self.assertFalse(result['ok']);self.assertNotIn('secret-fixture',json.dumps(result));self.assertIn('401',result['message'])

    def test_optional_grounded_query_and_fallback_keep_retrieval_independent(self):
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.ports.ui.rest_api import UiActor,QueryRequest,RetrieveRequest
        (self.root/'billing.md').write_text('# Billing\nQuasar refunds require an invoice.')
        with patch.dict(os.environ,{'PI_STARTUP_PROFILE':'minimal','PI_EMBEDDING_MODEL':'hashing','PI_DENSE_INDEX':'flat','PI_DOCLING_ENABLED':'0'}):
            service,ready=build_ui_service(repo_root=self.root,defer_runtime=True)
            _bootstrap_and_index_target(self.root,service=service,readiness=ready)
            service._chat_connection.save(self.settings())
            actor=UiActor('human','test','viewer')
            answer=service.query(actor,QueryRequest('Quasar refund'))
            self.assertEqual(answer.answer,'Grounded answer [1]')
            self.assertTrue(answer.results)
            self.assertIn('invoice',json.dumps(self.seen[-1][1]))
            count=len(self.seen);service.retrieve(actor,RetrieveRequest('Quasar refund'))
            self.assertEqual(len(self.seen),count)
            service._chat_connection.save({'model':'bad'})
            failed=service.query(actor,QueryRequest('Quasar refund'))
            self.assertIsNone(failed.answer);self.assertTrue(failed.results)
            self.assertTrue(any('401' in e for e in failed.explanations))
            service._chat_connection.save({'enabled':False})
            count=len(self.seen);self.assertIsNone(service.query(actor,QueryRequest('refund')).answer)
            self.assertEqual(count,len(self.seen))
            service._chat_connection.save({'enabled':True,'model':'fixture'})
            from pi_platform.ports import RuntimeNotReadyError
            with patch.object(service._chat_connection,'enhance',side_effect=lambda result: (setattr(service._retrieval,'runtime',object()) or result)):
                with self.assertRaises(RuntimeNotReadyError):
                    service.query(actor,QueryRequest('refund'))

    def test_admin_http_configuration_test_and_openwebui_share_connection(self):
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.adapters.ui.http_server import UiHttpServer
        from pi_platform.adapters.ui.openai_compat import OpenAiCompatShim
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.ports.ui.rest_api import UiActor, QueryRequest
        import urllib.error
        (self.root/'billing.md').write_text('# Billing\nQuasar refunds require invoices.')
        with patch.dict(os.environ,{'PI_STARTUP_PROFILE':'minimal','PI_EMBEDDING_MODEL':'hashing','PI_DENSE_INDEX':'flat','PI_DOCLING_ENABLED':'0'}):
            service,ready=build_ui_service(repo_root=self.root,defer_runtime=True)
            _bootstrap_and_index_target(self.root,service=service,readiness=ready)
            actor=UiActor('human','test','viewer')
            shim=OpenAiCompatShim(lambda prompt: service.query(actor,QueryRequest(prompt)))
            server=UiHttpServer(service,readiness=ready.is_ready,openai_compat=shim,token='ui-access').start_background()
            self.addCleanup(server.stop)
            def request(path,method='GET',body=None,**headers):
                req=urllib.request.Request(server.address+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','Authorization':'Bearer ui-access',**headers})
                return urllib.request.urlopen(req)
            with self.assertRaises(urllib.error.HTTPError) as err:
                request('/api/v1/admin/chat','PUT',self.settings(),**{'X-Actor-Role':'coding-agent'})
            self.assertEqual(err.exception.code,403)
            with request('/api/v1/admin/chat','PUT',self.settings()) as response:
                self.assertNotIn('secret-fixture',response.read().decode())
            with request('/api/v1/admin/chat') as response:
                self.assertTrue(json.load(response)['api_key_set'])
            with request('/api/v1/admin/chat/test','POST',{}) as response:
                self.assertTrue(json.load(response)['ok'])
            with request('/v1/chat/completions','POST',{'messages':[{'role':'user','content':'Quasar refund'}],'stream':True}) as response:
                self.assertIn('Grounded answer [1]',response.read().decode())
            service._chat_connection.save({'model':'bad'})
            with request('/v1/chat/completions','POST',{'messages':[{'role':'user','content':'Quasar refund'}]}) as response:
                content=json.load(response)['choices'][0]['message']['content']
                self.assertIn('401',content);self.assertIn('Quasar',content)
            with self.assertRaises(urllib.error.HTTPError) as err:
                request('/v1/chat/completions','POST',{},**{'X-ProjectExpert-Chat':'1'})
            self.assertEqual(err.exception.code,400)

    def test_remote_context_needs_scoped_operator_approval_and_classification(self):
        c=self.connection();c.save(self.settings())
        settings=c._settings();settings['base_url']='https://api.example.invalid/v1'
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"choices":[{"message":{"content":"answer"}}]}'
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=response
            self.assertEqual(c._complete(settings,'context',classification='INTERNAL'),'answer')
            self.assertTrue(c._egress._decisions[-1].request.approval_token)
            with self.assertRaisesRegex(Exception,'egress policy'):
                c._complete(settings,'secret',classification='CONFIDENTIAL')
            self.assertEqual(opener.return_value.open.call_count,1)

    def test_context_egress_denial_does_not_send_or_drop_evidence(self):
        from pi_platform.adapters.orchestration.chat_connection import ChatConnectionError
        c=self.connection();c.save(self.settings())
        with patch.object(c._egress,'evaluate',return_value=SimpleNamespace(allowed=False)):
            with self.assertRaises(ChatConnectionError): c._complete(c._settings(),'private context')
        self.assertEqual(self.seen,[])

    def test_requires_context_consent_and_valid_url(self):
        c=self.connection()
        for patch_data in ({'share_context':False},{'base_url':'file:///tmp/model'},{'base_url':'http://user:pass@localhost/v1'}):
            data=self.settings();data.update(patch_data)
            with self.assertRaises(ValueError):c.save(data)


class EffectiveModeTests(unittest.TestCase):
    def test_managed_backend_is_separate_from_requested_auto(self):
        from pi_platform.adapters.ui.execution_status import embedding_execution_status
        model=SimpleNamespace(stats=lambda:{'requested_device':'auto','backend':'llama.cpp'})
        for backend,mode in [('cpu','CPU'),('vulkan','Hybrid'),('cuda','Hybrid')]:
            with patch.dict(os.environ,{'PI_INFERENCE_BACKEND':backend,'PI_GPU_DEVICE':'GPU0'}):
                status=embedding_execution_status(model)
            self.assertEqual(status['mode'],mode);self.assertEqual(status['backend'],backend)
            self.assertEqual(status['requested_device'],'auto')
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(embedding_execution_status(model)['mode'],'Unknown')
        with patch.dict(os.environ,{'PI_LLAMA_ENDPOINT':'http://embeddings:8769','PI_EMBEDDING_DEVICE':'cpu'},clear=True):
            self.assertEqual(embedding_execution_status(model)['mode'],'CPU')

    def test_native_actual_device_not_requested_value(self):
        from pi_platform.adapters.ui.execution_status import embedding_execution_status
        model=SimpleNamespace(stats=lambda:{'effective_device':'cuda','requested_device':'auto','backend':'native'})
        self.assertEqual(embedding_execution_status(model)['mode'],'GPU')
