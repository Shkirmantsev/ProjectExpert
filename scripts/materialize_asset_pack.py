#!/usr/bin/env python3
"""Build-time downloads only: assemble the pinned production pack for review.

Without an independently pinned reviewed manifest the output stays BLOCKED.
Never run this on an installation client; clients consume the published OCI pack.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_REVISION
from pi_platform.cli.gguf_setup import GEMMA_FILES
from pi_platform.adapters.pdf.real_docling import DOCLING_LAYOUT_REVISION, DOCLING_TABLE_REVISION, DOCLING_OCR_REVISION, DOCLING_OCR_FILES
from pi_platform.deployment.asset_pack import AssetPackError, sha256, load_manifest, verify
from pi_platform.deployment.offline_assets import COMPATIBILITY, verify_pack


def fetch(url, destination, expected=None, *, cache_roots=()):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and expected and sha256(destination) == expected:
        return
    cached = None
    if expected:
        for root in cache_roots:
            for candidate in (root / destination.name, root / expected):
                if candidate.is_file() and not candidate.is_symlink() and sha256(candidate) == expected:
                    cached = candidate
                    break
            if cached is not None:
                break
    print(('Reusing verified cache: ' if cached else 'Downloading: ') + destination.name, flush=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.download-', dir=destination.parent)
    import os
    try:
        with os.fdopen(descriptor, 'wb') as target, (cached.open('rb') if cached else urllib.request.urlopen(url, timeout=120)) as source:
            shutil.copyfileobj(source, target)
        if expected and sha256(Path(temporary)) != expected:
            raise AssetPackError('Build-time download checksum mismatch: ' + destination.name)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def assemble(destination: Path, *, cache_roots=(), native_backends=('vulkan',)):
    if destination.exists() and any(destination.iterdir()):
        raise AssetPackError('Use an empty controlled output directory; existing packs are never modified')
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    def record(path, url, revision):
        entries.append(dict(path=path.relative_to(destination).as_posix(), sha256=sha256(path),
                            source=url, revision=revision, license=None, license_evidence=None))
    for name, url, digest in GEMMA_FILES:
        path = destination / 'embedding' / name
        fetch(url, path, digest, cache_roots=cache_roots)
        record(path, url, GEMMA_REVISION)
    specs = (
        ('google/embeddinggemma-2', '914f7f89142e33e77833254d9c9b90c3cef7303b', 'transformers/gemma', None),
        ('docling-project/docling-layout-heron', DOCLING_LAYOUT_REVISION, 'docling/artifacts/docling-project--docling-layout-heron', None),
        ('docling-project/docling-models', DOCLING_TABLE_REVISION, 'docling/artifacts/docling-project--docling-models',
         ('config.json', 'README.md', 'model_artifacts/tableformer/accurate/')),
        ('SWHL/RapidOCR', DOCLING_OCR_REVISION, 'docling/ocr', (*DOCLING_OCR_FILES, 'README.md', 'LICENSE')),
    )
    for repo, revision, prefix, patterns in specs:
        with urllib.request.urlopen('https://huggingface.co/api/models/' + repo + '/revision/' + revision + '?blobs=true', timeout=120) as source:
            info = json.load(source)
        if info['sha'] != revision:
            raise AssetPackError('Upstream revision identity mismatch: ' + repo)
        for entry in info['siblings']:
            name = entry['rfilename']
            parts = PurePosixPath(name)
            if parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name:
                raise AssetPackError('Unsafe upstream path')
            if name.startswith('.') or (patterns and not any(name == item or (item.endswith('/') and name.startswith(item)) for item in patterns)):
                continue
            url = 'https://huggingface.co/' + repo + '/resolve/' + revision + '/' + urllib.parse.quote(name)
            path = destination / prefix / name
            expected = (entry.get('lfs') or {}).get('sha256')
            fetch(url, path, expected, cache_roots=cache_roots)
            record(path, url, revision)
    lock = json.loads((ROOT / 'distribution/deployment/accelerator-lock.json').read_text())
    for backend in native_backends:
        for asset in lock['windows'][backend]:
            url = 'https://github.com/ggml-org/llama.cpp/releases/download/' + lock['runtime_version'] + '/' + asset['name']
            archive = destination / 'windows/archives' / asset['name']
            fetch(url, archive, asset['sha256'], cache_roots=cache_roots)
            record(archive, url, lock['runtime_version'])
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    parts = PurePosixPath(member.filename)
                    if parts.is_absolute() or '..' in parts.parts or '\\' in member.filename or ':' in member.filename or (member.external_attr >> 16) & 0o170000 == 0o120000:
                        raise AssetPackError('Unsafe native archive member')
                    if member.is_dir():
                        continue
                    path = destination / 'windows' / backend / parts
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        with bundle.open(member) as source:
                            digest = hashlib.sha256()
                            for block in iter(lambda: source.read(1024 * 1024), b''):
                                digest.update(block)
                        if sha256(path) != digest.hexdigest():
                            raise AssetPackError('Native archives contain conflicting files: ' + member.filename)
                        continue
                    with bundle.open(member) as source, path.open('xb') as target:
                        shutil.copyfileobj(source, target)
                    record(path, url + '#' + member.filename, lock['runtime_version'])
    manifest = dict(schema_version=1, release_status='blocked', runtime_compatibility=COMPATIBILITY,
                    production_lock_sha256=sha256(ROOT / 'requirements-production-linux-x86_64.txt'),
                    native_backends=list(native_backends),
                    release_blockers=['Per-file redistribution licenses and evidence require independent review',
                                      'Real egress-denied model loading/conversion and OCI publication required'],
                    files=sorted(entries, key=lambda entry: entry['path']))
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'tmp/local/asset-pack')
    parser.add_argument('--native-backends', nargs='+', choices=('vulkan', 'cuda'), default=['vulkan'], help='Windows fallback binaries; container CUDA uses the pinned upstream CUDA image and host driver')
    parser.add_argument('--download-cache', type=Path, action='append', default=[], help='Explicit read-only cache; reuse requires an upstream SHA-256 match')
    parser.add_argument('--reviewed-manifest', type=Path)
    parser.add_argument('--license-evidence', type=Path, help='Explicit local review evidence directory to copy into licenses/')
    parser.add_argument('--reviewed-manifest-sha256')
    args = parser.parse_args()
    if bool(args.reviewed_manifest) != bool(args.reviewed_manifest_sha256):
        parser.error('Review manifest and independent digest must be supplied together')
    reviewed = (load_manifest(args.reviewed_manifest, args.reviewed_manifest_sha256)
                if args.reviewed_manifest else None)
    # The pinned full Transformers model, GGUF/projector and native archives
    # coexist during assembly. Do not risk filling an operator's working disk.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.output.parent).free < 8 * 1024 ** 3:
        raise AssetPackError('Controlled asset assembly requires at least 8 GiB free disk; no downloads started')
    candidate = assemble(args.output, cache_roots=args.download_cache, native_backends=args.native_backends)
    if args.reviewed_manifest:
        if args.license_evidence:
            evidence = args.license_evidence.resolve()
            if not evidence.is_dir() or any(path.is_symlink() for path in evidence.rglob('*')):
                raise AssetPackError('License evidence must be a regular local directory without links')
            shutil.copytree(evidence, args.output / 'licenses')
        original = {row['path']: row for row in candidate['files']}
        for row in reviewed['files']:
            if row['path'] in original and any(row[key] != original[row['path']][key] for key in ('sha256', 'source', 'revision')):
                raise AssetPackError('Review does not match materialized provenance: ' + row['path'])
        if not set(original).issubset({row['path'] for row in reviewed['files']}):
            raise AssetPackError('Reviewed manifest omits materialized files')
        # Additional review evidence must already have been explicitly supplied.
        verify(args.output, reviewed)
        shutil.copyfile(args.reviewed_manifest, args.output / 'manifest.json')
        verify_pack(args.output, args.reviewed_manifest_sha256)
        print('Reviewed offline pack:', args.reviewed_manifest_sha256)
    else:
        print('Materialized candidate BLOCKED pending review:', sha256(args.output / 'manifest.json'))


if __name__ == '__main__':
    main()
