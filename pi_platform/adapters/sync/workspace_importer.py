"""Restricted tar receiver. A durable journal keeps refresh fenced until replay completes."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import time
import tempfile
import unicodedata
from pi_platform.core.sync.project_lock import ProjectLock

MAX_FILES = 200_000
MAX_BYTES = 20 * 1024**3
RESERVED = {'.git', '.svn', '.hg', '.projectexpert-workspace', 'project-knowledge', '.project-intelligence-cache', '.project-intelligence-deploy', 'node_modules', '__pycache__', '.venv', 'venv', 'target', 'build', 'dist', 'out', '.next', 'vendor', 'third_party', 'generated', '.generated'}

def safe_path(name):
    p = PurePosixPath(name)
    if name == 'tmp/local' or name.startswith('tmp/local/') or name == 'distribution/sbom' or name.startswith('distribution/sbom/'):
        raise ValueError('excluded source path')
    if not name or '\\' in name or ':' in name or p.is_absolute() or str(p) != name or any(x in {'', '.', '..'} for x in name.split('/')):
        raise ValueError('unsafe source path')
    for x in p.parts:
        low = x.lower()
        if low in RESERVED or low.startswith('.env') or low.endswith(('.pem', '.key', '.p12', '.pfx')) or low in {'id_rsa', 'id_ed25519', 'id_ecdsa', 'id_dsa', 'credentials', 'credentials.json', '.ssh', '.aws', '.azure', '.kube', '.docker', '.npmrc', '.pypirc', '.netrc', '.git-credentials'}:
            raise ValueError('excluded source path')
    return p

def atomic_json(path, value):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(value, f, sort_keys=True)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def confined(root, name):
    safe_path(name)
    path = root / name
    for parent in [path, *path.parents]:
        if parent == root: break
        if parent.is_symlink(): raise ValueError('symlink destination')
    return path

def validate(manifest):
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('generation'), str) or not manifest['generation']:
        raise ValueError('invalid generation')
    files = manifest.get('files')
    if not isinstance(files, dict) or len(files) > MAX_FILES: raise ValueError('file limit')
    seen = set(); total = 0
    for name, item in files.items():
        safe_path(name)
        key = unicodedata.normalize('NFC', name).casefold()
        if key in seen: raise ValueError('case or unicode collision')
        seen.add(key)
        if not isinstance(item, dict) or type(item.get('size')) is not int or item['size'] < 0 or len(item.get('sha256', '')) != 64:
            raise ValueError('invalid file metadata')
        int(item['sha256'], 16); total += item['size']
    if total > MAX_BYTES: raise ValueError('byte limit')
    for name in files:
        if any(str(p) in files for p in PurePosixPath(name).parents if str(p) != '.'): raise ValueError('file directory collision')
    if not isinstance(manifest.get('vcs', {}), dict): raise ValueError('invalid vcs')
    return files

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def sync_workspace(descriptor):
    """Flush the same Linux filesystem before journal/publication barriers.

    Per-file fsync makes a 30k-file initial import needlessly serial. syncfs
    covers file contents, access modes, renames and directory entries together.
    The importer holds the exclusive workspace lease and has no host bind.
    """
    library = ctypes.CDLL(None, use_errno=True)
    try:
        syncfs = library.syncfs
    except AttributeError as exc:
        raise RuntimeError('Managed workspace requires Linux syncfs support') from exc
    syncfs.argtypes = [ctypes.c_int]
    syncfs.restype = ctypes.c_int
    if syncfs(descriptor) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))


def replay(root, state, descriptor):
    journal = state / 'importing.json'
    if not journal.exists(): return
    tx = json.loads(journal.read_text())
    manifest = tx['manifest']; files = validate(manifest)
    stage = state / 'stage'
    for name in tx['deleted']:
        dst = confined(root, name)
        if dst.is_file():
            dst.unlink()
    # Stage files are retained until metadata publication, making replay idempotent.
    for name in tx['changed']:
        src = confined(stage, name); dst = confined(root, name)
        if src.stat().st_size != files[name]['size'] or digest(src) != files[name]['sha256']: raise ValueError('corrupt recovery stage')
        if dst.exists() and dst.is_dir(): shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        temporary_fd, temporary = tempfile.mkstemp(prefix='.workspace-import-', dir=state)
        tmp = Path(temporary)
        try:
            with src.open('rb') as a, os.fdopen(temporary_fd, 'wb') as b:
                shutil.copyfileobj(a, b, 1024*1024); b.flush()
                os.fchmod(b.fileno(), 0o644)
            os.replace(tmp, dst)
        finally:
            tmp.unlink(missing_ok=True)
    sync_workspace(descriptor)
    published = dict(manifest, last_sync=time.time(), pending_files=0)
    atomic_json(state / 'applied-generation.json', published)
    journal.unlink()
    directory = os.open(state, os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)
    shutil.rmtree(stage)

def receive(stream, root, owner_uid=None, owner_gid=None):
    if sys.platform != 'linux':
        raise RuntimeError('Workspace importer requires Linux containers; use the native host agent')
    root = Path(root).absolute(); root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink(): raise ValueError('symlink root')
    # Open before staging/replay writes: syncfs must retain its error-sequence
    # baseline across asynchronous writeback in both phases.
    descriptor = os.open(root, os.O_RDONLY)
    try:
        return _receive(stream, root, owner_uid, owner_gid, descriptor)
    finally:
        os.close(descriptor)

def _receive(stream, root, owner_uid, owner_gid, descriptor):
    state = root / '.projectexpert-workspace'
    if state.is_symlink(): raise ValueError('symlink state')
    state.mkdir(exist_ok=True)
    if owner_uid is not None and owner_gid is not None:
        os.chown(root, owner_uid, owner_gid)
        os.chown(state, owner_uid, owner_gid)
    with ProjectLock('commit', root=state).acquire():
        for name in ('project-knowledge', '.project-intelligence-cache'):
            mountpoint = root / name
            if mountpoint.is_symlink(): raise ValueError('linked mountpoint')
            mountpoint.mkdir(exist_ok=True)
        atomic_json(state / 'managed.json', {'schema_version': 1})
        replay(root, state, descriptor)
        stage = state / 'stage'
        if stage.exists(): shutil.rmtree(stage)
        stage.mkdir()
        try:
            with tarfile.open(fileobj=stream, mode='r|') as archive:
                first = archive.next()
                if first is None or first.name != 'manifest.json' or not first.isfile() or first.size > 64*1024*1024: raise ValueError('manifest must be first')
                manifest = json.load(archive.extractfile(first)); files = validate(manifest)
                changed = set()
                while True:
                    entry = archive.next()
                    if entry is None: break
                    name = entry.name; safe_path(name)
                    if not entry.isfile() or name not in files or name in changed or entry.size != files[name]['size']: raise ValueError('unexpected archive entry')
                    dst = confined(stage, name); dst.parent.mkdir(parents=True, exist_ok=True)
                    with dst.open('xb') as out:
                        shutil.copyfileobj(archive.extractfile(entry), out, 1024*1024); out.flush()
                    if digest(dst) != files[name]['sha256']: raise ValueError('hash mismatch')
                    changed.add(name)
            old_path = state / 'applied-generation.json'
            old = json.loads(old_path.read_text())['files'] if old_path.exists() else {}
            for name, item in files.items():
                if name not in changed:
                    dst = confined(root, name)
                    if old.get(name) != item or not dst.is_file() or dst.stat().st_size != item['size'] or digest(dst) != item['sha256']: raise ValueError('missing changed payload')
            for name in old: safe_path(name)
            if shutil.disk_usage(root).free < sum(files[n]['size'] for n in changed): raise OSError('insufficient workspace staging space')
            tx = {'manifest': manifest, 'changed': sorted(changed), 'deleted': sorted(set(old)-set(files))}
            sync_workspace(descriptor)
            atomic_json(state / 'importing.json', tx)
            replay(root, state, descriptor)
            return manifest['generation']
        except BaseException:
            if not (state / 'importing.json').exists(): shutil.rmtree(stage, ignore_errors=True)
            raise

def main():
    p = argparse.ArgumentParser(); p.add_argument('--root', default='/repo'); p.add_argument('--owner-uid', type=int); p.add_argument('--owner-gid', type=int)
    a = p.parse_args(); receive(sys.stdin.buffer, a.root, a.owner_uid, a.owner_gid)
if __name__ == '__main__': main()
