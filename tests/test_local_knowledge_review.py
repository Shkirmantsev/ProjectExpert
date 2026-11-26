"""Tokenless administration and configured bearer boundaries."""
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
    def test_loopback_needs_no_token_and_rejects_cross_origin_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            service, _ = build_ui_service(repo_root=target, defer_runtime=True)
            with UiHttpServer(service, token='') as server:
                coordinator = KnowledgeSyncCoordinator(target, target / '.project-intelligence-cache',
                    local_operator=not server.token)
                server.admin_routes.knowledge_sync = coordinator
                url = server.address + '/api/v1/admin/knowledge/settings'
                def save(headers=None):
                    return urllib.request.urlopen(urllib.request.Request(url,
                        data=b'{"share_enabled":true,"post_reindex_export":true}', method='PUT',
                        headers={'Content-Type':'application/json', **(headers or {})}), timeout=10)
                with save({'Origin':server.address}) as response:
                    self.assertTrue(json.load(response)['post_reindex_export'])
                for headers in ({'Origin':'https://untrusted.invalid'},
                                {'Sec-Fetch-Site':'cross-site'}):
                    with self.subTest(headers=headers), self.assertRaises(urllib.error.HTTPError) as raised:
                        save(headers)
                    self.assertEqual(raised.exception.code, 403)

    def test_effective_container_token_requires_matching_bearer(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'PI_UI_TOKEN': 'fixture-token'}):
            service, _ = build_ui_service(repo_root=Path(tmp), defer_runtime=True)
            with UiHttpServer(service, host='0.0.0.0') as server:
                base = server.address.replace('0.0.0.0', '127.0.0.1')
                for value in (None, 'wrong', 'fixture-token'):
                    headers = {'Host': 'projectexpert.example:8765'}
                    if value:
                        headers['Authorization'] = 'Bearer ' + value
                    request = urllib.request.Request(base + '/api/v1/auth-status', headers=headers)
                    with urllib.request.urlopen(request, timeout=10) as response:
                        status = json.load(response)
                    self.assertTrue(status['token_required'])
                    self.assertEqual(status['admin_access'], value == 'fixture-token')
                    request = urllib.request.Request(base + '/api/v1/admin/runtime', headers=headers)
                    if value == 'fixture-token':
                        with urllib.request.urlopen(request, timeout=10) as response:
                            self.assertEqual(response.status, 200)
                    else:
                        with self.assertRaises(urllib.error.HTTPError) as raised:
                            urllib.request.urlopen(request, timeout=10)
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

    def test_wildcard_container_binding_allows_tokenless_administration(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',
                {'PI_UI_LOCAL_ADMIN': '1', 'PI_UI_BIND_HOST': '0.0.0.0'}):
            service, _ = build_ui_service(repo_root=Path(tmp), defer_runtime=True)
            with UiHttpServer(service, host='0.0.0.0', token='') as server:
                url = server.address.replace('0.0.0.0', '127.0.0.1')
                with urllib.request.urlopen(url + '/api/v1/admin/runtime', timeout=10) as response:
                    self.assertEqual(response.status, 200)

    def test_forwarded_remote_browser_can_manage_knowledge_without_token(self):
        from pi_platform.adapters.ui.http_server import _build_handler

        def rancher_handler(server):
            original = _build_handler(server)

            class ForwardedHandler(original):
                def setup(self):
                    super().setup()
                    self.client_address = ('192.168.127.1', self.client_address[1])

            return ForwardedHandler

        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {}), patch(
            'pi_platform.adapters.ui.http_server._build_handler', side_effect=rancher_handler
        ):
            import os
            os.environ.pop('PI_UI_TOKEN', None)
            target = Path(tmp)
            service, _ = build_ui_service(repo_root=target, defer_runtime=True)
            with UiHttpServer(service, host='0.0.0.0') as server:
                server.admin_routes.knowledge_sync = KnowledgeSyncCoordinator(
                    target, target / '.project-intelligence-cache', local_operator=not server.token)
                base = server.address.replace('0.0.0.0', '127.0.0.1')

                def request(path, data=None):
                    req = urllib.request.Request(base + path, data=data, method='PUT' if data else 'GET',
                        headers={'Host': 'projectexpert.example:8765', 'Origin': 'https://projectexpert.example:8765',
                                 'Content-Type': 'application/json'})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        return json.load(response)

                auth = request('/api/v1/auth-status')
                self.assertTrue(auth['admin_access'])
                self.assertFalse(auth['token_required'])
                saved = request('/api/v1/admin/knowledge/settings',
                    b'{"share_enabled":true,"post_reindex_export":true}')
                self.assertTrue(saved['post_reindex_export'])
