"""Offline Windows CUDA inspection, scoped review and immutable installation.

Never downloads assets or executes binaries. The default model/Vulkan pack is
not changed. Candidate manifests deliberately remain blocked for human review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

from .asset_pack import AssetPackError, load_manifest, local_file, sha256, sync_directory, verify

MAX_EXPANDED_BYTES = 4 * 1024**3
MAX_FILES = 4096
COMPATIBILITY = 'llama-b11515/docling-production-lock'
REVIEW = 'licenses/operator-review.json'


def runtime_lock():
    # Installed application images retain the deployment bundle at /bundle.
    for root in (Path(os.environ.get('PI_PLATFORM_HOME') or Path(__file__).resolve().parents[2]) / 'distribution/deployment', Path('/bundle')):
        path = root / 'accelerator-lock.json'
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8'))
    raise AssetPackError('Missing application accelerator lock')


def windows_path(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or name.startswith('/') or any(ord(char) < 32 for char in name)):
        raise AssetPackError('Unsafe Windows asset path')
    parts = name.split('/')
    for part in parts:
        if (not part or part in ('.', '..') or part.endswith((' ', '.'))
                or re.search(r'[<>"|?*]', part)
                or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I)):
            raise AssetPackError('Unsafe Windows asset path: ' + name)
    return '/'.join(parts).casefold()


def _register_path(name, paths, *, directory=False):
    parts = name.split('/')
    for index in range(1, len(parts) + 1):
        prefix = '/'.join(parts[:index])
        key = windows_path(prefix)
        is_directory = index < len(parts) or directory
        if key in paths and paths[key] != (prefix, is_directory):
            raise AssetPackError('Windows case/path collision in native closure')
        paths[key] = (prefix, is_directory)


def archive_inventory(archive):
    """Hash bounded ZIP members without loading the binary closure into RAM."""
    result, seen, total, paths = {}, set(), 0, {}
    with zipfile.ZipFile(archive) as stream:
        if len(stream.infolist()) > MAX_FILES:
            raise AssetPackError('Native archive file limit exceeded')
        for item in stream.infolist():
            # ZipInfo.filename normalizes Windows separators and truncates at
            # NUL. Check the original stored name before those transformations.
            name = item.orig_filename
            if name.endswith('/'):
                name = name[:-1]
            key = windows_path(name)
            _register_path(name, paths, directory=item.is_dir())
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise AssetPackError('Linked or special native archive member')
            if key in seen:
                raise AssetPackError('Windows case/path collision in archive')
            seen.add(key)
            if item.is_dir(): continue
            total += item.file_size
            if item.flag_bits & 1 or total > MAX_EXPANDED_BYTES:
                raise AssetPackError('Encrypted or oversized native archive')
            digest, count = hashlib.sha256(), 0
            with stream.open(item) as reader:
                for block in iter(lambda: reader.read(1024 * 1024), b''):
                    count += len(block)
                    if count > item.file_size or count > MAX_EXPANDED_BYTES:
                        raise AssetPackError('Expanded archive limit exceeded')
                    digest.update(block)
            if count != item.file_size:
                raise AssetPackError('Truncated native archive')
            result[name] = digest.hexdigest()
    return result


def _closure(root, lock):
    result, normalized, paths, provenance = {}, {}, {}, {}
    expanded = 0
    for entry in lock['windows']['cuda']:
        archive = local_file(root, 'windows/archives/' + entry['name'])
        if sha256(archive) != entry['sha256']:
            raise AssetPackError('Native CUDA archive pin mismatch: ' + entry['name'])
        with zipfile.ZipFile(archive) as stream:
            expanded += sum(row.file_size for row in stream.infolist())
        if expanded > MAX_EXPANDED_BYTES: raise AssetPackError('Native closure expansion limit exceeded')
        archive_source = 'https://github.com/ggml-org/llama.cpp/releases/download/' + lock['runtime_version'] + '/' + entry['name']
        provenance['windows/archives/' + entry['name']] = archive_source
        for name, digest in archive_inventory(archive).items():
            _register_path(name, paths)
            key = windows_path(name)
            if key in normalized:
                previous = normalized[key]
                if previous != name or result[previous] != digest:
                    raise AssetPackError('Conflicting native archive closure')
            normalized[key] = name
            result[name] = digest
            provenance.setdefault('windows/cuda/' + name, archive_source + '#' + name)
            if len(result) > MAX_FILES: raise AssetPackError('Native closure file limit exceeded')
    if not any(PurePosixPath(name).name == 'llama-server.exe' for name in result):
        raise AssetPackError('Native archive closure has no llama-server.exe')
    if not any(PurePosixPath(name).name == 'ggml-cuda.dll' for name in result):
        raise AssetPackError('Native archive closure has no ggml-cuda.dll')
    servers = [PurePosixPath(name).parent for name in result if name.endswith('/llama-server.exe') or name == 'llama-server.exe']
    if len(servers) != 1 or any(PurePosixPath(name).parent != servers[0] for name in result if name.lower().endswith(('.exe', '.dll'))):
        raise AssetPackError('Native DLL closure must share the isolated server directory')
    return result, provenance


def _safe_tree(root):
    if root.is_symlink(): raise AssetPackError('Linked native pack root')
    seen = set()
    for path in root.rglob('*'):
        key = windows_path(path.relative_to(root).as_posix())
        if key in seen: raise AssetPackError('Duplicate Windows asset path')
        seen.add(key)
        info = path.lstat()
        if path.is_symlink() or (not path.is_dir() and (not path.is_file() or info.st_nlink != 1)):
            raise AssetPackError('Linked or special native asset')


def verify_native_runtime_pack(root, digest, primary_digest, *, mode='operator-local'):
    root = Path(root)
    if mode not in ('operator-local', 'reviewed-oci') or not re.fullmatch('[0-9a-f]{64}', primary_digest):
        raise AssetPackError('Invalid native runtime verification mode or primary identity')
    _safe_tree(root)
    manifest = load_manifest(root / 'manifest.json', digest)
    lock = runtime_lock()
    if (manifest.get('kind') != 'windows-native-cuda' or manifest.get('architecture') != 'windows-amd64'
            or manifest.get('native_backends') != ['cuda']
            or manifest.get('llama_cpp_revision') != lock['runtime_version']
            or manifest.get('runtime_compatibility') != COMPATIBILITY
            or manifest.get('primary_asset_manifest_sha256') != primary_digest):
        raise AssetPackError('Incompatible native CUDA pack or primary manifest binding')
    seen = set()
    for row in manifest['files']:
        key = windows_path(row['path'])
        if key in seen: raise AssetPackError('Duplicate Windows manifest path')
        seen.add(key)
        if row['revision'] != lock['runtime_version']:
            raise AssetPackError('Native file revision mismatch')
    verify(root, manifest)
    review = json.loads(local_file(root, REVIEW).read_text(encoding='utf-8'))
    required_scope = 'redistribution' if mode == 'reviewed-oci' else 'operator-local'
    if (review.get('approved') is not True or review.get('scope') != required_scope
            or not review.get('review_id') or any(row['license_evidence'] != REVIEW for row in manifest['files'])):
        raise AssetPackError('Native CUDA pack lacks scoped operator/license approval')
    closure, provenance = _closure(root, lock)
    expected = {'windows/cuda/' + name: digest for name, digest in closure.items()}
    expected.update({'windows/archives/' + entry['name']: entry['sha256'] for entry in lock['windows']['cuda']})
    expected[REVIEW] = sha256(root / REVIEW)
    provenance[REVIEW] = 'operator-offline-review'
    if any(row['source'] != provenance.get(row['path']) for row in manifest['files']):
        raise AssetPackError('Native CUDA provenance differs from pinned archive closure')
    actual = {row['path']: row['sha256'] for row in manifest['files']}
    if actual != expected:
        raise AssetPackError('Native CUDA inventory differs from pinned archive closure')
    return manifest


def inspect_archives(archives, destination, primary_digest):
    """Produce a blocked, complete inventory for independent offline review."""
    archives, destination = Path(archives), Path(destination)
    if destination.exists() or destination.is_symlink() or not re.fullmatch('[0-9a-f]{64}', primary_digest):
        raise AssetPackError('Inspection needs a new directory and exact primary manifest pin')
    lock = runtime_lock()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.native-inspect-', dir=destination.parent))
    try:
        target = staging / 'windows/archives'; target.mkdir(parents=True)
        for entry in lock['windows']['cuda']:
            source = local_file(archives, entry['name'])
            if sha256(source) != entry['sha256']: raise AssetPackError('Native CUDA archive pin mismatch')
            shutil.copyfile(source, target / entry['name'])
        closure, provenance = _closure(staging, lock)
        runtime = staging / 'windows/cuda'; runtime.mkdir()
        for entry in lock['windows']['cuda']:
            with zipfile.ZipFile(target / entry['name']) as stream:
                for item in stream.infolist():
                    if item.is_dir(): continue
                    windows_path(item.filename)
                    path = (runtime / item.filename).resolve()
                    if not path.is_relative_to(runtime.resolve()):
                        raise AssetPackError('Native archive member escapes staging root')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists(): continue  # Equal-byte collisions already verified.
                    with stream.open(item) as reader, path.open('xb') as writer:
                        shutil.copyfileobj(reader, writer, 1024 * 1024)
        (staging / 'licenses').mkdir()
        (staging / REVIEW).write_text(json.dumps({'approved': False, 'scope': 'operator-local', 'review_id': ''}, indent=2)+'\n')
        files = []
        for path in sorted(p for p in staging.rglob('*') if p.is_file()):
            name = path.relative_to(staging).as_posix()
            files.append(dict(path=name, sha256=sha256(path),
                source=provenance[name] if name.startswith('windows/') else 'operator-offline-review',
                revision=lock['runtime_version'], license=None, license_evidence=REVIEW))
        manifest = dict(schema_version=1, release_status='blocked', kind='windows-native-cuda', architecture='windows-amd64',
            native_backends=['cuda'], llama_cpp_revision=lock['runtime_version'], runtime_compatibility=COMPATIBILITY,
            primary_asset_manifest_sha256=primary_digest, files=files)
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        os.rename(staging, destination)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    return destination


def install(source, destination, digest, primary_digest, *, mode='operator-local'):
    source, destination = Path(source), Path(destination)
    manifest = verify_native_runtime_pack(source, digest, primary_digest, mode=mode)
    if destination.is_symlink(): raise AssetPackError('Linked native install directory')
    destination.mkdir(parents=True, exist_ok=True)
    final = destination / digest
    if final.exists() or final.is_symlink():
        verify_native_runtime_pack(final, digest, primary_digest, mode=mode)
        return final
    staging = Path(tempfile.mkdtemp(prefix='.native-install-', dir=destination))
    try:
        for name in [row['path'] for row in manifest['files']] + ['manifest.json']:
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with local_file(source, name).open('rb') as reader, target.open('xb') as writer:
                shutil.copyfileobj(reader, writer, 1024 * 1024)
                writer.flush(); os.fsync(writer.fileno())
        verify_native_runtime_pack(staging, digest, primary_digest, mode=mode)
        sync_directory(staging)
        try: os.rename(staging, final)
        except OSError:
            verify_native_runtime_pack(final, digest, primary_digest, mode=mode)
        sync_directory(destination)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--primary-manifest-sha256', required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--inspect-archives', action='store_true')
    parser.add_argument('--mode', choices=('operator-local', 'reviewed-oci'), default='operator-local')
    args = parser.parse_args()
    try:
        if args.inspect_archives:
            if not args.destination: parser.error('inspection requires --destination')
            result = inspect_archives(args.source, args.destination, args.primary_manifest_sha256)
            print('BLOCKED candidate for independent per-file license review: ' + str(result))
        else:
            if not args.manifest_sha256: parser.error('verification requires --manifest-sha256')
            if args.destination:
                print(install(args.source, args.destination, args.manifest_sha256, args.primary_manifest_sha256, mode=args.mode))
            else:
                verify_native_runtime_pack(args.source, args.manifest_sha256, args.primary_manifest_sha256, mode=args.mode)
                print('Native CUDA pack: verified')
    except (AssetPackError, OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(1, 'native_cuda_pack_invalid: ' + str(exc) + '\n')


if __name__ == '__main__': main()
