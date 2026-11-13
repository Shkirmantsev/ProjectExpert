"""Verify installed EmbeddingGemma assets and provision the private runtime key.

Normal setup never downloads. Only explicit developer callers may opt into
pinned, checksum-verified downloads; production always requires its OCI pack.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import urllib.request

from pi_platform.adapters.retrieval.gguf_artifacts import (
    GEMMA_FILENAME,
    GEMMA_PROJECTOR_FILENAME,
    GEMMA_PROJECTOR_SHA256,
    GEMMA_SHA256,
    GEMMA_URL_ROOT,
)

__all__ = ["file_hash", "prepare", "GEMMA_FILES", "main"]


#: The pinned package: the quantised backbone and the matching projector.
GEMMA_FILES = (
    (GEMMA_FILENAME, GEMMA_URL_ROOT + GEMMA_FILENAME, GEMMA_SHA256),
    (
        GEMMA_PROJECTOR_FILENAME,
        GEMMA_URL_ROOT + GEMMA_PROJECTOR_FILENAME,
        GEMMA_PROJECTOR_SHA256,
    ),
)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(cache: Path, filename: str, url: str, sha256: str) -> Path:
    model = cache / filename
    if model.is_file() and file_hash(model) == sha256:
        return model
    descriptor, temporary = tempfile.mkstemp(prefix="gguf-", suffix=".partial", dir=cache)
    try:
        with os.fdopen(descriptor, "wb") as target, urllib.request.urlopen(url, timeout=120) as source:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        if file_hash(Path(temporary)) != sha256:
            raise ValueError("GGUF download checksum mismatch; model was not installed")
        os.replace(temporary, model)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return model


def prepare(cache: Path, model_alias: str = "gemma", *, allow_download: bool = False) -> Path:
    """Verify local pinned artefacts and return the backbone path.

    ``model_alias`` accepts ``gemma`` (the pinned GGUF binding, the only
    supported production alias). The retired alias is rejected with an
    actionable message.
    """

    from pi_platform.adapters.retrieval.embedding_model_factory import (
        GEMMA_ALIAS,
        RetiredEmbeddingAliasError,
    )

    if model_alias != GEMMA_ALIAS:
        raise RetiredEmbeddingAliasError(
            f"unknown GGUF model alias {model_alias!r}; expected {GEMMA_ALIAS!r}"
        )
    pack = None
    if os.environ.get('PI_STARTUP_PROFILE') == 'production' or os.environ.get('PI_ASSET_MANIFEST_SHA256'):
        from pi_platform.deployment.offline_assets import configure
        pack = configure(cache)
        if allow_download:
            raise ValueError('Production setup forbids remote model downloads')
    # Validate all inputs before creating keys or touching existing cache files.
    for filename, url, digest in GEMMA_FILES:
        candidate = pack / 'embedding' / filename if pack else cache / filename
        if not candidate.is_file() or file_hash(candidate) != digest:
            if not allow_download or pack:
                raise ValueError('Missing or corrupt offline embedding asset: ' + filename + '; install the reviewed OCI asset pack. Developer downloads require explicit opt-in.')
    cache.mkdir(parents=True, exist_ok=True)
    model = None
    for filename, url, sha256 in GEMMA_FILES:
        path = cache / filename
        if pack is not None and (not path.is_file() or file_hash(path) != sha256):
            descriptor, temporary = tempfile.mkstemp(prefix='gguf-', suffix='.partial', dir=cache)
            try:
                with os.fdopen(descriptor, 'wb') as target, (pack / 'embedding' / filename).open('rb') as source:
                    shutil.copyfileobj(source, target)
                    target.flush()
                    os.fsync(target.fileno())
                if file_hash(Path(temporary)) != sha256:
                    raise ValueError('Offline embedding asset changed during provisioning')
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        elif allow_download:
            path = _download(cache, filename, url, sha256)
        if model is None:
            model = path
    key = cache / "llama-api-key"
    try:
        descriptor = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if len(key.read_text().strip()) < 32:
            raise ValueError(
                "Existing llama-api-key is invalid; restore it or remove it and restart setup"
            )
    else:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(secrets.token_hex(32))
    return model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/models"))
    parser.add_argument("--model", default="gemma")
    args = parser.parse_args()
    from pi_platform.cli.runtime_python import bundle_python
    if os.environ.get('PI_ASSET_MANIFEST_SHA256'):
        from pi_platform.deployment.offline_assets import configure
        configure(args.cache, load_models=True)
    bundle_python(args.cache)
    print(f"Verified GGUF model: {prepare(args.cache, args.model)}")


if __name__ == "__main__":
    main()
