#!/usr/bin/env python3
"""Inspect and safely back up/restore derived indexing SQLite state.

Stop the serving application before restore. The indexer lock prevents builds,
but cannot close query connections owned by a running application process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pi_platform.adapters.runtime.sqlite_ingestion_cache import exclusive_indexer, indexing_progress

DATABASES = ('indexing-state.sqlite', 'indexes/embeddings.sqlite', 'documents-v2.sqlite')
JOURNAL = 'restore-in-progress.json'


class RecoveryError(RuntimeError):
    pass


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def sync_directory(directory):
    if os.name != 'nt':
        handle = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)


def write_json(path, value):
    path = Path(path)
    handle, temporary = tempfile.mkstemp(prefix='.recovery-', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def regular_file(root, name):
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise RecoveryError(f'Missing or linked state file: {name}')
    return path


def check_database(path):
    connection = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro&immutable=1', uri=True)
    try:
        for pragma in ('quick_check', 'integrity_check'):
            results = connection.execute(f'PRAGMA {pragma}').fetchall()
            if results != [('ok',)]:
                raise RecoveryError(f'SQLite {pragma} failed: {path.name}')
    finally:
        connection.close()


def reject_linked_sidecars(path):
    if any(Path(str(path) + suffix).is_symlink() for suffix in ('-wal', '-shm', '-journal')):
        raise RecoveryError(f'Refusing linked SQLite sidecar: {path.name}')


def snapshot_database(source, target):
    reject_linked_sidecars(source)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    reader = sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True, timeout=5)
    writer = sqlite3.connect(target)
    try:
        last_progress = time.monotonic()
        def progress(status, _remaining, _total):
            nonlocal last_progress
            if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                if time.monotonic() - last_progress > 5:
                    raise RecoveryError('SQLite backup is busy; stop other database writers and retry')
            else:
                last_progress = time.monotonic()
        reader.backup(writer, pages=128, progress=progress, sleep=0.05)
        writer.execute('PRAGMA journal_mode=DELETE')
        writer.commit()
    finally:
        writer.close()
        reader.close()
    os.chmod(target, 0o600)
    with target.open('r+b') as stream:
        os.fsync(stream.fileno())
    check_database(target)
    sync_directory(target.parent)


def _backup_locked(cache, destination, *, allow_empty=False):
    if destination.exists() or destination.is_symlink():
        raise RecoveryError('Backup destination already exists; choose a new private directory')
    destination.mkdir(parents=True, mode=0o700)
    os.chmod(destination, 0o700)
    files = []
    for name in DATABASES:
        if (cache / name).exists():
            source = regular_file(cache, name)
            snapshot_database(source, destination / name)
            files.append({'path': name, 'sha256': digest(destination / name), 'bytes': (destination / name).stat().st_size})
    if not files and not allow_empty:
        raise RecoveryError('No indexing databases found; incomplete backup retained for inspection')
    manifest = {'schema_version': 1, 'created_at': time.time(), 'files': files}
    write_json(destination / 'manifest.json', manifest)
    return manifest


def backup(cache, destination):
    cache, destination = Path(cache).resolve(), Path(destination).absolute()
    with exclusive_indexer(cache):
        if (cache / JOURNAL).exists():
            raise RecoveryError('Interrupted restore exists; resume it before starting a new backup')
        return _backup_locked(cache, destination)


def verify_backup(directory, expected_manifest=None, *, allow_empty=False):
    directory = Path(directory).resolve()
    manifest_path = regular_file(directory, 'manifest.json')
    raw = manifest_path.read_bytes()
    if expected_manifest and hashlib.sha256(raw).hexdigest() != expected_manifest:
        raise RecoveryError('Backup manifest changed since restore began')
    data = json.loads(raw)
    if data.get('schema_version') != 1 or not isinstance(data.get('files'), list) or (not data['files'] and not allow_empty):
        raise RecoveryError('Unsupported or empty backup manifest')
    names = set()
    for entry in data['files']:
        name = entry.get('path')
        if name not in DATABASES or name in names:
            raise RecoveryError('Unexpected or duplicate database in backup manifest')
        names.add(name)
        path = regular_file(directory, name)
        if digest(path) != entry.get('sha256') or path.stat().st_size != entry.get('bytes'):
            raise RecoveryError(f'Backup checksum mismatch: {name}')
        if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
            raise RecoveryError(f'Backup is not a standalone SQLite file: {name}')
        check_database(path)
    return data


def _checkpoint_closed(path):
    reject_linked_sidecars(path)
    if not path.exists():
        return
    connection = sqlite3.connect(path, timeout=1)
    try:
        # A busy checkpoint means another process still owns WAL readers/writers.
        result = connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if result and result[0] != 0:
            raise RecoveryError('SQLite is busy; stop the application before restore')
    finally:
        connection.close()


def restore(cache, directory=None, *, resume=False, failure_hook=None):
    cache = Path(cache).resolve()
    hook = failure_hook or (lambda _stage, _name: None)
    with exclusive_indexer(cache):
        journal_path = cache / JOURNAL
        if journal_path.exists():
            if not resume:
                raise RecoveryError('Interrupted restore exists; rerun restore --resume after stopping the application')
            journal = json.loads(regular_file(cache, JOURNAL).read_text())
            if journal.get('schema_version') != 1 or journal.get('cache_root') != str(cache):
                raise RecoveryError('Restore journal identity mismatch; preserve state for manual recovery')
            directory = Path(journal['backup_root'])
            manifest = verify_backup(directory, journal['manifest_sha256'])
            pre_restore = Path(journal['pre_restore_backup'])
            verify_backup(pre_restore, journal['pre_restore_manifest_sha256'], allow_empty=True)
        else:
            if resume:
                raise RecoveryError('No interrupted restore journal exists')
            if directory is None:
                raise RecoveryError('Restore requires a verified backup directory')
            directory = Path(directory).resolve()
            manifest = verify_backup(directory)
            pre_restore = cache / ('pre-restore-' + uuid.uuid4().hex)
            _backup_locked(cache, pre_restore, allow_empty=True)
            journal = {'schema_version': 1, 'cache_root': str(cache), 'backup_root': str(directory),
                       'manifest_sha256': digest(directory / 'manifest.json'),
                       'pre_restore_backup': str(pre_restore),
                       'pre_restore_manifest_sha256': digest(pre_restore / 'manifest.json'), 'completed': []}
            write_json(journal_path, journal)
        hook('journal', None)
        # Each retry gets a new private attempt directory. Never overwrite prior
        # displaced files; an operator can recover either complete snapshot.
        attempt = pre_restore / ('attempt-' + uuid.uuid4().hex)
        attempt.mkdir(mode=0o700)
        for entry in manifest['files']:
            name = entry['path']
            target = cache / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or not target.resolve().is_relative_to(cache):
                raise RecoveryError(f'Refusing linked restore target: {name}')
            _checkpoint_closed(target)
            staged = attempt / 'staged' / name
            snapshot_database(regular_file(directory, name), staged)
            hook('staged', name)
            for suffix in ('', '-wal', '-shm', '-journal'):
                current = Path(str(target) + suffix)
                if current.exists() or current.is_symlink():
                    if current.is_symlink():
                        raise RecoveryError(f'Refusing linked SQLite sidecar: {name}{suffix}')
                    displaced = attempt / 'displaced' / (name + suffix)
                    displaced.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    os.replace(current, displaced)
                    sync_directory(displaced.parent)
            sync_directory(target.parent)
            hook('displaced', name)
            os.replace(staged, target)
            sync_directory(target.parent)
            check_database(target)
            journal['completed'] = sorted(set(journal['completed']) | {name})
            write_json(journal_path, journal)
            hook('promoted', name)
        for entry in manifest['files']:
            check_database(regular_file(cache, entry['path']))
        hook('verified', None)
        journal_path.unlink()
        sync_directory(cache)
        return {'restored': [entry['path'] for entry in manifest['files']], 'pre_restore_backup': str(pre_restore)}


def status(cache):
    cache = Path(cache)
    return {'restore_in_progress': (cache / JOURNAL).exists(),
            'gc_in_progress': (cache / 'gc-in-progress.json').exists(),
            'databases': {name: (cache / name).is_file() for name in DATABASES},
            'indexing': {} if (cache / JOURNAL).exists() else indexing_progress(cache / DATABASES[0])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('status')
    gc = actions.add_parser('gc', help='Plan canonical-state GC; --apply requires stopped serving readers')
    gc.add_argument('--active-job')
    gc.add_argument('--previous-job')
    gc.add_argument('--compatibility-hash')
    gc.add_argument('--ttl-seconds', type=float, default=7 * 86400)
    gc.add_argument('--apply', action='store_true')
    gc.add_argument('--resume', action='store_true')
    gc.add_argument('--min-free-bytes', type=int, default=0)
    gc.add_argument('--min-free-percent', type=float, default=0)
    gc.add_argument('--max-payload-bytes', type=int, default=0)
    gc.add_argument('--max-state-bytes', type=int, default=0)
    actions.add_parser('backup').add_argument('directory', type=Path)
    actions.add_parser('verify').add_argument('directory', type=Path)
    recover = actions.add_parser('restore')
    recover.add_argument('directory', type=Path, nargs='?')
    recover.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.action == 'gc':
        from pi_platform.adapters.runtime.generation_gc import collect
        result = collect(args.cache, active_job=args.active_job, previous_job=args.previous_job,
                         compatibility_hash=args.compatibility_hash, ttl_seconds=args.ttl_seconds,
                         apply=args.apply, resume=args.resume, min_free_bytes=args.min_free_bytes,
                         min_free_percent=args.min_free_percent, max_payload_bytes=args.max_payload_bytes,
                         max_state_bytes=args.max_state_bytes)
    elif args.action == 'status':
        result = status(args.cache)
    elif args.action == 'backup':
        result = backup(args.cache, args.directory)
    elif args.action == 'verify':
        result = verify_backup(args.directory)
    else:
        result = restore(args.cache, args.directory, resume=args.resume)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
