"""Optional local ownership and unchanged protected remote token boundary."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from pi_platform.adapters.orchestration.knowledge_sync import KnowledgeSyncCoordinator
from pi_platform.adapters.ui.composition import build_ui_service
from pi_platform.adapters.ui.http_server import UiHttpServer


class LocalKnowledgeReviewTests(unittest.TestCase):
    def test_loopback_owner_needs_no_token_but_other_origins_and_hosts_are_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            service, _ = build_ui_service(repo_root=target, defer_runtime=True)
            with UiHttpServer(service, token='') as server:
                coordinator = KnowledgeSyncCoordinator(target, target / '.project-intelligence-cache',
                    local_operator=server.local_admin_enabled)
                server.admin_routes.knowledge_sync = coordinator
                url = server.address + '/api/v1/admin/knowledge/settings'
                def save(headers=None):
                    return urllib.request.urlopen(urllib.request.Request(url,
                        data=b'{"share_enabled":true,"post_reindex_export":true}', method='PUT',
                        headers={'Content-Type':'application/json', **(headers or {})}), timeout=10)
                with save({'Origin':server.address}) as response:
                    self.assertTrue(json.load(response)['post_reindex_export'])
                for headers in ({'Origin':'https://untrusted.invalid'}, {'Host':'untrusted.invalid'},
                                {'Sec-Fetch-Site':'cross-site'}):
                    with self.subTest(headers=headers), self.assertRaises(urllib.error.HTTPError) as raised:
                        save(headers)
                    self.assertEqual(raised.exception.code, 403)

    def test_configured_token_still_required_for_local_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = build_ui_service(repo_root=Path(tmp), defer_runtime=True)
            with UiHttpServer(service, token='test-owner-token') as server:
                req = urllib.request.Request(server.address + '/api/v1/admin/knowledge/settings',
                    data=b'{}', method='PUT', headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(req, timeout=10)
                self.assertEqual(raised.exception.code, 401)

    def test_public_container_binding_does_not_enable_tokenless_ownership(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',
                {'PI_UI_LOCAL_ADMIN':'1', 'PI_UI_BIND_HOST':'0.0.0.0'}):
            service, _ = build_ui_service(repo_root=Path(tmp), defer_runtime=True)
            with UiHttpServer(service, host='0.0.0.0', token='') as server:
                self.assertFalse(server.local_admin_enabled)
                url = server.address.replace('0.0.0.0', '127.0.0.1') + '/api/v1/admin/knowledge/settings'
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(url, timeout=10)
                self.assertEqual(raised.exception.code, 403)

