import tempfile
import unittest
from pathlib import Path
from pi_platform.core.sync.version_monitor import PollingProjectVersionMonitor, ProjectVersionState


class FailedCandidateTests(unittest.TestCase):
    def test_permanent_candidate_survives_restart_manual_retry_and_changed_input(self):
        from pi_platform.core.ingest.failures import CandidateIndexingError
        with tempfile.TemporaryDirectory() as raw:
            state = [ProjectVersionState('head', 'main', 'one')]
            calls = []
            def fail(event):
                calls.append(event)
                raise CandidateIndexingError({'permanent': 2})
            def monitor():
                return PollingProjectVersionMonitor(Path(raw), on_change=fail, state_reader=lambda: state[0])
            m = monitor()
            with self.assertRaises(CandidateIndexingError): m.poll_once()
            for _ in range(4): self.assertIsNone(m.poll_once())
            m = monitor(); self.assertIsNone(m.poll_once())
            m.request_refresh()
            with self.assertRaises(CandidateIndexingError): m.poll_once()
            self.assertEqual(len(calls), 2)
            state[0] = ProjectVersionState('head', 'main', 'two')
            with self.assertRaises(CandidateIndexingError): m.poll_once()
            self.assertEqual(len(calls), 3)

    def test_transient_candidate_recovers_after_backoff_without_an_edit(self):
        from unittest.mock import patch
        from pi_platform.core.ingest.failures import CandidateIndexingError
        with tempfile.TemporaryDirectory() as raw:
            calls = []
            def refresh(event):
                calls.append(event)
                if len(calls) == 1: raise CandidateIndexingError({'transient': 1})
            m = PollingProjectVersionMonitor(Path(raw), on_change=refresh,
                state_reader=lambda: ProjectVersionState('h', 'b', 'f'))
            with patch('pi_platform.core.sync.version_monitor.time.time', return_value=100):
                with self.assertRaises(CandidateIndexingError): m.poll_once()
                self.assertIsNone(m.poll_once())
            with patch('pi_platform.core.sync.version_monitor.time.time', return_value=111):
                self.assertIsNotNone(m.poll_once())
            self.assertEqual(len(calls), 2)

    def test_first_start_failure_binds_effective_settings_without_repeating(self):
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.core.ingest.failures import CandidateIndexingError
        from tests.test_portable_canonical_sync import PortableProductionTests
        fixture = PortableProductionTests('test_cold_clone_skips_parser_and_document_embedding_and_queries')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        (fixture.root / 'legacy.sql').write_bytes('select \'Grüße\';'.encode('cp1252'))
        calls = []
        def refresh(event):
            calls.append(event)
            return _bootstrap_and_index_target(fixture.root)
        m = PollingProjectVersionMonitor(fixture.root, on_change=refresh)
        with self.assertRaises(CandidateIndexingError): m.poll_once()
        for _ in range(3): self.assertIsNone(m.poll_once())
        self.assertEqual(len(calls), 1)

    def test_changed_runtime_asset_identity_unblocks_same_source_bytes(self):
        import os
        from unittest.mock import patch
        from pi_platform.core.ingest.failures import CandidateIndexingError
        with tempfile.TemporaryDirectory() as raw:
            calls = []
            def refresh(event):
                calls.append(event)
                raise CandidateIndexingError({'configuration_error': 1})
            m = PollingProjectVersionMonitor(Path(raw), on_change=refresh)
            with patch.dict(os.environ, {'PI_ASSET_MANIFEST_SHA256': '1'*64}):
                with self.assertRaises(CandidateIndexingError): m.poll_once()
                self.assertIsNone(m.poll_once())
            with patch.dict(os.environ, {'PI_ASSET_MANIFEST_SHA256': '2'*64}):
                with self.assertRaises(CandidateIndexingError): m.poll_once()
            self.assertEqual(len(calls), 2)
