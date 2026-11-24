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

    def test_restricted_configured_actor_cannot_override_role_via_headers(self):
        from pi_platform.ports.ui.rest_api import UiActor

        with tempfile.TemporaryDirectory() as tmp:
            service, _ = build_ui_service(repo_root=Path(tmp), defer_runtime=True)
            with UiHttpServer(service, token='fixture-token',
                              actor=UiActor(actor_type='human', actor_id='reader', role='viewer')) as server:
                headers = {'Authorization': 'Bearer fixture-token', 'X-Actor-Role': 'administrator'}
                status = urllib.request.Request(server.address + '/api/v1/auth-status', headers=headers)
                with urllib.request.urlopen(status, timeout=10) as response:
                    self.assertFalse(json.load(response)['admin_access'])
                config = urllib.request.Request(server.address + '/api/v1/admin/runtime', headers=headers)
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(config, timeout=10)
                self.assertEqual(raised.exception.code, 403)

    def test_public_container_binding_does_not_enable_tokenless_ownership(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',
                {'PI_UI_LOCAL_ADMIN':'1', 'PI_UI_BIND_HOST':'0.0.0.0'}):
            service, _ = build_ui_service(repo_root=Path(tmp), defer_runtime=True)
            with self.assertRaisesRegex(ValueError, 'PI_UI_TOKEN'):
                UiHttpServer(service, host='0.0.0.0', token='')

    def test_managed_owner_requires_private_launch_credential(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',
                {'PI_UI_LOCAL_ADMIN': '1', 'PI_UI_BIND_HOST': '127.0.0.1'}):
            target = Path(tmp)
            service, _ = build_ui_service(repo_root=target, defer_runtime=True)
            key_path = target / 'private' / 'key'
            from pi_platform.adapters.ui.http_server import _build_handler

            def rancher_handler(server):
                original = _build_handler(server)

                class ForwardedHandler(original):
                    def setup(self):
                        super().setup()
                        self.client_address = ('192.168.127.1', self.client_address[1])

                return ForwardedHandler

            with patch('pi_platform.deployment.local_ui._MANAGED_ADMIN_KEY', key_path), patch(
                'pi_platform.adapters.ui.http_server._build_handler', side_effect=rancher_handler
            ):
                with UiHttpServer(service, host='0.0.0.0', token='') as server:
                    server.admin_routes.knowledge_sync = KnowledgeSyncCoordinator(
                        target, target / '.project-intelligence-cache', local_operator=server.local_admin_enabled)
                    base = server.address.replace('0.0.0.0', '127.0.0.1')
                    def request(path, headers=None, data=None):
                        req = urllib.request.Request(base + path, data=data,
                            method='PUT' if data else 'GET',
                            headers={'Content-Type': 'application/json', **(headers or {})})
                        with urllib.request.urlopen(req, timeout=10) as response:
                            return json.load(response)
                    auth = '/api/v1/auth-status'
                    settings = '/api/v1/admin/knowledge/settings'
                    self.assertFalse(request(auth)['local_owner_access'])
                    for headers in ({'X-Actor-Role': 'admin'}, {'X-Forwarded-For': '127.0.0.1'}):
                        with self.assertRaises(urllib.error.HTTPError) as raised:
                            request(settings, headers)
                        self.assertEqual(raised.exception.code, 403)
                    credential = {'X-ProjectExpert-Local-Owner': key_path.read_text().strip()}
                    self.assertTrue(request(auth, credential)['admin_access'])
                    self.assertFalse(request(auth, credential)['token_required'])
                    self.assertTrue(request(settings, credential, b'{"share_enabled":true}')['share_enabled'])
                    for headers in ({'Origin': 'https://untrusted.invalid'}, {'X-Actor-Role': 'viewer'}):
                        with self.assertRaises(urllib.error.HTTPError) as raised:
                            request(settings, {**credential, **headers}, b'{"share_enabled":false}')
                        self.assertEqual(raised.exception.code, 403)
