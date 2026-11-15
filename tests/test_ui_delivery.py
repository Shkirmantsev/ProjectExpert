"""Actual HTML asset resolution and live UI delivery/version boundaries."""
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urljoin, urlparse
from urllib.request import url2pathname

from pi_platform.adapters.ui.http_server import STATIC_ROOT, UiHttpServer


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.assets = [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if 'id' in values:
            self.ids.append(values['id'])
        if tag == 'link' and values.get('rel') == 'stylesheet':
            self.assets.append(values['href'])
        if tag == 'script' and 'src' in values:
            self.assets.append(values['src'])


class UiDeliveryTests(unittest.TestCase):
    def test_file_preview_assets_resolve_and_controls_have_unique_targets(self):
        index = STATIC_ROOT / 'index.html'
        page = Page(index.read_text())
        self.assertEqual(len(page.ids), len(set(page.ids)), 'Duplicate IDs send results to the wrong panel')
        for relative in page.assets:
            resolved = Path(url2pathname(urlparse(urljoin(index.as_uri(), relative)).path))
            self.assertTrue(resolved.is_file(), f'File preview cannot load {relative}')
            self.assertEqual(resolved.parent, STATIC_ROOT)

    def test_live_page_and_api_identify_build_and_prevent_stale_browser_cache(self):
        import json
        import urllib.request
        from pi_platform.adapters.ui.composition import build_ui_service
        with tempfile.TemporaryDirectory() as temporary:
            service, _ = build_ui_service(repo_root=Path(temporary), defer_runtime=True)
            with UiHttpServer(service, token='fixture-token') as server:
                with urllib.request.urlopen(server.address + '/api/v1/ui-version', timeout=10) as response:
                    identity = json.load(response)
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(identity['ui_contract'], 'knowledge-sync/2')
                self.assertRegex(identity['ui_build'], '^[a-f0-9]{64}$')
                with urllib.request.urlopen(server.address, timeout=10) as response:
                    page = Page(response.read().decode())
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                for asset in page.assets:
                    with urllib.request.urlopen(urljoin(server.address + '/', asset), timeout=10) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
