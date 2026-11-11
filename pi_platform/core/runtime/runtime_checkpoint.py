"""Generation-coordinated, credential-free derived-runtime checkpoints."""
from contextlib import ExitStack, closing
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import time

SCHEMA_VERSION = 1
# Deliberately exclude HOME, settings/chat keys, model assets and arbitrary files.
DERIVED_FILES = frozenset({
    'runtime.db', 'embeddings.sqlite', 'index.json', 'wal.jsonl', 'documents-v2.sqlite',
    'ingestion.json', 'source-inventory.json', 'workspace-index.json',
})
DERIVED_TREES = frozenset({'objects', 'indexes', 'runtime-state', 'document-assets', 'dense', 'graph'})


class CheckpointError(RuntimeError):
    pass


def product_version():
    try:
        return version('pi-platform')
    except PackageNotFoundError:
        return '0.1.0'


def atomic_json(path: Path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.checkpoint-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == 'posix':
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sync_directories(root: Path):
    if os.name != 'posix':
        return
    paths = [p for p in Path(root).rglob('*') if p.is_dir()] + [Path(root)]
    for path in sorted(paths, key=lambda p: len(p.parts), reverse=True):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def safe_relative(raw: str) -> str:
    path = PurePosixPath(raw)
    if (not raw or '\\' in raw or ':' in raw or '\x00' in raw or path.is_absolute()
            or any(p in {'', '.', '..'} for p in raw.split('/'))):
        raise CheckpointError('Unsafe checkpoint path')
    return path.as_posix()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def _allowed(relative):
    parts = PurePosixPath(relative).parts
    return (relative in DERIVED_FILES or parts[0] in DERIVED_TREES) and not (
        relative.endswith(('-wal', '-shm', '.tmp', '.lock')) or '.tmp' in parts
    )


def _files(root):
    selected = []
    for name in sorted(DERIVED_FILES | DERIVED_TREES):
        path = root / name
        if path.is_symlink():
            raise CheckpointError('Linked runtime artifact')
        candidates = sorted(path.rglob('*')) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_symlink():
                raise CheckpointError('Linked runtime artifact')
            if candidate.is_file():
                rel = candidate.relative_to(root).as_posix()
                if _allowed(rel):
                    if candidate.stat().st_nlink != 1:
                        raise CheckpointError('Hard-linked runtime artifact')
                    selected.append(candidate)
    return selected


class RuntimeCheckpointService:
    """Caller holds the project writer lock for the complete checkpoint.

    SQLite write barriers cover all databases together. Separate reader
    connections use online backup while those barriers prevent changing any
    database in the set. File fingerprints and the active bundle are checked
    again before completion. Unsupported mutable files fail closed.
    """
    def __init__(self, cache_root: Path, *, max_bytes=20 * 1024**3, timeout=120):
        self.cache_root = Path(cache_root)
        self.max_bytes = max_bytes
        self.timeout = timeout

    def create(self, destination: Path) -> Path:
        from ..sync.version_snapshot import RuntimeSnapshotService
        snapshot = RuntimeSnapshotService(cache_root=self.cache_root).read_snapshot()
        if snapshot is None:
            raise CheckpointError('No published runtime generation to checkpoint')
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise CheckpointError('Checkpoint destination must be new')
        readiness_path = self.cache_root / 'readiness.json'
        if readiness_path.is_file():
            ready = json.loads(readiness_path.read_text())
            if not ready.get('consistent') or ready.get('in_progress'):
                raise CheckpointError('Runtime is not ready for a checkpoint')
        files = _files(self.cache_root)
        if sum(p.stat().st_size for p in files) > self.max_bytes:
            raise CheckpointError('Checkpoint exceeds byte limit')
        before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in files}
        databases = []
        for path in files:
            with path.open('rb') as stream:
                if stream.read(16) == b'SQLite format 3\x00':
                    databases.append(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.incomplete-', dir=destination.parent))
        started = time.monotonic()
        try:
            with ExitStack() as stack:
                # Sorted acquisition and a bounded timeout avoid waiting forever
                # on a non-cooperating writer. All connections close on failure.
                for path in databases:
                    connection = sqlite3.connect(path, timeout=min(5, self.timeout))
                    stack.callback(connection.close)
                    connection.execute('BEGIN IMMEDIATE')
                records = {}
                for path in files:
                    if time.monotonic() - started > self.timeout:
                        raise CheckpointError('Checkpoint deadline exceeded')
                    rel = path.relative_to(self.cache_root).as_posix()
                    output = temporary / rel
                    output.parent.mkdir(parents=True, exist_ok=True)
                    if path in databases:
                        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
                            with closing(sqlite3.connect(output)) as target:
                                def progress(_status, _left, _total):
                                    if time.monotonic() - started > self.timeout:
                                        raise CheckpointError('SQLite backup deadline exceeded')
                                source.backup(target, pages=256, progress=progress)
                                target.execute('PRAGMA journal_mode=DELETE')
                                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                                    raise CheckpointError('SQLite checkpoint integrity failure')
                    else:
                        shutil.copyfile(path, output)
                    os.chmod(output, 0o600)
                    with output.open('r+b') as stream:
                        os.fsync(stream.fileno())
                    records[rel] = {'size': output.stat().st_size, 'sha256': digest(output)}
                after = _files(self.cache_root)
                if set(after) != set(files) or any(
                    (p.stat().st_size, p.stat().st_mtime_ns) != before[p]
                    for p in files if p not in databases
                ):
                    raise CheckpointError('Runtime files changed during checkpoint')
                if RuntimeSnapshotService(cache_root=self.cache_root).read_snapshot() != snapshot:
                    raise CheckpointError('Active generation changed during checkpoint')
                active = snapshot.active
                atomic_json(temporary / 'checkpoint-manifest.json', {
                    'schema_version': SCHEMA_VERSION, 'product_version': product_version(),
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'generation': active.active_index_generation,
                    'embedding_profile': active.embedding_profile_identity,
                    'files': records,
                })
                verify_checkpoint(temporary, max_bytes=self.max_bytes)
                sync_directories(temporary)
                os.replace(temporary, destination)
                if os.name == 'posix':
                    descriptor = os.open(destination.parent, os.O_RDONLY)
                    try: os.fsync(descriptor)
                    finally: os.close(descriptor)
            return destination
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise


def verify_checkpoint(root: Path, *, max_bytes=20 * 1024**3, profile=None):
    root = Path(root)
    path = root / 'checkpoint-manifest.json'
    if root.is_symlink() or path.is_symlink():
        raise CheckpointError('Linked checkpoint')
    if path.stat().st_size > 16 * 1024**2:
        raise CheckpointError('Oversized checkpoint manifest')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != SCHEMA_VERSION or manifest.get('product_version') != product_version():
        raise CheckpointError('Incompatible checkpoint schema or product version')
    if profile is not None and manifest.get('embedding_profile') != profile:
        raise CheckpointError('Incompatible embedding profile; rebuild required')
    if not manifest.get('generation') or not isinstance(manifest.get('files'), dict):
        raise CheckpointError('Missing checkpoint generation/files')
    total = 0
    expected = {'checkpoint-manifest.json'}
    for raw, record in manifest['files'].items():
        rel = safe_relative(raw)
        if not _allowed(rel):
            raise CheckpointError('Unapproved runtime checkpoint artifact')
        file = root / rel
        if any(p.is_symlink() for p in [file, *file.parents] if p != root.parent):
            raise CheckpointError('Linked checkpoint artifact')
        size = file.stat().st_size
        total += size
        if total > max_bytes or size != record['size'] or digest(file) != record['sha256']:
            raise CheckpointError('Checkpoint size/checksum mismatch')
        expected.add(rel)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != expected:
        raise CheckpointError('Checkpoint contains unlisted files')
    from ..sync.version_snapshot import RuntimeSnapshotService
    snapshot = RuntimeSnapshotService(cache_root=root).read_snapshot()
    if snapshot is None or snapshot.active.active_index_generation != manifest['generation'] or snapshot.active.embedding_profile_identity != manifest['embedding_profile']:
        raise CheckpointError('Checkpoint does not match its active generation')
    return manifest


def restore_checkpoint(source: Path, inactive_root: Path, *, profile=None):
    """Restore only into an empty, inactive directory; never overwrite live state."""
    manifest = verify_checkpoint(source, profile=profile)
    inactive_root = Path(inactive_root)
    if inactive_root.is_symlink() or (inactive_root.exists() and any(inactive_root.iterdir())):
        raise CheckpointError('Restore requires an empty inactive runtime volume')
    inactive_root.mkdir(parents=True, exist_ok=True)
    copied = []
    try:
        for rel in manifest['files']:
            target = inactive_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(source) / rel, target)
            os.chmod(target, 0o600)
            with target.open('r+b') as stream:
                os.fsync(stream.fileno())
            copied.append(target)
        # The restored runtime must rebuild readiness under the actual current
        # source and model configuration; credentials are never restored.
        sync_directories(inactive_root)
        atomic_json(inactive_root / 'restored-checkpoint.json', {
            'generation': manifest['generation'], 'embedding_profile': manifest['embedding_profile'],
        })
    except Exception:
        for path in copied:
            path.unlink(missing_ok=True)
        raise
    return manifest
