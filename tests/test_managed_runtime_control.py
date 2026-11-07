"""UI runtime control regressions; subprocess and hardware are controlled fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class RuntimeControlTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'Bundle is provisioned only inside Linux containers')
    def test_controller_python_bundle_excludes_application_dependencies(self):
        from pi_platform.cli.runtime_python import bundle_python
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);stdlib=root/'stdlib';stdlib.mkdir()
            (stdlib/'json.py').write_text('fixture standard library')
            (stdlib/'site-packages').mkdir()
            (stdlib/'site-packages'/'large-model.py').write_text('not a runtime dependency')
            binary=root/'python';binary.write_bytes(b'fixture executable')
            library=root/'libpython.so.1';library.write_bytes(b'fixture shared runtime')
            output=root/'models'
            bundle_python(output, executable=binary, stdlib=stdlib, library=library, version='3.11')
            self.assertTrue((output/'runtime-python/bin/python3').is_file())
            self.assertTrue((output/'runtime-python/lib/python3.11/json.py').is_file())
            self.assertFalse((output/'runtime-python/lib/python3.11/site-packages').exists())

    def supervisor(self):
        spec = importlib.util.spec_from_file_location('runtime_supervisor',
            Path(__file__).resolve().parents[1] / 'distribution/deployment/runtime_supervisor.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_failed_gpu_start_restores_previous_child(self):
        controller=self.supervisor().Supervisor(['--model', '/models/fixed.gguf'])
        with patch.object(controller, 'probe', return_value='  Vulkan0: Test GPU'), \
             patch.object(controller, 'start', side_effect=[RuntimeError('Fixture startup failed'), None]) as start:
            with self.assertRaisesRegex(RuntimeError, 'previous device restored'):
                controller.configure({'device':'Vulkan0','fit_target':192})
            self.assertEqual(start.call_args_list[-1].args, ('none',192))
            self.assertFalse(controller.applying)
        with self.assertRaises(ValueError): controller.configure({'device':'none','command':'unsafe'})

    def test_supervisor_honors_initial_launch_fit_budget(self):
        controller=self.supervisor().Supervisor(['--device','Vulkan0','--fit-target','384'])
        self.assertEqual(controller.fit_target,384)

    def test_auto_benchmarks_and_keeps_cpu_when_gpu_is_slower(self):
        from pi_platform.adapters.orchestration.managed_runtime import apply_selection
        state=dict(generation='one', backend='vulkan', device='none', ready=True,
                   devices='  Vulkan0: Test GPU')
        changes=[]
        def transport(method, body=None):
            if method == 'PUT':
                changes.append(body['device']);state['device']=body['device'];state['generation']+='x'
            return dict(state)
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {'PI_RUNTIME_CONTROL_URL':'http://embeddings:8770'}):
            timings=iter([100,120])
            result=apply_selection(Path(raw),'gemma','auto',transport=transport,measure=lambda:next(timings))
            self.assertEqual(result['mode'],'CPU')
            self.assertEqual(changes,['none','Vulkan0','none'])
            self.assertIn('not faster',result['rejected'][0]['reason'])

    def test_device_override_preserves_model_capacity_and_cpu_projector(self):
        spec = importlib.util.spec_from_file_location('runtime_supervisor',
            Path(__file__).resolve().parents[1] / 'distribution/deployment/runtime_supervisor.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = ['--model', '/models/fixed.gguf', '--ctx-size', '4096', '--device', 'Vulkan0',
                '--fit', 'on', '--fit-target', '192', '--no-mmproj-offload']
        cpu = module.server_arguments(args, 'none', 192)
        self.assertEqual(cpu[cpu.index('--device') + 1], 'none')
        self.assertNotIn('--fit', cpu)
        self.assertEqual(cpu[cpu.index('--ctx-size') + 1], '4096')
        self.assertEqual(cpu.count('--no-mmproj-offload'), 1)
        gpu = module.server_arguments(cpu, 'Vulkan0', 256)
        self.assertEqual(gpu[gpu.index('--fit-target') + 1], '256')
        with self.assertRaises(ValueError): module.server_arguments(args, '--model=evil', 192)

    def test_explicit_unavailable_gpu_does_not_silently_claim_success(self):
        from pi_platform.adapters.orchestration.managed_runtime import apply_selection
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {
            'PI_RUNTIME_CONTROL_URL': 'http://embeddings:8770', 'PI_LLAMA_API_KEY_FILE': ''}):
            transport = lambda method, body=None: {'generation': 'one', 'backend': 'vulkan',
                'device': 'none', 'ready': True, 'devices': ''}
            with self.assertRaisesRegex(RuntimeError, 'GPU|device'):
                apply_selection(Path(raw), 'gemma', 'vulkan', transport=transport)

    def test_selection_is_applied_cached_and_reapplied_after_sidecar_restart(self):
        from pi_platform.adapters.orchestration.managed_runtime import apply_selection
        state = dict(generation='one', backend='vulkan', device='none', ready=True,
                     devices='  Vulkan0: Test GPU (4096 MiB, 3072 MiB free)')
        changes = []
        def transport(method, body=None):
            if method == 'PUT':
                changes.append(body); state['device'] = body['device']; state['generation'] += 'x'
            return dict(state)
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {'PI_RUNTIME_CONTROL_URL':'http://embeddings:8770'}):
            root=Path(raw)
            self.assertEqual(apply_selection(root, 'gemma', 'vulkan', transport=transport)['mode'], 'Hybrid')
            self.assertEqual(len(changes), 1)
            apply_selection(root, 'gemma', 'vulkan', transport=transport)
            self.assertEqual(len(changes), 1)
            state['generation']='restarted'; state['device']='none'
            apply_selection(root, 'gemma', 'vulkan', transport=transport)
            self.assertEqual(len(changes), 2)

    def test_ui_selection_survives_application_restart(self):
        from pi_platform.adapters.ui.http_server import UiHttpServer
        with tempfile.TemporaryDirectory() as raw:
            service=SimpleNamespace(_repo_root=Path(raw))
            server=UiHttpServer(service)
            settings=SimpleNamespace(embedding_model_alias='gemma-torch', device='cpu', document_processing_enabled=False)
            server.apply_runtime_settings(settings, ['embedding_model_alias','device'])
            restarted=SimpleNamespace(_repo_root=Path(raw))
            UiHttpServer(restarted)
            self.assertEqual(restarted._runtime_overrides, {'embedding_model':'gemma-torch','embedding_device':'cpu'})

    def test_binding_selection_reaches_factory_and_published_index(self):
        from pi_platform.adapters.ui.http_server import UiHttpServer
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.core.retrieval.embedding_model import HashingEmbeddingModel
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {
                'PI_STARTUP_PROFILE':'minimal','PI_EMBEDDING_MODEL':'hashing',
                'PI_DENSE_INDEX':'flat','PI_DOCLING_ENABLED':'0'}):
            root=Path(raw)
            (root/'README.md').write_text('# Quasar\nPortfolio evidence')
            service,ready=build_ui_service(repo_root=root,defer_runtime=True)
            server=UiHttpServer(service)
            server.apply_runtime_settings(SimpleNamespace(embedding_model_alias='gemma-torch',
                device='cpu',document_processing_enabled=False), ['embedding_model_alias','device'])
            with patch('pi_platform.adapters.retrieval.embedding_model_factory.EmbeddingModelFactory.build',
                       return_value=HashingEmbeddingModel(model_version='native-binding-fixture')) as factory:
                summary=_bootstrap_and_index_target(root,service=service,readiness=ready)
            self.assertTrue(summary['ready'])
            self.assertEqual(summary['active_model'],'gemma-torch')
            self.assertTrue(any(call.args[0] == 'gemma-torch' and call.kwargs['device'] == 'cpu'
                                for call in factory.call_args_list))

    def test_auth_metadata_is_public_but_never_returns_the_token(self):
        import urllib.request
        from pi_platform.adapters.ui.http_server import UiHttpServer
        with tempfile.TemporaryDirectory() as raw:
            server=UiHttpServer(SimpleNamespace(_repo_root=Path(raw)), token='fixture-secret').start_background()
            self.addCleanup(server.stop)
            with urllib.request.urlopen(server.address+'/api/v1/auth-status') as response:
                result=response.read().decode()
            self.assertTrue(json.loads(result)['token_required'])
            self.assertNotIn('fixture-secret', result)

    def test_wizard_applies_via_observable_job_and_reloads_saved_intent(self):
        import threading
        import urllib.request
        from pi_platform.adapters.ui.http_server import UiHttpServer
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {'PI_LLAMA_ENDPOINT':'http://embeddings:8769',
                'PI_RUNTIME_CONTROL_URL':'http://embeddings:8770'}):
            service=SimpleNamespace(_repo_root=Path(raw))
            server=UiHttpServer(service, token='fixture-secret').start_background()
            self.addCleanup(server.stop)
            applied=threading.Event()
            server.admin_routes.job_executor=lambda kind, details: applied.set()
            data=json.dumps({'embedding_model_alias':'gemma','device':'vulkan','document_processing_enabled':False}).encode()
            request=urllib.request.Request(server.address+'/api/v1/wizard', data=data,
                headers={'Authorization':'Bearer fixture-secret','Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status,202)
                job=json.load(response)
            self.assertTrue(applied.wait(2))
            self.assertIn('job_id',job)
            self.assertEqual(service._runtime_overrides['embedding_device'],'vulkan')

    def test_observed_status_not_stale_after_supervisor_restart(self):
        from pi_platform.adapters.orchestration import managed_runtime as module
        saved=dict(mode='Hybrid', backend='vulkan', generation='old', device='Vulkan0')
        with patch.object(module,'transport',return_value=dict(generation='new',device='none',backend='vulkan',ready=True)):
            self.assertEqual(module.observed_execution(saved)['mode'],'CPU')
