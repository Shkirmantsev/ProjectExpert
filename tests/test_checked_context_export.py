"""Project-wide checked projections never replace complete confidential local data."""
import json
import asyncio
from dataclasses import replace
from unittest.mock import patch

from tests.test_portable_canonical_sync import PortableProductionTests, git
from pi_platform.adapters.sync.portable_snapshot_reader import verified_snapshot
from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery


class CheckedContextTests(PortableProductionTests):
    def test_mixed_source_exports_safe_fragments_and_keeps_complete_local_context(self):
        marker = 'ghp_' + 'Q' * 40
        public = 'Public delivery routing uses the shipping reference.'
        body = '# Mixed source\n\n## Public operations\n\n' + (public + '\n') * 70
        body += '\n## Private configuration\n\n' + marker + '\n'
        (self.root / 'mixed.md').write_text(body)
        git(self.root, 'add', 'mixed.md'); git(self.root, 'commit', '-m', 'mixed fixture')
        runtime = self.build(); self.publish_runtime(runtime)
        before = list(runtime.multi_stage_retrieval.retrieve(RetrievalQuery('Private configuration')).hits)
        self.assertTrue(any(marker in hit.snippet for hit in before))
        proposal = self.stage(vectors=True)
        self.assertGreater(proposal['safeContextCount'], 0)
        staged = self.cache() / 'portable-staging' / proposal['stagingId'] / 'knowledge'
        with verified_snapshot(staged, self.cache()) as (db, report):
            self.assertEqual(db.execute("SELECT count(*) FROM records WHERE kind='source' AND id='repo:mixed.md'").fetchone()[0], 0)
            contexts = [json.loads(row[0])['body'] for row in db.execute("SELECT body FROM records WHERE kind='context'")]
            self.assertTrue(any(public in item['text'] for item in contexts))
            self.assertTrue(all(marker not in item['text'] for item in contexts))
        for path in staged.rglob('*'):
            if path.is_file(): self.assertNotIn(marker.encode(), path.read_bytes())
        # Export must not rewrite local source outputs or the serving retriever.
        self.assertTrue(any(marker in hit.snippet for hit in runtime.multi_stage_retrieval.retrieve(
            RetrievalQuery('Private configuration')).hits))
        with patch('pi_platform.adapters.markdown.markdown_adapter.MarkdownAdapter.parse',
                   side_effect=AssertionError('Export damaged complete local source cache')):
            local = self.build()
        from tests.test_mcp_retrieval_output import _build_context
        from pi_platform.mcp.server import McpServer
        context = replace(_build_context(), multi_stage_retrieval=local.multi_stage_retrieval,
            hybrid_retrieval=local.hybrid_retrieval, context_assembler=local.context_assembler)
        result = asyncio.run(McpServer(context=context).call_tool('project.retrieve_context',
            {'text':'Private configuration', 'contextBudget':8000}))
        self.assertTrue(result['ok'], result.get('error'))
        self.assertIn(marker, json.dumps(result))
        self.publish(proposal)
        clone = self.clone(); (clone / 'mixed.md').unlink()
        # Complete sources remain cache-reusable. Safe projections are searchable
        # evidence only; they must never become a complete mixed.md cache hit.
        restored = self.build(clone)
        self.assertEqual(restored.extra['indexing_report'].embedded_count, 0)
        self.assertTrue(any(public in hit.snippet for hit in restored.multi_stage_retrieval.retrieve(
            RetrievalQuery('shipping reference')).hits))

    def test_explicit_local_policy_never_becomes_a_text_projection(self):
        self.publish_runtime(self.build())
        from pi_platform.adapters.orchestration.knowledge_sync import KnowledgeSyncCoordinator
        KnowledgeSyncCoordinator(self.root, self.cache(), authenticated_operator=True).review_source('billing.md', 'confidential')
        proposal = self.stage()
        self.assertEqual(proposal.get('safeContextCount', 0), 0)

    def test_context_only_snapshot_and_tamper_rejection(self):
        marker = 'ghp_' + 'V' * 40
        (self.root / 'billing.md').unlink(); (self.root / 'shipping.md').unlink()
        (self.root / 'mixed.md').write_text('# Public context\n' + ('Safe public logistics explanation.\n' * 70) +
            '\n## Private credentials\n' + marker)
        git(self.root, 'add', '-A'); git(self.root, 'commit', '-m', 'only mixed input')
        self.publish_runtime(self.build())
        proposal = self.stage()
        self.assertEqual(proposal['sources'], 0)
        self.assertGreater(proposal['safeContextCount'], 0)
        from pi_platform.adapters.sync.checked_context import validate_context
        from pi_platform.adapters.sync.portable_format import PortableSnapshotError
        with verified_snapshot(self.cache() / 'portable-staging' / proposal['stagingId'] / 'knowledge', self.cache()) as (db, _):
            identity, raw = db.execute("SELECT id,body FROM records WHERE kind='context' LIMIT 1").fetchone()
            body = json.loads(raw)['body']; body['text'] += ' tampered'
            with self.assertRaises(PortableSnapshotError): validate_context(identity, body)
