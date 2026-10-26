"""Opt-in production proof: pinned models, native ANN, UI/MCP and model switch."""
import asyncio
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('PI_RUN_MODEL_TESTS') == '1', 'enable PI_RUN_MODEL_TESTS=1 for real production acceptance')
class ProductionEndToEndTests(unittest.TestCase):
    def setUp(self):
        # Both production bindings are exercised: the pinned GGUF binding
        # ('gemma') and the native Transformers binding ('gemma-torch').
        # The latter needs sentence-transformers + torch at runtime, so an
        # opted-in environment without them skips with a clear reason
        # instead of failing mid-acceptance.
        from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import (
            is_real_binding_available,
        )
        if not is_real_binding_available():
            self.skipTest(
                "native 'gemma-torch' binding unavailable: install "
                "sentence-transformers and torch to run real production "
                "acceptance for both production bindings"
            )

    def test_multilingual_golden_retrieval_for_both_real_models(self):
        import json
        import math
        import resource
        import time
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
        corpus = {
            'billing.md': '# Billing\nRefundService.refundPayment reverses a card charge and returns money to the customer. Protocol PAY-REFUND-042 requires an audit record for every refund.',
            'shipping.md': '# Shipping\nThe warehouse dispatches parcels with truck tracking numbers and delivery estimates.',
            'authentication.md': '# Authentication\nAccessTokenValidator.validateToken verifies signed authentication tokens and rejects expired credentials.',
            'backup.md': '# Backup\nNightly database snapshots restore customer records after disk failure. Recovery uses the latest verified backup.',
            'inventory.md': '# Inventory\nStockReservation.reserveStock prevents two orders from purchasing the same last item.',
            'monitoring.md': '# Monitoring\nThe metrics endpoint exports request latency, error rates and process memory consumption.',
            'email.md': '# Email\nNotificationSender sends an order confirmation message to the buyer email address.',
            'tax.md': '# Tax\nCalculate sales tax from the destination country and the current regional tax rate.',
            'catalog.md': '# Catalog\nProduct listings display descriptions, pictures and available color variations.',
            'scheduler.md': '# Scheduler\nCron expressions determine when background maintenance jobs execute.',
            'search.md': '# Search\nThe search index ranks relevant product descriptions for customer queries.',
        }
        queries = [
            ('English', 'How do I return money after a card purchase?', 'billing.md'),
            ('German', 'Wie kann ich dem Kunden eine Kartenzahlung erstatten?', 'billing.md'),
            ('Ukrainian', 'Як повернути клієнту гроші за оплату карткою?', 'billing.md'),
            ('Russian', 'Как вернуть покупателю деньги за оплату картой?', 'billing.md'),
            ('Java identifier', 'AccessTokenValidator.validateToken', 'authentication.md'),
            ('business requirement', 'Prevent overselling when only one product remains', 'inventory.md'),
            ('protocol identifier', 'PAY-REFUND-042', 'billing.md'),
            ('code retrieval', 'Which method checks expired access credentials?', 'authentication.md'),
            ('cross-language', 'Datenbank nach einem Festplattenausfall wiederherstellen', 'backup.md'),
        ]
        reports = {}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, body in corpus.items():
                (root/name).write_text(body, encoding='utf-8')
            with patch.dict(os.environ, {'PI_STARTUP_PROFILE':'production', 'PI_DOCLING_ENABLED':'0', 'PI_DENSE_INDEX':'usearch'}):
                service, readiness = build_ui_service(repo_root=root, defer_runtime=True)
                for alias in ('gemma', 'gemma-torch'):
                    _bootstrap_and_index_target(root, model_alias=alias, device='cpu', service=service, readiness=readiness)
                    runtime = service._retrieval.runtime
                    rows = []
                    for category, query, expected in queries:
                        started = time.perf_counter()
                        result = runtime.multi_stage_retrieval.retrieve(RetrievalQuery(text=query, top_k=10, contextBudget=4000))
                        paths = [Path(hit.metadata.sourcePath).name for hit in result.hits]
                        rank = paths.index(expected)+1 if expected in paths else None
                        context_paths = [Path(hit.metadata.sourcePath).name for hit in result.contextBundle.hits]
                        rows.append({'category':category, 'rank':rank,
                                     'context_evidence':expected in context_paths,
                                     'exact_evidence_retained':any(
                                         Path(hit.metadata.sourcePath or '').name == expected
                                         and (hit.source == 'exact' or hit.selection_state == 'PROTECTED')
                                         for hit in result.contextBundle.hits),
                                     'latency_ms':(time.perf_counter()-started)*1000})
                    reports[alias] = {
                        'profile':runtime.embedding_model.profile().identity(),
                        'recall_at_5':sum(r['rank'] is not None and r['rank']<=5 for r in rows)/len(rows),
                        'recall_at_10':sum(r['rank'] is not None and r['rank']<=10 for r in rows)/len(rows),
                        'mrr':sum(1/r['rank'] if r['rank'] else 0 for r in rows)/len(rows),
                        'ndcg_at_10':sum(1/math.log2(r['rank']+1) if r['rank'] and r['rank']<=10 else 0 for r in rows)/len(rows),
                        'context_evidence_coverage':sum(r['context_evidence'] for r in rows)/len(rows),
                        # Selection deliberately keeps PROTECTED evidence after
                        # PRIMARY/RESERVE in the flat result. Retention means
                        # it survives into context, not an invented rank-one rule.
                        'exact_identifier_retention':all(r['exact_evidence_retained'] for r in rows if 'identifier' in r['category']),
                        'native_index_bytes':Path(runtime.dense_index.index_path).stat().st_size,
                        'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        'queries':rows,
                    }
        # Keep small reproducible evidence, never model weights or source data.
        output = Path(os.environ.get('PI_QUALITY_REPORT', 'tmp/local/production-semantic-quality.json'))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(reports, indent=2), encoding='utf-8')
        for alias, report in reports.items():
            with self.subTest(model=alias):
                self.assertGreaterEqual(report['recall_at_5'], 0.8)
                self.assertGreaterEqual(report['mrr'], 0.7)
                self.assertTrue(report['exact_identifier_retention'])

    def test_first_run_model_switch_and_ui_mcp_result_equality(self):
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.cli.main import _bootstrap_and_index_target, _build_embedded_mcp_and_a2a
        from pi_platform.mcp.server import _tool_search
        from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
        from pi_platform.ports.ui.rest_api import UiActor, RetrieveRequest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'billing.md').write_text('# Refunds\nThe billing service refunds card payments to customers. Refunds reverse the original charge.\n')
            (root / 'shipping.md').write_text('# Shipping\nThe warehouse dispatches parcels and tracks delivery trucks.\n')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'sources'], check=True)
            before = {p.name:p.read_bytes() for p in root.glob('*.md')}
            with patch.dict(os.environ, {'PI_STARTUP_PROFILE':'production', 'PI_DOCLING_ENABLED':'0', 'PI_DENSE_INDEX':'usearch'}):
                service, readiness = build_ui_service(repo_root=root, defer_runtime=True)
                identities = []
                for alias in ('gemma', 'gemma-torch', 'gemma'):
                    with self.subTest(model=alias):
                        summary = _bootstrap_and_index_target(root, model_alias=alias, device='cpu', service=service, readiness=readiness)
                        self.assertTrue(summary['ready'])
                        runtime = service._retrieval.runtime
                        identities.append(runtime.embedding_profile_hash)
                        self.assertEqual(runtime.backend_name, 'usearch')
                        result = service.retrieve(UiActor('human','reader','viewer'), RetrieveRequest('How can I reimburse a declined purchase?'))
                        self.assertTrue(result.results)
                        self.assertIn('refund', result.results[0].snippet.lower())
                        mcp, _, _, _ = _build_embedded_mcp_and_a2a(target=root, cache_root=root/'.project-intelligence-cache', service=service, readiness=readiness)
                        ctx = getattr(mcp, 'context', None) or getattr(mcp, '_context')
                        response = asyncio.run(_tool_search(ctx, {'text':'How can I reimburse a declined purchase?'}))
                        self.assertEqual([h.chunkId for h in result.results], [h['chunkId'] for h in response['result']['hits']])
                        if alias == 'gemma' and len(identities) == 3:
                            self.assertEqual(runtime.extra['indexing_report'].embedded_count, 0)
                self.assertEqual(identities[0], identities[2])
                self.assertNotEqual(identities[0], identities[1])
                original_branch = subprocess.check_output(['git','-C',str(root),'branch','--show-current'], text=True).strip()
                old_ids = set(service._retrieval.runtime.extra['chunk_ids'])
                subprocess.run(['git','-C',str(root),'checkout','-qb','replacement'], check=True)
                (root/'billing.md').unlink()
                (root/'credits.md').write_text('# Credits\nStore credit is issued as a voucher redeemable at checkout.\n')
                graph = root/'project-knowledge/graph/nodes'
                graph.mkdir(parents=True)
                (graph/'branch.jsonl').write_text('{"id":"branch-b","family":"Component","label":"Voucher service"}\n')
                subprocess.run(['git','-C',str(root),'add','-A'],check=True)
                subprocess.run(['git','-C',str(root),'-c','user.name=Test','-c','user.email=test@example.com','commit','-qm','replacement evidence'],check=True)
                _bootstrap_and_index_target(root, model_alias='gemma',device='cpu',service=service,readiness=readiness)
                branch_runtime = service._retrieval.runtime
                self.assertEqual(branch_runtime.extra['graph_node_ids'], ('branch-b',))
                current_ids = set(branch_runtime.extra['chunk_ids'])
                self.assertTrue(old_ids-current_ids)
                self.assertFalse((old_ids-current_ids).intersection(
                    hit.chunkId for hit in branch_runtime.multi_stage_retrieval.retrieve(
                        RetrievalQuery('refund card payments')).hits))
                subprocess.run(['git','-C',str(root),'checkout','-q',original_branch],check=True)
                returned = _bootstrap_and_index_target(root,model_alias='gemma',device='cpu',service=service,readiness=readiness)
                self.assertEqual(returned['new_vectors'],0)
                self.assertEqual(set(service._retrieval.runtime.extra['chunk_ids']),old_ids)
                self.assertEqual(service._retrieval.runtime.extra['graph_node_ids'],())
                self.assertTrue(service._retrieval.runtime.extra['dense_generation_loaded'])
            self.assertEqual(before, {p.name:p.read_bytes() for p in root.glob('*.md')})
