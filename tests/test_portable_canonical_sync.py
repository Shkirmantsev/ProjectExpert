"""Actual production-cache/Git roundtrips, without downloading model assets."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.adapters.runtime.sqlite_ingestion_cache import candidate_publication
from pi_platform.adapters.sync.portable_format import (
    ROOT, PortableSnapshotError, add_record, confined, decode, encode,
    read_snapshot, sha, source_path, spool, write_snapshot,
)
from pi_platform.adapters.sync.portable_snapshot_reader import verified_snapshot
from pi_platform.core.control.retrieval_settings import RetrievalSettings
from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
from pi_platform.core.orchestration.repository_indexing import index_repository
from pi_platform.core.sync.materialise import MaterialiseService
from pi_platform.core.sync.trusted_approval import HmacTrustedApprovalBoundary
from pi_platform.ports import ApprovalRequest, ApprovalRejected, ApprovalRequired
from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class PortableProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Windows TEMP may use an 8.3 alias; tokens and writers bind resolve().
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'original'
        self.root.mkdir()
        git(self.root, 'init', '-b', 'main')
        git(self.root, 'config', 'core.autocrlf', 'false')
        git(self.root, 'config', 'user.name', 'Portable Test')
        git(self.root, 'config', 'user.email', 'portable@example.invalid')
        (self.root / '.gitignore').write_text('.project-intelligence-cache/\n')
        (self.root / 'billing.md').write_text('# Billing\nRefund customer payments safely\n')
        (self.root / 'shipping.md').write_text('# Shipping\nParcel dispatch tracking\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-m', 'source fixture')
        self.env = patch.dict(os.environ, {'PI_STARTUP_PROFILE': 'minimal', 'PI_EMBEDDING_MODEL': 'hashing',
            'PI_DENSE_INDEX': 'flat', 'PI_DOCLING_ENABLED': '0', 'PI_INDEX_ENGINE': 'resumable',
            'PI_PORTABLE_EXPORT': 'review'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.boundary = HmacTrustedApprovalBoundary(key=b'test-only-local-key')
        self.materialise = MaterialiseService(boundary=self.boundary)

    def cache(self, root=None):
        return (root or self.root) / '.project-intelligence-cache'

    def build(self, root=None, inventory=None):
        root = root or self.root
        return index_repository(target=root, cache_root=self.cache(root),
            inventory=inventory or RepositorySourceDiscovery().discover(root),
            previous_inventory=None, settings=RetrievalSettings())

    def publish_runtime(self, runtime, root=None):
        with candidate_publication(self.cache(root), runtime):
            pass

    def stage(self, vectors=False):
        return self.materialise.stage_active_index(self.root, cache_root=self.cache(), include_vectors=vectors)

    def publish(self, proposal, token=None):
        if token is None:
            token = self.boundary.issue(ApprovalRequest(action='materialise',
                repo_root=str(self.root.resolve()), change_ids=(proposal['snapshotId'],)))
        return self.materialise.publish_active_index(self.root, cache_root=self.cache(),
            staging_id=proposal['stagingId'], approval_token=token)

    def clone(self):
        git(self.root, 'add', 'project-knowledge')
        git(self.root, 'commit', '-m', 'approved portable snapshot')
        clone = self.base / 'other-machine'
        git(self.base, 'clone', str(self.root), str(clone))
        return clone

    def test_cold_clone_skips_parser_and_document_embedding_and_queries(self):
        first = self.build()
        self.publish_runtime(first)
        proposal = self.stage(vectors=True)
        self.assertFalse((self.root / 'project-knowledge').exists())
        self.publish(proposal)
        clone = self.clone()
        os.environ['PI_PORTABLE_EXPORT'] = 'off'  # root alone enables restore
        with patch('pi_platform.adapters.markdown.markdown_adapter.MarkdownAdapter.parse',
                   side_effect=AssertionError('cold clone parsed an unchanged source')):
            second = self.build(clone)
        self.assertEqual(second.extra['indexing_report'].embedded_count, 0)
        self.assertEqual(second.extra['indexing_report'].reused_count, len(first.extra['chunk_ids']))
        self.assertEqual(second.extra['portable_import']['importedSources'], 2)
        self.assertEqual(first.extra['chunk_ids'], second.extra['chunk_ids'])
        self.assertTrue(second.multi_stage_retrieval.retrieve(RetrievalQuery('refund')).hits)
        # Re-export from entirely separate path/cache is byte-identical.
        self.publish_runtime(second, clone)
        other = self.materialise.stage_active_index(clone, cache_root=self.cache(clone), include_vectors=True)
        self.assertEqual(proposal['snapshotId'], other['snapshotId'])
        self.assertEqual(other['changedPaths'], [])

    def test_branch_switch_deletion_dirty_and_return_reuse(self):
        first = self.build()
        self.publish_runtime(first)
        self.publish(self.stage(vectors=True))
        self.clone()
        git(self.root, 'switch', '-c', 'branch-b')
        (self.root / 'billing.md').write_text('# Billing\nVoucher cancellation\n')
        (self.root / 'shipping.md').unlink()
        git(self.root, 'add', '-u')
        git(self.root, 'commit', '-m', 'changed source and deletion')
        from pi_platform.adapters.markdown.markdown_adapter import MarkdownAdapter
        original = MarkdownAdapter.parse
        calls = []
        def counted(parser, source, context):
            calls.append(source.id)
            return original(parser, source, context)
        with patch.object(MarkdownAdapter, 'parse', counted):
            second = self.build()
        self.assertEqual(calls, ['repo:billing.md'])
        self.assertFalse(set(first.extra['chunk_ids']) & set(second.extra['chunk_ids']))
        git(self.root, 'switch', 'main')
        with patch.object(MarkdownAdapter, 'parse', side_effect=AssertionError('branch A reparsed')):
            returned = self.build()
        self.assertEqual(first.extra['chunk_ids'], returned.extra['chunk_ids'])
        (self.root / 'billing.md').write_text('# Billing\nDirty refund revision\n')
        dirty = self.build()
        self.assertNotEqual(first.extra['chunk_ids'], dirty.extra['chunk_ids'])
        self.assertEqual(git(self.root, 'diff', '--', 'project-knowledge'), '')

    def test_worktree_and_detached_head_use_checkout_cache(self):
        first = self.build()
        self.publish_runtime(first)
        self.publish(self.stage(vectors=True))
        self.clone()
        worktree = self.base / 'worktree'
        git(self.root, 'worktree', 'add', '--detach', str(worktree), 'HEAD')
        with patch('pi_platform.adapters.markdown.markdown_adapter.MarkdownAdapter.parse', side_effect=AssertionError('worktree parsed')):
            runtime = self.build(worktree)
        self.assertEqual(runtime.extra['chunk_ids'], first.extra['chunk_ids'])
        self.assertNotEqual(self.cache(worktree), self.cache())

    def test_policy_denial_no_local_only_or_reference_derivatives(self):
        inventory = RepositorySourceDiscovery().discover(self.root)
        inventory = replace(inventory, entries=tuple(replace(e, policy='LOCAL_ONLY') if e.path == 'billing.md' else e for e in inventory.entries))
        runtime = self.build(inventory=inventory)
        self.publish_runtime(runtime)
        # Make actual discovery reproduce scanner classification.
        with patch.object(RepositorySourceDiscovery, 'discover', return_value=inventory):
            proposal = self.stage(vectors=True)
        self.assertEqual(proposal['excludedSources'], ['repo:billing.md'])
        knowledge = self.cache() / 'portable-staging' / proposal['stagingId'] / 'knowledge'
        for path in knowledge.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'Refund customer', path.read_bytes())
        with self.assertRaises(ApprovalRequired):
            self.materialise.publish_active_index(self.root, cache_root=self.cache(), staging_id=proposal['stagingId'])
        with self.assertRaises(ApprovalRejected):
            self.publish(proposal, token='random-token')
        wrong = self.boundary.issue(ApprovalRequest(action='materialise', repo_root=str(self.root), change_ids=('other',)))
        with self.assertRaises(ApprovalRejected):
            self.publish(proposal, token=wrong)

    def test_stale_proposal_and_corruption_preserve_prior_root(self):
        runtime = self.build()
        self.publish_runtime(runtime)
        proposal = self.stage(vectors=True)
        self.publish(proposal)
        original = (self.root / 'project-knowledge' / ROOT).read_bytes()
        (self.root / 'billing.md').write_text('edited\n')
        runtime = self.build()
        self.publish_runtime(runtime)
        candidate = self.stage()
        (self.root / 'shipping.md').write_text('raced\n')
        with self.assertRaisesRegex(PortableSnapshotError, 'Stale'):
            self.publish(candidate)
        self.assertEqual((self.root / 'project-knowledge' / ROOT).read_bytes(), original)
        # Corruption must not become a parser miss.
        shard = next((self.root / 'project-knowledge/objects/portable-v2').glob('*.jsonl'))
        shard.write_bytes(b'{}\n')
        with patch('pi_platform.adapters.markdown.markdown_adapter.MarkdownAdapter.parse', side_effect=AssertionError('parsed corrupt snapshot')):
            with self.assertRaises(PortableSnapshotError):
                self.build()

    def test_repeat_export_zero_diff_and_discovery_keeps_wiki(self):
        runtime = self.build()
        self.publish_runtime(runtime)
        proposal = self.stage()
        self.publish(proposal)
        self.clone()
        second = self.stage()
        self.assertEqual(second['changedPaths'], [])
        self.assertEqual(self.publish(second)['changedPaths'], [])
        discovered = [e.path for e in RepositorySourceDiscovery().discover(self.root).entries]
        self.assertEqual(discovered, ['billing.md', 'shipping.md'])
        wiki = self.root / 'project-knowledge/wiki/page.md'
        wiki.parent.mkdir()
        wiki.write_text('# Curated knowledge\n')
        discovered = [e.path for e in RepositorySourceDiscovery().discover(self.root).entries]
        self.assertIn('project-knowledge/wiki/page.md', discovered)

    def test_standard_mode_reuses_parsing_but_builds_missing_vectors(self):
        first = self.build()
        self.publish_runtime(first)
        self.publish(self.stage())
        clone = self.clone()
        with patch('pi_platform.adapters.markdown.markdown_adapter.MarkdownAdapter.parse', side_effect=AssertionError('parser invoked')):
            cold = self.build(clone)
        self.assertEqual(cold.extra['source_parse_hits'], 2)
        self.assertEqual(cold.extra['source_parse_misses'], 0)
        self.assertGreater(cold.extra['indexing_report'].embedded_count, 0)

    def test_interrupted_import_retries_complete_sources(self):
        first = self.build()
        self.publish_runtime(first)
        self.publish(self.stage(vectors=True))
        clone = self.clone()
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import SqliteIngestionCache
        original = SqliteIngestionCache.complete_source_atomic
        calls = []
        def interrupted(cache, *args):
            calls.append(args[0])
            if len(calls) == 2:
                raise OSError('simulated interrupted import')
            return original(cache, *args)
        with patch.object(SqliteIngestionCache, 'complete_source_atomic', interrupted):
            with self.assertRaisesRegex(OSError, 'interrupted import'):
                self.build(clone)
        with patch('pi_platform.adapters.markdown.markdown_adapter.MarkdownAdapter.parse', side_effect=AssertionError('retry parsed')):
            second = self.build(clone)
        self.assertEqual(second.extra['chunk_ids'], first.extra['chunk_ids'])

    def test_unreferenced_staging_binary_is_never_copied(self):
        self.publish_runtime(self.build())
        proposal = self.stage()
        staged = self.cache() / 'portable-staging' / proposal['stagingId'] / 'knowledge'
        (staged / 'leak.sqlite').write_bytes(b'private binary')
        self.publish(proposal)
        self.assertFalse((self.root / 'project-knowledge/leak.sqlite').exists())

    def test_interrupted_publication_preserves_valid_previous_root(self):
        self.publish_runtime(self.build())
        self.publish(self.stage())
        root = self.root / 'project-knowledge' / ROOT
        prior = root.read_bytes()
        (self.root / 'billing.md').write_text('# Updated billing\nA different fact\n')
        self.publish_runtime(self.build())
        proposal = self.stage()
        from pi_platform.core.canonical.durable_write import atomic_write_bytes
        def interrupted(path, raw):
            if path == root:
                raise OSError('simulated disk failure at root')
            return atomic_write_bytes(path, raw)
        with patch('pi_platform.core.canonical.durable_write.atomic_write_bytes', interrupted):
            with self.assertRaisesRegex(OSError, 'disk failure'):
                self.publish(proposal)
        self.assertEqual(root.read_bytes(), prior)
        with verified_snapshot(self.root / 'project-knowledge', self.cache()):
            pass
        self.publish(proposal)

    def test_cli_verify_export_publish_and_status(self):
        from pi_platform.cli.main import main
        import contextlib
        import io
        self.publish_runtime(self.build())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['canonical', 'export', '--target', str(self.root), '--include-vectors'])
        self.assertEqual(code, 0)
        proposal = json.loads(output.getvalue())
        self.publish(proposal)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['canonical', 'verify', '--target', str(self.root)]), 0)
            self.assertEqual(main(['canonical', 'status', '--target', str(self.root)]), 0)

    def test_git_attributes_prevent_canonical_crlf_conversion(self):
        self.publish_runtime(self.build())
        self.publish(self.stage())
        git(self.root, 'add', 'project-knowledge')
        git(self.root, 'commit', '-m', 'portable text')
        clone = self.base / 'autocrlf-clone'
        git(self.base, '-c', 'core.autocrlf=true', 'clone', str(self.root), str(clone))
        with verified_snapshot(clone / 'project-knowledge', self.cache(clone)):
            pass


    def test_source_edit_during_parse_cannot_poison_prior_byte_identity(self):
        from pi_platform.adapters.markdown.markdown_adapter import MarkdownAdapter
        original = MarkdownAdapter.parse
        def raced(adapter, source, context):
            parsed = original(adapter, source, context)
            if source.id == 'repo:billing.md':
                Path(source.uri).write_text('changed while parsing\n')
            return parsed
        with patch.object(MarkdownAdapter, 'parse', raced):
            with self.assertRaisesRegex(RuntimeError, 'Incomplete ingestion'):
                self.build()
        with closing(sqlite3.connect(self.cache() / 'indexing-state.sqlite')) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM source_outputs WHERE source_id='repo:billing.md'").fetchone()[0], 0)

    def test_one_verification_plan_and_no_warm_source_or_vector_rewrites(self):
        self.publish_runtime(self.build())
        self.publish(self.stage(vectors=True))
        from pi_platform.adapters.sync.portable_snapshot_reader import read_snapshot
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import SqliteIngestionCache
        from pi_platform.adapters.runtime.sqlite_vector_record_store import SqliteVectorRecordStore
        def no_vector_write(store, records):
            self.assertFalse(records, 'warm vector data rewritten')
        with patch('pi_platform.adapters.sync.portable_snapshot_reader.read_snapshot', wraps=read_snapshot) as verify, \
                patch.object(SqliteIngestionCache, 'complete_source_atomic', side_effect=AssertionError('warm source rewritten')), \
                patch.object(SqliteVectorRecordStore, 'put_many', no_vector_write):
            warm = self.build()
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(warm.extra['portable_import']['importedSources'], 0)
        self.assertEqual(warm.extra['portable_import']['reusedLocalSources'], 2)
        self.assertEqual(warm.extra['portable_import']['importedVectors'], 0)

    def test_production_source_parser_admits_parallel_workers(self):
        import threading
        from pi_platform.adapters.markdown.markdown_adapter import MarkdownAdapter
        original = MarkdownAdapter.parse
        barrier = threading.Barrier(2)
        threads = set()
        lock = threading.Lock()
        def concurrent(adapter, source, context):
            with lock:
                threads.add(threading.get_ident())
            barrier.wait(timeout=10)
            return original(adapter, source, context)
        with patch('pi_platform.adapters.runtime.host_resources.parse_worker_budget', return_value=2), \
                patch.object(MarkdownAdapter, 'parse', concurrent):
            runtime = self.build()
        self.assertEqual(len(threads), 2)
        self.assertEqual(runtime.extra['source_parse_misses'], 2)

    def test_signed_retry_repairs_corrupt_shard_and_verifies_success(self):
        self.publish_runtime(self.build())
        proposal = self.stage(vectors=True)
        self.publish(proposal)
        shard = next((self.root / 'project-knowledge/objects/portable-v2').glob('*.jsonl'))
        shard.write_bytes(b'corrupt\n')
        repaired = self.publish(proposal)
        self.assertIn(shard.relative_to(self.root / 'project-knowledge').as_posix(), repaired['changedPaths'])
        with verified_snapshot(self.root / 'project-knowledge', self.cache()):
            pass

    def test_independent_fresh_parses_in_different_paths_are_identical(self):
        self.publish_runtime(self.build())
        first = self.stage(vectors=True)
        other = self.base / 'fresh-independent-root'
        other.mkdir()
        for name in ('billing.md', 'shipping.md'):
            shutil.copyfile(self.root / name, other / name)
        runtime = self.build(other)
        self.publish_runtime(runtime, other)
        second = self.materialise.stage_active_index(other, cache_root=self.cache(other), include_vectors=True)
        self.assertEqual(first['snapshotId'], second['snapshotId'])

    def test_python_graph_and_document_structure_roundtrip(self):
        (self.root / 'billing.py').write_text('class Refund:\n    def approve(self):\n        return True\n')
        git(self.root, 'add', 'billing.py')
        git(self.root, 'commit', '-m', 'Python graph source')
        runtime = self.build()
        self.publish_runtime(runtime)
        self.publish(self.stage(vectors=True))
        clone = self.clone()
        with patch('pi_platform.adapters.python.intelligence.PythonSourceAdapter.parse',
                   side_effect=AssertionError('Python parsed on clone')):
            restored = self.build(clone)
        self.assertEqual(runtime.extra['graph_node_ids'], restored.extra['graph_node_ids'])
        self.assertTrue(runtime.extra['graph_node_ids'])
        self.assertEqual(runtime.extra['chunk_ids'], restored.extra['chunk_ids'])
        self.assertEqual(restored.extra['indexing_report'].embedded_count, 0)

    def test_automatic_review_and_signed_auto_publication_no_monitor_loop(self):
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.core.sync.version_monitor import PollingProjectVersionMonitor, read_project_version
        from pi_platform.core.sync.version_snapshot import RuntimeSnapshotService
        first = _bootstrap_and_index_target(self.root)
        self.assertTrue(first['ready'])
        self.assertEqual(first['portable_export']['state'], 'pending-review')
        self.assertFalse((self.root / 'project-knowledge' / ROOT).exists())
        capability = self.boundary.issue(ApprovalRequest(action='materialise', repo_root=str(self.root)))
        with patch.dict(os.environ, {'PI_PORTABLE_EXPORT': 'approved-auto',
                'PI_OPERATOR_APPROVAL_KEY': 'test-only-local-key', 'PI_PORTABLE_APPROVAL_TOKEN': capability}):
            result = _bootstrap_and_index_target(self.root)
            self.assertEqual(result['portable_export']['state'], 'published')
            version = read_project_version(self.root)
            persisted = RuntimeSnapshotService(cache_root=self.cache()).read_snapshot()
            self.assertEqual(persisted.active.working_tree_fingerprint, version.working_tree_fingerprint)
            monitor = PollingProjectVersionMonitor(self.root, on_change=lambda _: _bootstrap_and_index_target(self.root))
            monitor._previous = version
            self.assertIsNone(monitor.poll_once())
            with patch('pi_platform.adapters.markdown.markdown_adapter.MarkdownAdapter.parse', side_effect=AssertionError('auto repeat parsed')):
                repeated = _bootstrap_and_index_target(self.root)
            self.assertEqual(repeated['portable_export']['changedPaths'], [])
            self.assertEqual(repeated['new_vectors'], 0)

    def test_automatic_denial_keeps_query_generation_ready(self):
        from pi_platform.cli.main import _bootstrap_and_index_target
        with patch.dict(os.environ, {'PI_PORTABLE_EXPORT': 'approved-auto', 'PI_PORTABLE_APPROVAL_TOKEN': 'forged'}):
            result = _bootstrap_and_index_target(self.root)
        self.assertTrue(result['ready'])
        self.assertEqual(result['portable_export']['state'], 'failed')
        self.assertFalse((self.root / 'project-knowledge' / ROOT).exists())

    def test_rest_selector_uses_real_materialiser_and_scoped_approval(self):
        from tests.test_phase_9_rest_core import build_service, ACTOR
        from pi_platform.ports.ui.rest_api import MaterializeRequest
        self.publish_runtime(self.build())
        token = self.boundary.issue(ApprovalRequest(action='materialise', repo_root=str(self.root)))
        service = build_service(repo_root=self.root, materialise=self.materialise, approval=self.boundary)
        result = service.materialize(ACTOR, MaterializeRequest(approval_token=token,
            from_active_index=True, preview=True, include_vectors=True))
        self.assertFalse(result.materialized)
        self.assertEqual(result.reason, 'pending review')
        published = service.materialize(ACTOR, MaterializeRequest(approval_token=token,
            from_active_index=True, staging_id=result.proposal['stagingId']))
        self.assertTrue(published.materialized)



class PortableFormatTests(unittest.TestCase):
    def test_segmented_pages_size_bounds_hashes_and_determinism(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            identities = []
            for iteration in range(2):
                with spool(base) as db:
                    order = range(1000) if iteration == 0 else reversed(range(1000))
                    for i in order:
                        add_record(db, 'payload', str(i), {'text': 'x' * 250})
                    root = base / str(iteration)
                    descriptor = write_snapshot(db, root, cap=1024)
                    identities.append(descriptor['snapshotId'])
                    self.assertTrue(all(p.stat().st_size <= 1024 for p in root.rglob('*') if p.is_file()))
                with spool(base) as db:
                    report = read_snapshot(root, db, cap=1024)
                    self.assertEqual(report['records'], 1000)
            self.assertEqual(identities[0], identities[1])

    def test_oversize_and_budget_reject_before_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with spool(root) as db:
                add_record(db, 'payload', 'big', {'text': 'x' * 2048})
                with self.assertRaisesRegex(PortableSnapshotError, 'Oversized'):
                    write_snapshot(db, root / 'knowledge', cap=1024)
                self.assertFalse((root / 'knowledge' / ROOT).exists())
            with spool(root) as db:
                add_record(db, 'payload', 'a', {})
                with self.assertRaisesRegex(PortableSnapshotError, 'budget'):
                    write_snapshot(db, root / 'budget', max_total=1)

    def test_paths_links_reserved_names_and_duplicate_json(self):
        for value in ('../escape', '/etc/passwd', 'a/../b', 'a\\b', 'CON.txt', 'a:stream', 'a./b'):
            with self.subTest(value=value), self.assertRaises(PortableSnapshotError):
                source_path(value)
        with self.assertRaises(PortableSnapshotError):
            decode(b'{"a":1,"a":2}\n')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            try:
                (root / 'link').symlink_to(root, target_is_directory=True)
            except OSError:
                return  # Windows without symlink privilege still checks path/JSON cases.
            with self.assertRaises(PortableSnapshotError):
                confined(root, 'link/file.json')

    def test_portable_import_batches_durable_commits_without_partial_sources(self):
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import SqliteIngestionCache, exclusive_indexer
        def sources(count):
            for i in range(count):
                payload = encode({'id': str(i)})
                address, key = sha(payload), sha(f'pipeline-{i}'.encode())
                summary = encode({'addresses': [address], 'chunkCount': 0})
                yield (f'repo:source-{i}.md', sha(str(i).encode()), key, [address], sha(b'metadata'),
                       {address: payload, key: summary})
        with tempfile.TemporaryDirectory() as temporary, exclusive_indexer(temporary):
            cache = SqliteIngestionCache(Path(temporary) / 'indexing-state.sqlite')
            try:
                statements = []
                cache._db.set_trace_callback(statements.append)
                self.assertEqual(cache.import_portable_sources(sources(65)), 65)
                self.assertEqual(sum(s == 'COMMIT' for s in statements), 2)
                self.assertEqual(len(cache.source_ids()), 65)
            finally:
                cache.close()
        with tempfile.TemporaryDirectory() as temporary, exclusive_indexer(temporary):
            cache = SqliteIngestionCache(Path(temporary) / 'indexing-state.sqlite')
            def interrupted():
                yield from sources(64)
                raise OSError('interrupt after committed group')
            try:
                with self.assertRaises(OSError):
                    cache.import_portable_sources(interrupted())
                self.assertEqual(len(cache.source_ids()), 64)
            finally:
                cache.close()

    def test_legacy_jsonl_hydration_counts_real_hits_and_rejects_corruption(self):
        from pi_platform.core.sync.hydrate import HydrateService
        from pi_platform.core.canonical import Shard, manifest_from_shards
        from pi_platform.runtime import RuntimeCache
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'graph/nodes/a.jsonl'
            path.parent.mkdir(parents=True)
            raw = encode({'id': 'a', 'label': 'Alpha'}) + encode({'id': 'b', 'label': 'Beta'})
            path.write_bytes(raw)
            shard = Shard(id='nodes/a', path='graph/nodes/a.jsonl', contentHash=sha(raw), count=2)
            manifest = manifest_from_shards('graph', [shard])
            cache = RuntimeCache(root / 'cache')
            service = HydrateService(cache=cache)
            self.assertEqual(service._hydrate_family(root, manifest, cache, root), (0, 1))
            self.assertEqual(service._hydrate_family(root, manifest, cache, root), (1, 1))
            path.write_bytes(b'{}\n')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                service._hydrate_family(root, manifest, cache, root)

    def test_legacy_graph_cap_rejects_without_replacing_previous_shard(self):
        from pi_platform.adapters.runtime.sharded_graph import LocalShardedGraph
        from pi_platform.ports.runtime.graph import GraphPortError
        with tempfile.TemporaryDirectory() as temp:
            graph = LocalShardedGraph(Path(temp))
            path = graph.root / 'nodes/a/shard.jsonl'
            path.parent.mkdir()
            prior = encode({'id': 'a'})
            path.write_bytes(prior)
            graph.MAX_SHARD_BYTES = len(prior) + 1
            with self.assertRaises(GraphPortError):
                graph._write_shard_line(path, encode({'id': 'b'}), lambda raw: json.loads(raw)['id'])
            self.assertEqual(path.read_bytes(), prior)

    def test_export_rejects_machine_metadata_and_credentials(self):
        from pi_platform.adapters.sync.portable_snapshot_reader import validate_payload
        for body in ({'rationale': '/private/host/project/source.md'},
                     {'metadata': {'system_prompt': 'private runtime instruction'}},
                     {'metadata': {'api_key': 'private credential'}}):
            with self.subTest(body=tuple(body)), self.assertRaises(PortableSnapshotError):
                validate_payload(encode(body), local_root='/private/host/project')
        with self.assertRaises(PortableSnapshotError):
            validate_payload(encode([]))

    def test_vector_exact_float32_and_invalid_values(self):
        from pi_platform.adapters.sync.portable_vectors import encode_record, decode_record
        from pi_platform.ports.runtime.vector_record_store import VectorRecord
        from pi_platform.core.retrieval.semantic_index_service import encode_vector_payload
        record = VectorRecord('c', 'content', 'a'*64, 'revision', 3, 'none',
                              encode_vector_payload([0.123456789, -100.456789, 1.1]), 'b'*64)
        body = encode_record(record)
        self.assertEqual(decode_record(json.loads(encode(body))).vector_payload, record.vector_payload)
        for vector in ([float('nan'), 1, 0], [1], [1e100, 0, 0]):
            with self.assertRaises(PortableSnapshotError):
                decode_record({**body, 'vector': vector})
