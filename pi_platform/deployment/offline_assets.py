"""Production asset contract. Runtime verification never downloads anything."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from .asset_pack import AssetPackError, load_manifest, local_file, sha256, verify
from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_FILENAME, GEMMA_PROJECTOR_FILENAME, GEMMA_SHA256, GEMMA_PROJECTOR_SHA256

COMPATIBILITY = 'llama-b11515/docling-production-lock'


def _checked_release(data: dict, manifest: Path) -> dict:
    if data.get('release_status') != 'verified':
        raise AssetPackError('Offline asset release is blocked: complete the actual file/license review and publish an immutable asset image; online fallback is disabled')
    if not re.fullmatch(r'ghcr\.io/shkirmantsev/project-intelligence-assets@sha256:[0-9a-f]{64}', data.get('image') or ''):
        raise AssetPackError('Offline asset image must be pinned by its published OCI digest')
    if not re.fullmatch(r'[0-9a-f]{64}', data.get('manifest_sha256') or ''):
        raise AssetPackError('Offline asset manifest SHA-256 is missing')
    inventory = load_manifest(manifest, data['manifest_sha256'])
    if inventory['runtime_compatibility'] != COMPATIBILITY:
        raise AssetPackError('Reviewed release inventory is incompatible with this runtime')
    return data


def release_identity(path: Path) -> dict:
    return _checked_release(json.loads(path.read_text(encoding='utf-8')), path.with_name('assets-lock.json'))


def bind_published_release(path: Path, image: str, digest: str) -> dict:
    """Bind CI's observed registry output to the reviewed kit inventory.

    The caller owns registry retrieval/verification and offline acceptance. This
    never approves an unreviewed manifest or accepts a tag/local Docker image ID.
    """
    data = _checked_release(dict(schema_version=1, release_status='verified', image=image,
        manifest_sha256=digest, reason='Bound to the verified CI registry output'), path.with_name('assets-lock.json'))
    previous = json.loads(path.read_text(encoding='utf-8'))
    previous.update(data)  # Retain matching application image and kit revision.
    path.write_text(json.dumps(previous, indent=2) + '\n', encoding='utf-8')
    return previous


def verify_candidate(root: Path, digest: str) -> dict:
    """Inspect build contents without granting production activation rights."""
    raw = (root / 'manifest.json').read_bytes()
    if not re.fullmatch(r'[0-9a-f]{64}', digest) or hashlib.sha256(raw).hexdigest() != digest:
        raise AssetPackError('Candidate asset manifest digest mismatch')
    data = json.loads(raw)
    if data.get('schema_version') != 1 or not data.get('files') or data.get('runtime_compatibility') != COMPATIBILITY:
        raise AssetPackError('Candidate asset manifest is incomplete or incompatible')
    seen = set()
    for entry in data['files']:
        name = entry['path']
        if name in seen or not re.fullmatch(r'[0-9a-f]{64}', entry.get('sha256') or ''):
            raise AssetPackError('Duplicate or unpinned candidate asset: ' + name)
        if not entry.get('source') or not entry.get('revision'):
            raise AssetPackError('Missing candidate provenance: ' + name)
        seen.add(name)
    verify(root, data)
    return data


def verify_pack(root: Path, digest: str, *, native_backend=None) -> dict:
    """Verify hashes and the complete production shape before any indexing writes."""
    manifest = load_manifest(root / 'manifest.json', digest)
    if manifest['runtime_compatibility'] != COMPATIBILITY:
        raise AssetPackError('Offline asset runtime/kit mismatch; upgrade the matching application, deployment kit and asset release')
    # Scripts outside the application directory import the installed wheel.
    # The production image retains its lock under its explicit application home.
    application_home = Path(os.environ.get('PI_PLATFORM_HOME') or Path(__file__).resolve().parents[2])
    lock = application_home / 'requirements-production-linux-x86_64.txt'
    if not lock.is_file() or manifest.get('production_lock_sha256') != sha256(lock):
        raise AssetPackError('Offline assets do not match the exact production dependency lock')
    verify(root, manifest)
    for name, expected in ((GEMMA_FILENAME, GEMMA_SHA256), (GEMMA_PROJECTOR_FILENAME, GEMMA_PROJECTOR_SHA256)):
        if sha256(local_file(root, 'embedding/' + name)) != expected:
            raise AssetPackError('Offline GGUF/projector identity mismatch: ' + name)
    for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'model.safetensors'):
        local_file(root, 'transformers/gemma/' + name)
    from pi_platform.adapters.pdf.assets import resolve_local_docling_assets
    resolve_local_docling_assets(root / 'docling', do_ocr=True)
    backends = manifest.get('native_backends')
    if not isinstance(backends, list) or not backends or len(set(backends)) != len(backends) or any(backend not in ('vulkan', 'cuda') for backend in backends):
        raise AssetPackError('Offline asset manifest must declare its native Windows backends')
    if native_backend is not None and native_backend not in backends:
        raise AssetPackError('Native Windows backend is not included in this pack: ' + native_backend + '; use the container runtime or an explicitly reviewed native pack')
    for backend in backends:
        directory = root / 'windows' / backend
        if not directory.is_dir() or not list(directory.rglob('llama-server.exe')):
            raise AssetPackError('Missing offline native Windows runtime: ' + backend)
    return manifest


def configure(cache: Path | None = None, *, load_models=False) -> Path:
    """Resolve only the independent deployment pin, never the mutable marker."""
    digest = os.environ.get('PI_ASSET_MANIFEST_SHA256', '')
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise AssetPackError('Missing offline asset release pin PI_ASSET_MANIFEST_SHA256; upgrade the deployment kit with --upgrade and review preserved deployment.env')
    root = (cache or Path(os.environ.get('PI_ASSET_CACHE', '/models'))) / 'asset-packs' / digest
    if root.is_symlink():
        raise AssetPackError('Refusing symlinked offline asset pack')
    if not root.is_dir():
        raise AssetPackError('Missing offline asset pack; run the mandatory asset-seed service for the reviewed release: ' + str(root))
    verify_pack(root, digest)
    os.environ.update(PI_DOCLING_ASSET_ROOT=str(root / 'docling'),
                      PI_DOCLING_TOKENIZER=str(root / 'transformers/gemma'),
                      PI_TRANSFORMERS_ASSET_ROOT=str(root / 'transformers/gemma'),
                      PI_ALLOW_REMOTE_ASSET_DOWNLOADS='0', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    if load_models:
        from pi_platform.adapters.pdf.real_docling import HuggingFaceTokenizerAdapter
        tokenizer = HuggingFaceTokenizerAdapter(tokenizer_id=str(root / 'transformers/gemma'))
        tokenizer.count_tokens('Offline production preflight')
        from pi_platform.adapters.pdf.real_docling import RealDoclingConverter
        from docling.datamodel.base_models import InputFormat
        converter = RealDoclingConverter(embedding_model_id='google/embeddinggemma-2')
        converter._ensure_converter(do_ocr=True).initialize_pipeline(InputFormat.PDF)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--load-models', action='store_true')
    parser.add_argument('--deployment-env', type=Path)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--candidate', action='store_true', help='Integrity inspection only; does not permit seeding or production activation')
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--bind-image', help='Immutable registry output from the trusted release job; requires --release and --manifest-sha256')
    args = parser.parse_args()
    if args.bind_image and (not args.release or not args.manifest_sha256 or args.candidate or args.root):
        parser.error('--bind-image requires --release and --manifest-sha256')
    if args.candidate and (not args.root or args.release or args.load_models):
        parser.error('--candidate requires --root and cannot activate models or releases')
    if args.release:
        if args.bind_image:
            bind_published_release(args.release, args.bind_image, args.manifest_sha256)
        identity = release_identity(args.release)
        if args.deployment_env:
            content = args.deployment_env.read_text(encoding='utf-8')
            for key, value in (('PI_ASSET_IMAGE', identity['image']), ('PI_ASSET_MANIFEST_SHA256', identity['manifest_sha256'])):
                content = re.sub(r'^' + key + r'=.*$', key + '=' + value, content, flags=re.M)
            args.deployment_env.write_text(content, encoding='utf-8')
        print(json.dumps(identity))
    elif args.root:
        if args.candidate:
            data = verify_candidate(args.root, args.manifest_sha256 or '')
            print('Candidate contents verified; release activation unchanged:', data.get('release_status'))
        else:
            verify_pack(args.root, args.manifest_sha256 or '')
            print('Offline production pack: verified')
    else:
        print(configure(load_models=args.load_models))


if __name__ == '__main__':
    main()
