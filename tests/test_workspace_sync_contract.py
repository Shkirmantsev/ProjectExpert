"""Safety proofs for source commit/publication and host identity bridging."""
import json
import os
from unittest.mock import patch
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest

from pi_platform.core.sync.project_lock import ProjectLock
from pi_platform.core.sync.workspace_sync_contract import WorkspaceSyncFence, WorkspaceUnavailable
from pi_platform.core.sync.version_monitor import read_project_version
from pi_platform.core.git.version_identity import compute_version_identity


def mutate(root, acquired):
    state = Path(root) / '.projectexpert-workspace'
    with ProjectLock('commit', root=state).acquire():
        acquired.set()
        (Path(root) / 'evidence.md').write_text('second source')
        payload = json.loads((state / 'applied-generation.json').read_text())
        payload['generation'] = 'two'
        (state / 'applied-generation.json').write_text(json.dumps(payload))


class WorkspaceFenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / '.projectexpert-workspace'
        self.state.mkdir()
        (self.state / 'managed.json').write_text('{"schema_version":1}')
        (self.state / 'commit.lock').touch()
        (self.root / 'evidence.md').write_text('first source')
        self.write()

    def write(self, **updates):
        payload = {'schema_version': 1, 'generation': 'one',
                   'vcs': {'provider': 'git', 'head': 'abc123', 'branch': 'topic'}}
        payload.update(updates)
        (self.state / 'applied-generation.json').write_text(json.dumps(payload))

    def test_bind_has_no_metadata_or_lock_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with WorkspaceSyncFence(root).lease() as value:
                self.assertIsNone(value)
            self.assertEqual(list(root.iterdir()), [])

    def test_explicit_volume_never_falls_back_to_bind_when_metadata_is_lost(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'PI_WORKSPACE_MODE': 'volume'}):
            with self.assertRaises(WorkspaceUnavailable):
                WorkspaceSyncFence(Path(directory)).committed()

    def test_managed_missing_importing_or_invalid_metadata_fails_closed(self):
        fence = WorkspaceSyncFence(self.root)
        for filename in ('managed.json', 'applied-generation.json'):
            path = self.state / filename
            saved = path.read_bytes()
            path.unlink()
            with self.assertRaises(WorkspaceUnavailable):
                fence.committed()
            path.write_bytes(saved)
        (self.state / 'importing.json').write_text('{}')
        with self.assertRaises(WorkspaceUnavailable):
            fence.committed()
        (self.state / 'importing.json').unlink()
        self.write(schema_version=2)
        with self.assertRaises(WorkspaceUnavailable):
            fence.committed()

    def test_import_cannot_mutate_during_complete_index_publication_lease(self):
        acquired = multiprocessing.Event()
        with WorkspaceSyncFence(self.root).lease() as source:
            process = multiprocessing.Process(target=mutate, args=(str(self.root), acquired))
            process.start()
            self.assertFalse(acquired.wait(.15))
            self.assertEqual((self.root / 'evidence.md').read_text(), 'first source')
            self.assertEqual(source['generation'], 'one')
            # A simulated final index publication still sees the original tree.
            self.assertEqual(WorkspaceSyncFence(self.root).committed(), source)
        self.assertTrue(acquired.wait(3))
        process.join(3)
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(WorkspaceSyncFence(self.root).committed()['generation'], 'two')

    def test_git_worktree_and_branch_identity_reaches_hydration_identity(self):
        version = read_project_version(self.root)
        self.assertEqual((version.head, version.branch), ('abc123', 'topic'))
        self.assertEqual(compute_version_identity(self.root).gitHead, 'abc123')
        self.write(generation='two', vcs={'provider': 'git', 'head': 'abc123', 'branch': 'other'})
        self.assertNotEqual(version, read_project_version(self.root))

    def test_svn_identity_and_local_same_size_edit(self):
        self.write(vcs={'provider': 'svn', 'revision': '42'})
        before = read_project_version(self.root)
        self.assertEqual(before.head, '42')
        (self.root / 'evidence.md').write_text('other source')
        self.assertNotEqual(before.working_tree_fingerprint, read_project_version(self.root).working_tree_fingerprint)

    def test_canonical_change_changes_identity_with_same_sync_generation(self):
        canonical = self.root / 'project-knowledge' / 'wiki'
        canonical.mkdir(parents=True)
        page = canonical / 'page.md'
        page.write_text('revision A')
        before = read_project_version(self.root)
        page.write_text('revision B')
        self.assertNotEqual(before, read_project_version(self.root))
