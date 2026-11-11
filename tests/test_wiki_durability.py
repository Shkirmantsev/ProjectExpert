"""Successful canonical atomic writes must cross content/rename durability barriers."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pi_platform.core.wiki.llm_wiki import LlmWiki


@unittest.skipUnless(os.name == 'posix', 'Linux-container canonical filesystem')
class WikiDurabilityTests(unittest.TestCase):
    def test_file_and_directory_are_synced_around_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'page.md'
            path.write_text('old')
            events = []
            actual_sync, actual_replace = os.fsync, os.replace
            def sync(fd):
                events.append('sync')
                return actual_sync(fd)
            def replace(source, target):
                events.append('replace')
                return actual_replace(source, target)
            with patch('pi_platform.core.wiki.llm_wiki.os.fsync', side_effect=sync), patch('pi_platform.core.wiki.llm_wiki.os.replace', side_effect=replace):
                LlmWiki._atomic_write(path, 'new')
            self.assertEqual(events[:3], ['sync', 'replace', 'sync'])
            self.assertTrue(all(event == 'sync' for event in events[2:]))
            self.assertEqual(path.read_text(), 'new')

    def test_failed_content_flush_is_not_acknowledged_or_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'page.md'
            path.write_text('old')
            with patch('pi_platform.core.wiki.llm_wiki.os.fsync', side_effect=OSError('flush failed')):
                with self.assertRaises(OSError):
                    LlmWiki._atomic_write(path, 'new')
            self.assertEqual(path.read_text(), 'old')
            self.assertEqual(list(Path(tmp).glob('.wiki-*')), [])


class ApprovedCanonicalDurabilityTests(unittest.TestCase):
    def test_manifest_flush_failure_preserves_previous_approved_bytes(self):
        from pi_platform.core.canonical import save_manifest, manifest_from_shards
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'manifest.yaml'
            save_manifest(path, manifest_from_shards('objects', ()))
            before = path.read_bytes()
            with patch('pi_platform.core.canonical.durable_write.os.fsync', side_effect=OSError('disk flush failed')):
                with self.assertRaises(OSError):
                    save_manifest(path, manifest_from_shards('objects', (), dependencies=('changed',)))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.glob('.canonical-*')), [])
