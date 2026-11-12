"""Deterministic scheduler evidence fixtures; these are not hardware benchmarks."""
from dataclasses import replace
import threading
import unittest
from unittest.mock import patch

from pi_platform.adapters.retrieval.multi_endpoint_embedding_model import (
    EmbeddingEndpoint, EndpointParityEvidence, MultiEndpointEvidence,
    MultiEndpointEmbeddingModel, benchmark_document_endpoints,
)
from pi_platform.adapters.retrieval.embedding_model_factory import EmbeddingModelFactory
from pi_platform.core.retrieval.semantic_index_service import CountingEmbeddingModel
from pi_platform.ports.retrieval.embedding_profile import EMBEDDINGGEMMA2_512, EMBEDDINGGEMMA2_GGUF_512
from pi_platform.ports.retrieval.embedding_model import EmbeddingModelError, EmbeddingRequest, EmbeddingRole


class MultiEndpointTests(unittest.TestCase):
    def setUp(self):
        self.models=[CountingEmbeddingModel(profile=EMBEDDINGGEMMA2_512) for _ in range(2)]
        self.endpoints=tuple(EmbeddingEndpoint(str(i),model,'runtime-'+str(i),'pinned-model',
            ('device-'+str(i),),lambda i=i:('runtime-'+str(i),'pinned-model')) for i,model in enumerate(self.models))
        # Fixture values test the gate only, not a speed claim.
        self.evidence=MultiEndpointEvidence(tuple(endpoint.signature() for endpoint in self.endpoints),
            EMBEDDINGGEMMA2_512.identity(),'representative-fixture', {'0':(10.,10.,10.),'1':(11.,11.,11.)},
            (15.,15.,15.), (EndpointParityEvidence('1',1.,0.,(('a','b'),('b','a')),(('a','b'),('b','a'))),),
            batch_size=1, combined_topk=(('a','b'),('b','a')))

    def build(self, **kwargs):
        kwargs.setdefault('batch_size',1)
        kwargs.setdefault('enabled',True)
        return MultiEndpointEmbeddingModel(self.endpoints,self.evidence,**kwargs)

    def test_opt_in_off_by_default_factory_uses_explicit_ports_only(self):
        with patch.dict('os.environ',{'PI_EMBED_MULTI_BACKEND':'0'}):
            with self.assertRaisesRegex(EmbeddingModelError,'disabled'):
                MultiEndpointEmbeddingModel(self.endpoints,self.evidence,batch_size=1)
        model=EmbeddingModelFactory().build_multi_endpoint(self.endpoints,self.evidence,batch_size=1,enabled=True)
        self.assertEqual(model.profile().identity(),EMBEDDINGGEMMA2_512.identity())

    def test_gates_profile_runtime_physical_devices_quality_and_actual_speedup(self):
        for evidence in (
            replace(self.evidence,parity=()),
            replace(self.evidence,combined_topk=()),
            replace(self.evidence,parity=(replace(self.evidence.parity[0],minimum_cosine=0.9),)),
            replace(self.evidence,parity=(replace(self.evidence.parity[0],candidate_topk=(('b','a'),('b','a'))),)),
            replace(self.evidence,combined_per_second=(11.,11.,11.)),
            replace(self.evidence,standalone_per_second={'0':(10.,),'1':(11.,)*3}),
            replace(self.evidence,workload_identity=''),
            replace(self.evidence,stage='query_embedding'),
            replace(self.evidence,endpoint_signatures=()),
        ):
            with self.subTest(evidence=evidence):
                with self.assertRaises(EmbeddingModelError):
                    MultiEndpointEmbeddingModel(self.endpoints,evidence,batch_size=1,enabled=True)
        for endpoint in (
            replace(self.endpoints[1],physical_devices=('device-0',)),
            replace(self.endpoints[1],model_identity='other'),
            replace(self.endpoints[1],identity_probe=lambda:('different','pinned-model')),
            replace(self.endpoints[1],model=CountingEmbeddingModel(profile=EMBEDDINGGEMMA2_GGUF_512)),
        ):
            with self.assertRaises(EmbeddingModelError):
                MultiEndpointEmbeddingModel((self.endpoints[0],endpoint),self.evidence,batch_size=1,enabled=True)

    def test_parallel_batches_preserve_order_with_one_inflight_call_per_endpoint(self):
        model=self.build()
        barrier=threading.Barrier(2)
        originals=[item.embed_requests for item in self.models]
        entered=[0,0]
        def first(index,requests):
            entered[index]+=1
            if entered[index] == 1:
                barrier.wait(timeout=2)
            return originals[index](requests)
        with patch.object(self.models[0],'embed_requests',side_effect=lambda requests:first(0,requests)), \
             patch.object(self.models[1],'embed_requests',side_effect=lambda requests:first(1,requests)):
            actual=model.embed_batch([str(i) for i in range(9)])
        self.assertEqual(actual,[self.models[0]._deterministic_vector(str(i)) for i in range(9)])
        self.assertTrue(all(entered))

    def test_failed_endpoint_retries_only_its_missing_batch(self):
        model=self.build()
        original=self.models[0].embed_requests
        with patch.object(self.models[1],'embed_requests',side_effect=EmbeddingModelError('fixture down')):
            output=model.embed_batch(['a','b','c','d'])
        self.assertEqual(output,[self.models[0]._deterministic_vector(text) for text in ['a','b','c','d']])
        self.assertEqual(sorted(request.text for request in self.models[0].embed_request_calls),['a','b','c','d'])

    def test_all_endpoint_failures_exhaust_budget_without_returning_partial_vectors(self):
        model=self.build()
        with patch.object(self.models[0],'embed_requests',side_effect=EmbeddingModelError('down')), \
             patch.object(self.models[1],'embed_requests',side_effect=EmbeddingModelError('down')):
            with self.assertRaises(EmbeddingModelError):
                model.embed_batch(['a','b'])

    def test_identity_change_after_embedding_is_not_mixed_into_result(self):
        calls=[0]
        def probe():
            calls[0]+=1
            return ('runtime-1' if calls[0] <= 2 else 'replaced','pinned-model')
        endpoint=replace(self.endpoints[1],identity_probe=probe)
        self.endpoints=(self.endpoints[0],endpoint)
        model=self.build()
        output=model.embed_batch(['a','b','c'])
        self.assertEqual(output,[self.models[0]._deterministic_vector(text) for text in ['a','b','c']])

    def test_query_requests_remain_on_baseline_without_using_document_throughput(self):
        model=self.build()
        with patch.object(self.models[1],'embed_requests',side_effect=AssertionError('query dispatch')):
            output=model.embed_requests([EmbeddingRequest('query',EmbeddingRole.QUERY)])
        self.assertEqual(len(output),1)

    def test_document_benchmark_uses_actual_caller_corpus_and_repeated_completed_work(self):
        docs=[EmbeddingRequest(text,EmbeddingRole.DOCUMENT) for text in ['a','b','c','d']]
        queries=[EmbeddingRequest(text,EmbeddingRole.QUERY) for text in ['a','c']]
        times=iter(range(18)) # Two times for each of nine real corpus runs.
        evidence=benchmark_document_endpoints(self.endpoints,docs,queries,batch_size=1,clock=lambda:next(times))
        self.assertEqual(len(evidence.combined_per_second),3)
        self.assertEqual(evidence.combined_per_second,(4.,4.,4.))
        self.assertTrue(evidence.parity[0].passes())
        self.assertEqual(len(evidence.workload_identity),64)
        with self.assertRaisesRegex(EmbeddingModelError,'fastest standalone'):
            MultiEndpointEmbeddingModel(self.endpoints,evidence,batch_size=1,enabled=True)
        bad=CountingEmbeddingModel(profile=EMBEDDINGGEMMA2_512)
        for text in ['a','b','c','d']:
            bad._vectors[text]=[-value for value in bad._deterministic_vector(text)]
        endpoint=replace(self.endpoints[1],model=bad)
        with self.assertRaisesRegex(EmbeddingModelError,'parity failed'):
            benchmark_document_endpoints((self.endpoints[0],endpoint),docs,queries,batch_size=1)
