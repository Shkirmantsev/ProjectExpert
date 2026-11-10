"""Restricted local checkpoint CLI used by the host workspace supervisor.

Only completed checkpoints are streamed; input archives are manually extracted
with bounded sizes, exact allowlists and checksum verification before restore.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

from pi_platform.core.runtime.runtime_checkpoint import (
    CheckpointError, RuntimeCheckpointService, atomic_json, restore_checkpoint,
    safe_relative, verify_checkpoint,
)
from pi_platform.core.sync.project_lock import ProjectLock
from pi_platform.core.sync.workspace_sync_contract import WorkspaceSyncFence


def extract_checkpoint(stream, destination: Path, *, max_bytes=20 * 1024**3):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    total, count, seen = 0, 0, set()
    try:
        with tarfile.open(fileobj=stream, mode='r|') as archive:
            for member in archive:
                rel = safe_relative(member.name)
                count += 1
                if not member.isfile() or member.size < 0 or rel in seen or count > 1_000_000:
                    raise CheckpointError('Unsafe checkpoint archive entry')
                seen.add(rel)
                total += member.size
                if total > max_bytes or (rel == 'checkpoint-manifest.json' and member.size > 16 * 1024**2):
                    raise CheckpointError('Checkpoint archive exceeds limits')
                target = destination / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(target, 0o600)
        return verify_checkpoint(destination, max_bytes=max_bytes)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def create(target: Path, stream):
    target = Path(target).resolve()
    cache = target / '.project-intelligence-cache'
    project_id = 'proj-' + hashlib.sha256(str(target).lower().encode()).hexdigest()[:32]
    checkpoint_root = cache / 'checkpoints'
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix='.export-', dir=checkpoint_root)) / 'snapshot'
    try:
        with ProjectLock(project_id, root=cache / 'locks').acquire(timeout_seconds=120):
            with WorkspaceSyncFence(target).lease():
                RuntimeCheckpointService(cache).create(path)
        with tarfile.open(fileobj=stream, mode='w|', format=tarfile.PAX_FORMAT) as archive:
            for file in sorted(path.rglob('*')):
                if file.is_file():
                    archive.add(file, arcname=file.relative_to(path).as_posix(), recursive=False)
        atomic_json(cache / 'checkpoint-status.json', {
            'last_checkpoint': datetime.now(timezone.utc).isoformat(), 'error': None,
            'state': 'streamed-awaiting-host-verification',
        })
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('create')
    make.add_argument('--target', type=Path, default=Path('/repo'))
    restore = sub.add_parser('restore')
    restore.add_argument('--inactive-root', required=True, type=Path)
    restore.add_argument('--profile')
    args = parser.parse_args()
    try:
        if args.command == 'create':
            create(args.target, sys.stdout.buffer)
        else:
            # Caller mounts only a newly created inactive runtime volume.
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'snapshot'
                extract_checkpoint(sys.stdin.buffer, path)
                restore_checkpoint(path, args.inactive_root, profile=args.profile)
        return 0
    except Exception as exc:
        if args.command == 'create':
            try:
                status = args.target / '.project-intelligence-cache' / 'checkpoint-status.json'
                previous = json.loads(status.read_text()) if status.is_file() else {}
                atomic_json(status, {**previous, 'error': str(exc), 'last_attempt': datetime.now(timezone.utc).isoformat()})
            except (OSError, ValueError):
                pass
        print(f'Runtime checkpoint failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
