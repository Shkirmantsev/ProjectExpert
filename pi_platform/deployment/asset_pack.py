"""Verify and atomically seed immutable, licensed local asset packs.

No downloads are performed. The manifest bytes must be pinned by the caller;
a mutable marker is never treated as proof of the installed file contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile


class AssetPackError(ValueError):
    """An incomplete, unreviewed or damaged pack cannot be activated."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def local_file(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise AssetPackError(f'Unsafe asset path: {name!r}')
    candidate = root / path
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()):
        raise AssetPackError(f'Linked asset outside pack: {name}')
    if not candidate.is_file():
        raise AssetPackError(f'Missing asset: {name}')
    return candidate


def load_manifest(manifest: Path, expected_digest: str) -> dict:
    raw = manifest.read_bytes()
    if not re.fullmatch(r'[0-9a-f]{64}', expected_digest) or hashlib.sha256(raw).hexdigest() != expected_digest:
        raise AssetPackError('Asset manifest digest mismatch')
    data = json.loads(raw)
    if data.get('schema_version') != 1 or data.get('release_status') != 'verified':
        raise AssetPackError('Asset pack release is blocked or schema unsupported')
    if not data.get('runtime_compatibility') or not data.get('files'):
        raise AssetPackError('Asset manifest lacks runtime compatibility or files')
    seen = set()
    for entry in data['files']:
        name = entry['path']
        if name in seen or not re.fullmatch(r'[0-9a-f]{64}', entry.get('sha256', '')):
            raise AssetPackError(f'Duplicate path or unpinned digest: {name}')
        seen.add(name)
        if not all(entry.get(key) for key in ('source', 'revision', 'license', 'license_evidence')):
            raise AssetPackError(f'Missing provenance or redistribution review: {name}')
    for entry in data['files']:
        if entry['license_evidence'] not in seen:
            raise AssetPackError(f'License evidence is not inventoried: {entry["path"]}')
    return data


def verify(root: Path, manifest: dict) -> None:
    expected = {entry['path'] for entry in manifest['files']}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise AssetPackError(f'Linked asset in pack: {path.relative_to(root)}')
        if path.is_file() and path != root / 'manifest.json' and path.relative_to(root).as_posix() not in expected:
            raise AssetPackError(f'Uninventoried asset: {path.relative_to(root)}')
    for entry in manifest['files']:
        if sha256(local_file(root, entry['path'])) != entry['sha256']:
            raise AssetPackError(f'Asset checksum mismatch: {entry["path"]}')



def sync_directory(directory: Path) -> None:
    if os.name == 'nt':
        return  # Windows does not support opening directories with os.open.
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

def seed(source: Path, destination: Path, expected_digest: str) -> Path:
    manifest = load_manifest(source / 'manifest.json', expected_digest)
    verify(source, manifest)
    destination.mkdir(parents=True, exist_ok=True)
    packs = destination / 'asset-packs'
    if packs.is_symlink():
        raise AssetPackError('Refusing symlinked asset pack directory')
    packs.mkdir(exist_ok=True)
    final = packs / expected_digest
    if final.exists():
        if final.is_symlink():
            raise AssetPackError('Refusing symlinked installed asset pack')
        # Never repair in place: a runtime may be using these files.
        load_manifest(final / 'manifest.json', expected_digest)
        verify(final, manifest)
    else:
        staging = Path(tempfile.mkdtemp(prefix='.seed-', dir=packs))
        try:
            for entry in manifest['files']:
                target = staging / entry['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                with local_file(source, entry['path']).open('rb') as reader, target.open('xb') as writer:
                    shutil.copyfileobj(reader, writer)
                    writer.flush()
                    os.fsync(writer.fileno())
            with (staging / 'manifest.json').open('xb') as stream:
                stream.write((source / 'manifest.json').read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            for directory in [*sorted((path for path in staging.rglob('*') if path.is_dir()), reverse=True), staging]:
                sync_directory(directory)
            load_manifest(staging / 'manifest.json', expected_digest)
            verify(staging, manifest)
            try:
                os.rename(staging, final)
            except OSError:
                # Concurrent seeders may have published this exact immutable pack.
                if not final.is_dir() or final.is_symlink():
                    raise
                load_manifest(final / 'manifest.json', expected_digest)
                verify(final, manifest)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    # Consumers use final directly. Pointer is informational and atomic.
    descriptor, pointer = tempfile.mkstemp(prefix='.assets-', dir=destination)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(expected_digest + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pointer, destination / 'active-asset-pack')
        sync_directory(packs)
    finally:
        if os.path.exists(pointer):
            os.unlink(pointer)
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('/opt/projectexpert-assets'))
    parser.add_argument('--destination', type=Path, default=Path('/models'))
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        verify(args.source, load_manifest(args.source / 'manifest.json', args.manifest_sha256))
    else:
        print(seed(args.source, args.destination, args.manifest_sha256))


if __name__ == '__main__':
    main()
