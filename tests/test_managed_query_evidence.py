"""Managed query-stage selection uses real repeated samples, never index claims."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.adapters.orchestration import managed_runtime
from pi_platform.core.inference.benchmark import query_workload_identity


class ManagedQueryEvidenceTests(unittest.TestCase):
    def sample(self, rate):
        return {'median_ms':1000/rate, 'completed_per_second':[rate]*3,
                'workload_identity':query_workload_identity(), 'stage':'query_embedding',
                'probe_vectors':[[1. if i == j else 0. for i in range(512)] for j in range(6)]}

    def controller(self):
        state=dict(generation='session', backend='vulkan', device='none', ready=True,
                   devices='  Vulkan0: Test GPU')
        changes=[]
        def transport(method, body=None):
            if method == 'PUT':
                changes.append(body['device'])
                state['device']=body['device']
                state['generation']+='x'
            return dict(state)
        return state, changes, transport

    def test_collector_retains_three_completed_corpus_rounds_and_exact_prompt(self):
        values=iter([value for i in range(23) for value in (i, i+0.01)])
        with patch.dict(os.environ, {'PI_LLAMA_ENDPOINT':'http://fixture'}), \
             patch.object(managed_runtime.time, 'perf_counter', side_effect=lambda:next(values)), \
             patch.object(managed_runtime, 'request_json', return_value={'data':[{'embedding':[1.]*768}]}) as request:
            result=managed_runtime._measure()
        self.assertEqual(len(result['latencies_ms']), 18)
        self.assertEqual(len(result['completed_per_second']), 3)
        self.assertAlmostEqual(result['completed_per_second'][0],100)
        self.assertEqual(request.call_count,23)
        self.assertTrue(request.call_args.args[2]['input'][0].startswith('task: search result | query: '))

    def test_two_percent_query_gain_uses_stage_planner_and_session_invalidation(self):
        state, changes, transport=self.controller()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PI_RUNTIME_CONTROL_URL':'http://fixture'}):
            samples=iter([self.sample(100),self.sample(102)])
            result=managed_runtime.apply_selection(Path(tmp),'gemma','auto',transport=transport,
                                                  measure=lambda:next(samples))
            self.assertEqual(result['backend'],'vulkan')
            self.assertEqual(result['execution_shape'],'gpu-backbone-cpu-projector')
            self.assertEqual(result['stage_resources']['decision']['evidence_state'],'measured')
            self.assertEqual(result['stage_resources']['stage'],'query_embedding')
            self.assertEqual(len(result['stage_resources']['evidence']),2)
            # Same live process can reuse its decision without running new work.
            managed_runtime.apply_selection(Path(tmp),'gemma','auto',transport=transport,
                                            measure=lambda:self.fail('unexpected cached benchmark'))
            state['generation']='new-controller'
            samples=iter([self.sample(100),self.sample(80)])
            result=managed_runtime.apply_selection(Path(tmp),'gemma','auto',transport=transport,
                                                  measure=lambda:next(samples))
            self.assertEqual(result['backend'],'cpu')
            self.assertEqual(result['stage_resources']['runtime_generation'],state['generation'])

    def test_query_sample_cannot_be_labeled_as_document_embedding_evidence(self):
        state, changes, transport=self.controller()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PI_RUNTIME_CONTROL_URL':'http://fixture'}):
            wrong={**self.sample(1000),'stage':'embedding'}
            samples=iter([wrong,wrong])
            result=managed_runtime.apply_selection(Path(tmp),'gemma','auto',transport=transport,
                                                  measure=lambda:next(samples))
            self.assertEqual(result['backend'],'cpu')
            self.assertEqual(result['stage_resources']['decision']['evidence_state'],'unavailable')

    def test_divergent_or_missing_fixed_probes_reject_faster_gpu(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                state, changes, transport=self.controller()
                with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PI_RUNTIME_CONTROL_URL':'http://fixture'}):
                    gpu=self.sample(200)
                    if missing:
                        gpu.pop('probe_vectors')
                    else:
                        gpu['probe_vectors']=[[-value for value in row] for row in gpu['probe_vectors']]
                    samples=iter([self.sample(100),gpu])
                    result=managed_runtime.apply_selection(Path(tmp),'gemma','auto',transport=transport,
                                                          measure=lambda:next(samples))
                    self.assertEqual(result['backend'],'cpu')
                    self.assertFalse(result['stage_resources']['fixed_probe_parity']['validated'])
                    self.assertIn('parity',result['stage_resources']['decision']['rejected'][0][1])
                    self.assertNotIn('probe_vectors',(Path(tmp)/'managed-runtime-state.json').read_text())

    def test_failed_cpu_baseline_is_reported_as_a_blocking_comparison_failure(self):
        state, changes, transport=self.controller()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PI_RUNTIME_CONTROL_URL':'http://fixture'}):
            with self.assertRaisesRegex(RuntimeError, 'CPU query benchmark baseline failed'):
                managed_runtime.apply_selection(Path(tmp),'gemma','auto',transport=transport,
                    measure=lambda:(_ for _ in ()).throw(RuntimeError('fixture unavailable')))
        self.assertEqual(changes,['none'])

    def test_live_status_invalidates_old_generation_evidence(self):
        saved={'generation':'old','stage_resources':{'evidence':[{'old':True}]}}
        with patch.object(managed_runtime, 'transport', return_value={
            'generation':'new', 'device':'none', 'backend':'vulkan', 'ready':True,
        }):
            result=managed_runtime.observed_execution(saved)
        self.assertEqual(result['stage_resources']['evidence'],[])
        self.assertIsNone(result['stage_resources']['decision'])

    def test_scalar_compatibility_does_not_manufacture_repeated_samples(self):
        state, changes, transport=self.controller()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PI_RUNTIME_CONTROL_URL':'http://fixture'}):
            samples=iter([100.,90.])
            result=managed_runtime.apply_selection(Path(tmp),'gemma','auto',transport=transport,
                                                  measure=lambda:next(samples))
            self.assertEqual(result['backend'],'vulkan')
            self.assertEqual(result['stage_resources']['evidence'],[])
            self.assertIsNone(result['stage_resources']['decision'])
