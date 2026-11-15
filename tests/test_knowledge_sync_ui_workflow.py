"""Administrator workflow, real proposal review, and private preferences."""
import json
import os
import time
import unittest
from unittest.mock import patch

from tests.test_portable_canonical_sync import PortableProductionTests, git
from pi_platform.adapters.orchestration.knowledge_sync import KnowledgeSyncCoordinator
from pi_platform.adapters.ui.retrieval_admin_routes import RetrievalAdminRoutes, create_dispatcher


class KnowledgeWorkflowTests(PortableProductionTests):
    def test_reindex_job_history_survives_route_recreation(self):
        routes = RetrievalAdminRoutes(target_repo=self.root)
        routes.knowledge_sync = self.coordinator()
        def reindex(kind, details):
            runtime = self.build()
            self.publish_runtime(runtime)
            return {'source_parse_misses': runtime.extra['source_parse_misses'],
                    'new_vectors': runtime.extra['indexing_report'].embedded_count}
        routes.job_executor = reindex
        job = routes.handle_reindex().body['job_id']
        completed = self.wait_job(routes, job)
        restored = RetrievalAdminRoutes(target_repo=self.root)
        restored.knowledge_sync = self.coordinator()
        self.assertEqual(restored.job_view(job), completed)
    def test_http_restore_publishes_query_ready_without_parsing_or_embedding(self):
        import urllib.request
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.adapters.ui.http_server import UiHttpServer
        from pi_platform.cli.main import _bootstrap_and_index_target
        self.publish_runtime(self.build())
        self.publish(self.stage(vectors=True))
        clone = self.clone()
        service, ready = build_ui_service(repo_root=clone, defer_runtime=True)
        server = UiHttpServer(service, readiness=ready.is_ready, token='fixture-token')
        coordinator = KnowledgeSyncCoordinator(clone, self.cache(clone), authenticated_operator=True,
            index=lambda **kw: _bootstrap_and_index_target(clone, service=service, readiness=ready,
                                                          cache_root=self.cache(clone), **kw))
        server.admin_routes.knowledge_sync = coordinator
        server.admin_routes.job_executor = lambda kind, details: coordinator.restore()
        server.start_background()
        self.addCleanup(server.stop)
        def request(path, body=None):
            req = urllib.request.Request(server.address + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Authorization': 'Bearer fixture-token', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.load(response)
        with patch('pi_platform.adapters.ingest.local_pipeline_driver.LocalPipelineDriver.run_many',
                   side_effect=AssertionError('HTTP restore scheduled parsing')), patch(
                   'pi_platform.adapters.retrieval.hashing_embedding_model.HashingEmbeddingAdapter.embed_request',
                   side_effect=AssertionError('HTTP restore called model')):
            job = request('/api/v1/admin/knowledge/restore', {})['job_id']
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                result = request('/api/v1/admin/jobs/' + job)
                if result['status'] in {'failed', 'completed'}:
                    break
                time.sleep(0.01)
            self.assertEqual(result['status'], 'completed', result)
            self.assertTrue(result['result']['searchReady'], result)
        self.assertTrue(ready.is_ready())
        self.assertEqual(request('/api/v1/admin/knowledge/status')['localIndexReady'], True)
    def test_project_preference_controls_auto_export_after_local_publication(self):
        from pi_platform.cli.main import _bootstrap_and_index_target
        coordinator = self.coordinator()
        coordinator.save_settings({'share_enabled': True, 'include_vectors': True})
        with patch.dict(os.environ, {'PI_PORTABLE_EXPORT': 'off', 'PI_OPERATOR_APPROVAL_KEY': '', 'PI_OPERATOR_APPROVAL_KEY_FILE': ''}):
            first = _bootstrap_and_index_target(self.root)
            self.assertTrue(first['ready'])
            self.assertFalse((self.root / 'project-knowledge').exists())
            coordinator.save_settings({'post_reindex_export': True})
            second = _bootstrap_and_index_target(self.root)
            self.assertTrue(second['ready'])
            self.assertEqual(second['portable_export']['state'], 'published')
            self.assertEqual(second['source_parse_misses'], 0)
            self.assertEqual(second['new_vectors'], 0)
            (self.cache() / 'security-state' / 'auto-export-grant').write_text('forged')
            failed = _bootstrap_and_index_target(self.root)
            self.assertTrue(failed['ready'])
            self.assertEqual(failed['portable_export']['state'], 'failed')

    def test_secret_file_loading_and_private_cache_ignore_work_in_git_worktrees(self):
        from pi_platform.core.sync.trusted_approval import HmacTrustedApprovalBoundary
        from pi_platform.ports import ApprovalRequest, ApprovalRejected
        path = self.base / 'operator.key'
        path.write_bytes(b'private-test-key-file-material\n')
        path.chmod(0o600)
        with patch.dict(os.environ, {'PI_OPERATOR_APPROVAL_KEY_FILE': str(path), 'PI_OPERATOR_APPROVAL_KEY': ''}):
            boundary = HmacTrustedApprovalBoundary()
            request = ApprovalRequest(action='materialise', repo_root=str(self.root))
            boundary.verify(request, boundary.issue(request))
            if os.name != 'nt':
                path.chmod(0o644)
                with self.assertRaises(ApprovalRejected):
                    HmacTrustedApprovalBoundary()
        worktree = self.base / 'worktree'
        git(self.root, 'worktree', 'add', '-b', 'review', str(worktree))
        from pi_platform.adapters.fs.private_cache import ensure_private_cache
        ensure_private_cache(worktree, self.cache(worktree))
        self.assertEqual(git(worktree, 'check-ignore', '.project-intelligence-cache/private.sqlite'),
                         '.project-intelligence-cache/private.sqlite')
    def coordinator(self, authenticated=True):
        return KnowledgeSyncCoordinator(self.root, self.cache(), authenticated_operator=authenticated)

    def test_admin_exports_reviews_and_publishes_without_browser_signing_secret(self):
        first = self.build()
        self.publish_runtime(first)
        coordinator = self.coordinator()
        routes = RetrievalAdminRoutes(target_repo=self.root)
        routes.knowledge_sync = coordinator
        def execute(kind, details):
            if kind == 'knowledge.export':
                return coordinator.proposal(coordinator.export()['stagingId'])
            return coordinator.publish(details['stagingId'])
        routes.job_executor = execute
        dispatch = create_dispatcher(routes)
        prefix = '/api/v1/admin/knowledge/'
        self.assertEqual(dispatch('PUT', prefix + 'settings', {'share_enabled': True}).status, 200)
        job = dispatch('POST', prefix + 'export', {}).body['job_id']
        result = self.wait_job(routes, job)['result']
        self.assertIn('changedPaths', result)
        self.assertNotIn('version', result)
        self.assertNotIn('key', json.dumps(result))
        self.assertFalse((self.root / 'project-knowledge').exists())
        request = {k: result[k] for k in ('stagingId', 'snapshotId')}
        self.assertEqual(dispatch('POST', prefix + 'publish', {**request, 'snapshotId': 'wrong'}).status, 400)
        job = dispatch('POST', prefix + 'publish', request).body['job_id']
        self.assertEqual(self.wait_job(routes, job)['result']['state'], 'published')
        fresh_routes = RetrievalAdminRoutes(target_repo=self.root)
        fresh_routes.knowledge_sync = self.coordinator()
        self.assertEqual(fresh_routes.job_view(job)['result']['state'], 'published')
        self.assertTrue(git(self.root, 'status', '--porcelain', '--', 'project-knowledge'))
        self.assertEqual(git(self.root, 'diff', '--cached', '--name-only'), '')
        key = self.cache() / 'security-state' / 'operator-approval.key'
        self.assertTrue(key.exists())
        if os.name != 'nt':
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.coordinator().settings()['share_enabled'], True)

    def wait_job(self, routes, job):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            view = routes.job_view(job)
            if view['status'] in {'completed', 'failed'}:
                self.assertEqual(view['status'], 'completed', view)
                return view
            time.sleep(0.01)
        self.fail('Knowledge job did not finish')

    def test_anonymous_operator_cannot_issue_publication_or_auto_grant(self):
        coordinator = self.coordinator(False)
        coordinator.save_settings({'share_enabled': True})
        with self.assertRaisesRegex(ValueError, 'Authenticated'):
            coordinator.save_settings({'post_reindex_export': True})
        self.assertFalse(coordinator.settings()['post_reindex_export'])
        self.publish_runtime(self.build())
        proposal = coordinator.export()
        with self.assertRaisesRegex(ValueError, 'Authenticated'):
            coordinator.publish(proposal['stagingId'])
        self.assertFalse((self.root / 'project-knowledge').exists())
        routes = RetrievalAdminRoutes(target_repo=self.root, caller_capability_provider=lambda: 'coding-agent')
        routes.knowledge_sync = coordinator
        for method, operation in [('GET', 'settings'), ('POST', 'restore'), ('POST', 'export'), ('POST', 'publish')]:
            self.assertEqual(create_dispatcher(routes)(method, '/api/v1/admin/knowledge/' + operation, {}).status, 403)

    def test_settings_reject_secrets_and_default_auto_export_is_off(self):
        coordinator = self.coordinator()
        self.assertEqual(coordinator.settings(), {'share_enabled': False, 'post_reindex_export': False, 'include_vectors': False})
        for value in ({'share_enabled': 'yes'}, {'key': 'private-key'}, {'post_reindex_export': True}):
            with self.assertRaises(ValueError):
                coordinator.save_settings(value)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(KnowledgeWorkflowTests(name) for name in KnowledgeWorkflowTests.__dict__ if name.startswith('test_'))
