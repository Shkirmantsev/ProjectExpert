"""Download and verify the optional GGUF model before starting its runtime."""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import secrets
import tempfile
import urllib.request

from pi_platform.adapters.retrieval.gguf_artifacts import (FILENAME, MODEL_URL, SHA256,
    GEMMA_FILENAME, GEMMA_SHA256, GEMMA_PROJECTOR_FILENAME, GEMMA_PROJECTOR_SHA256, GEMMA_URL_ROOT)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _download(cache: Path, filename: str, url: str, sha256: str) -> Path:
    model = cache / filename
    if not model.is_file() or file_hash(model) != sha256:
        descriptor, temporary = tempfile.mkstemp(prefix='gguf-', suffix='.partial', dir=cache)
        try:
            with os.fdopen(descriptor, 'wb') as target, urllib.request.urlopen(url, timeout=120) as source:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            if file_hash(Path(temporary)) != sha256:
                raise ValueError('GGUF download checksum mismatch; model was not installed')
            os.replace(temporary, model)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return model


def prepare(cache: Path, model_alias: str = 'qwen-gguf') -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    if model_alias == 'qwen-gguf':
        model = _download(cache, FILENAME, MODEL_URL, SHA256)
    elif model_alias == 'gemma-gguf':
        model = _download(cache, GEMMA_FILENAME, GEMMA_URL_ROOT + GEMMA_FILENAME, GEMMA_SHA256)
        _download(cache, GEMMA_PROJECTOR_FILENAME, GEMMA_URL_ROOT + GEMMA_PROJECTOR_FILENAME, GEMMA_PROJECTOR_SHA256)
    else:
        raise ValueError('Unknown GGUF model alias')
    key = cache / 'llama-api-key'
    try:
        descriptor = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if len(key.read_text().strip()) < 32:
            raise ValueError('Existing llama-api-key is invalid; restore it or remove it and restart setup')
    else:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(secrets.token_hex(32))
    return model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=Path('/models'))
    parser.add_argument('--model', choices=('qwen-gguf', 'gemma-gguf'), default='qwen-gguf')
    args = parser.parse_args()
    print(f'Verified GGUF model: {prepare(args.cache, args.model)}')


if __name__ == '__main__':
    main()
