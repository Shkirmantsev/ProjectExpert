import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
from pi_platform.deployment import offline_assets


class OfflineDiagnosticTests(unittest.TestCase):
    def test_missing_pack_and_wrong_manifest_return_codes_without_private_path(self):
        with tempfile.TemporaryDirectory(prefix='private-corporate-') as raw:
            root = Path(raw)
            for exists, expected in [(False, 'asset_missing'), (True, 'manifest_digest_mismatch')]:
                if exists: (root / 'manifest.json').write_text('{}')
                output = StringIO()
                with patch('sys.argv', ['offline_assets', '--root', raw, '--manifest-sha256', '1'*64, '--diagnostic-json']), redirect_stdout(output):
                    with self.assertRaises(SystemExit) as caught: offline_assets.main()
                self.assertEqual(caught.exception.code, 2)
                result = json.loads(output.getvalue())
                self.assertEqual(result['code'], expected)
                self.assertNotIn(raw, output.getvalue())
                self.assertFalse(result['ok'])
