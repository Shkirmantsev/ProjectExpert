"""Production asset contract. Runtime verification never downloads anything."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from .asset_pack import AssetPackError, load_manifest, local_file, sha256, verify
from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_FILENAME, GEMMA_PROJECTOR_FILENAME, GEMMA_SHA256, GEMMA_PROJECTOR_SHA256

COMPATIBILITY = 'llama-b11515/docling-production-lock'


def release_identity(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('release_status') != 'verified':
        raise AssetPackError('Offline asset release is blocked: complete the actual file/license review and publish an immutable asset image; online fallback is disabled')
    if not re.fullmatch(r'ghcr\.io/shkirmantsev/project-intelligence-assets@sha256:[0-9a-f]{64}', data.get('image') or ''):
        raise AssetPackError('Offline asset image must be pinned by its published OCI digest')
    if not re.fullmatch(r'[0-9a-f]{64}', data.get('manifest_sha256') or ''):
        raise AssetPackError('Offline asset manifest SHA-256 is missing')
    inventory = load_manifest(path.with_name('assets-lock.json'), data['manifest_sha256'])
    if inventory['runtime_compatibility'] != COMPATIBILITY:
        raise AssetPackError('Reviewed release inventory is incompatible with this runtime')
    return data


def verify_pack(root: Path, digest: str, *, native_backend=None) -> dict:
    """Verify hashes and the complete production shape before any indexing writes."""
    manifest = load_manifest(root / 'manifest.json', digest)
    if manifest['runtime_compatibility'] != COMPATIBILITY:
        raise AssetPackError('Offline asset runtime/kit mismatch; upgrade the matching application, deployment kit and asset release')
    lock = Path(__file__).resolve().parents[2] / 'requirements-production-linux-x86_64.txt'
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
    for backend in ((native_backend,) if native_backend else ('vulkan', 'cuda')):
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
    parser.add_argument('--manifest-sha256')
    args = parser.parse_args()
    if args.release:
        identity = release_identity(args.release)
        if args.deployment_env:
            content = args.deployment_env.read_text(encoding='utf-8')
            for key, value in (('PI_ASSET_IMAGE', identity['image']), ('PI_ASSET_MANIFEST_SHA256', identity['manifest_sha256'])):
                content = re.sub(r'^' + key + r'=.*$', key + '=' + value, content, flags=re.M)
            args.deployment_env.write_text(content, encoding='utf-8')
        print(json.dumps(identity))
    elif args.root:
        verify_pack(args.root, args.manifest_sha256 or '')
        print('Offline production pack: verified')
    else:
        print(configure(load_models=args.load_models))


if __name__ == '__main__':
    main()
