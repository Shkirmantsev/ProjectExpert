import hashlib
import io
import json
import tarfile
from pathlib import Path
import unittest
import tempfile
from unittest import mock
from contextlib import contextmanager

class Raises:
    @staticmethod
    @contextmanager
    def raises(kind):
        try: yield
        except kind: return
        raise AssertionError(f"expected {kind}")
pytest=Raises()
from pi_platform.adapters.sync import workspace_importer as w


def stream(files, payload=None, generation='one'):
    manifest = {'schema_version': 1, 'generation': generation, 'files': {n: {'size': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for n,b in files.items()}, 'vcs': {'provider': 'none'}}
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as tar:
        data=json.dumps(manifest).encode(); entry=tarfile.TarInfo('manifest.json'); entry.size=len(data); tar.addfile(entry,io.BytesIO(data))
        for n,b in (files if payload is None else payload).items():
            entry=tarfile.TarInfo(n); entry.size=len(b); tar.addfile(entry,io.BytesIO(b))
    out.seek(0); return out


def check_full_incremental_delete(tmp_path):
    w.receive(stream({'src/a': b'a', 'gone': b'x'}), tmp_path)
    w.receive(stream({'src/a': b'a', 'new': b'next'}, {'new': b'next'}, 'two'), tmp_path)
    assert not (tmp_path/'gone').exists()
    assert (tmp_path/'new').read_bytes()==b'next'
    w.receive(stream({'src/a': b'a', 'new': b'next'}, {}, 'three'), tmp_path)
    assert json.loads((tmp_path/'.projectexpert-workspace/applied-generation.json').read_text())['generation']=='three'


def check_reject_unsafe(tmp_path,name):
    with pytest.raises(ValueError): w.receive(stream({name:b'bad'}),tmp_path)
    assert not (tmp_path/'.projectexpert-workspace/applied-generation.json').exists()


def check_hash_rejection_preserves_generation(tmp_path):
    w.receive(stream({'a':b'old'}),tmp_path)
    with pytest.raises(ValueError): w.receive(stream({'a':b'new'}, {'a':b'bad'}),tmp_path)
    assert (tmp_path/'a').read_bytes()==b'old'


def check_symlink_and_collision(tmp_path):
    (tmp_path/'linked').symlink_to(tmp_path.parent,target_is_directory=True)
    with pytest.raises(ValueError): w.receive(stream({'linked/file':b'x'}),tmp_path)
    with pytest.raises(ValueError): w.receive(stream({'A':b'a','a':b'b'}),tmp_path)


def check_interrupted_apply_replays(tmp_path):
    original=w.atomic_json
    def fail(path,value):
        if path.name=='applied-generation.json': raise OSError('simulated power loss')
        return original(path,value)
    with mock.patch.object(w,'atomic_json',fail):
        with pytest.raises(OSError): w.receive(stream({'a':b'content'}),tmp_path)
    assert (tmp_path/'.projectexpert-workspace/importing.json').exists()
    w.receive(stream({'a':b'content'}, {}, 'recovered'),tmp_path)
    assert not (tmp_path/'.projectexpert-workspace/importing.json').exists()
    assert (tmp_path/'a').read_bytes()==b'content'


def check_file_directory_transitions(tmp_path):
    w.receive(stream({'a':b'a'}),tmp_path)
    w.receive(stream({'a/child':b'b'}),tmp_path)
    assert (tmp_path/'a/child').read_bytes()==b'b'
    w.receive(stream({'a':b'c'}),tmp_path)
    assert (tmp_path/'a').read_bytes()==b'c'


class WorkspaceImporterTests(unittest.TestCase):
    def run_case(self, fn, *args):
        with tempfile.TemporaryDirectory() as directory:
            fn(Path(directory), *args)
    def test_full(self): self.run_case(check_full_incremental_delete)
    def test_security(self):
        for name in ['../outside','/absolute','a/../b','a\\b','project-knowledge/wiki/a','.projectexpert-workspace/x','.git/config','.env.production','secrets/key.pem','A:x']:
            with self.subTest(name=name): self.run_case(check_reject_unsafe,name)
    def test_hash(self): self.run_case(check_hash_rejection_preserves_generation)
    def test_collision(self): self.run_case(check_symlink_and_collision)
    def test_recovery(self): self.run_case(check_interrupted_apply_replays)
    def test_temporary_names_do_not_overwrite_legitimate_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            w.receive(stream({'a': b'one', 'a.workspace-tmp': b'preserved'}), root)
            w.receive(stream({'a': b'two', 'a.workspace-tmp': b'preserved'}, {'a': b'two'}, 'two'), root)
            self.assertEqual((root / 'a.workspace-tmp').read_bytes(), b'preserved')
            self.assertEqual((root / 'a').stat().st_mode & 0o777, 0o644)

    def test_durability_barrier_failure_requires_recovery_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            w.receive(stream({'a': b'old'}), root)
            original = w.sync_workspace
            calls = []
            def fail_after_mutation(path):
                calls.append(path)
                if len(calls) == 2:
                    raise OSError('simulated syncfs failure')
                return original(path)
            with mock.patch.object(w, 'sync_workspace', side_effect=fail_after_mutation):
                with self.assertRaises(OSError):
                    w.receive(stream({'a': b'new'}, generation='two'), root)
            from pi_platform.core.sync.workspace_sync_contract import WorkspaceSyncFence, WorkspaceUnavailable
            with self.assertRaises(WorkspaceUnavailable):
                WorkspaceSyncFence(root).committed()
            w.receive(stream({'a': b'new'}, {}, 'two'), root)
            self.assertEqual(WorkspaceSyncFence(root).committed()['generation'], 'two')
            self.assertEqual((root / 'a').read_bytes(), b'new')

    def test_syncfs_descriptor_is_open_before_staging_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actual_sync, actual_atomic = w.sync_workspace, w.atomic_json
            descriptors, metadata = [], []
            def sync(descriptor):
                self.assertIsInstance(descriptor, int)
                self.assertTrue(__import__('stat').S_ISDIR(__import__('os').fstat(descriptor).st_mode))
                descriptors.append(descriptor)
                return actual_sync(descriptor)
            def atomic(path, value):
                metadata.append(path.name)
                return actual_atomic(path, value)
            with mock.patch.object(w, 'sync_workspace', side_effect=sync), mock.patch.object(w, 'atomic_json', side_effect=atomic):
                w.receive(stream({'a': b'content'}), root)
            self.assertEqual(len(descriptors), 2)
            self.assertEqual(descriptors[0], descriptors[1])
            with self.assertRaises(OSError):
                __import__('os').fstat(descriptors[0])
            self.assertIn('importing.json', metadata)

    def test_transitions(self): self.run_case(check_file_directory_transitions)

if __name__ == '__main__': unittest.main()
