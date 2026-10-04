"""Manifest writer/reader per knowledge family.

The manifest records ``schemaVersion``, ``family``, ``shards``,
``dependencies`` and a self-computed ``contentHash``. The runtime
hydrate MUST use manifests as the primary entry point for loading
canonical knowledge (per
``openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from .content_address import content_address, content_address_bytes
from .serializer import canonical_dump_json, canonical_load_json
from .value_types import Manifest, Shard, dataclass_to_dict

__all__ = [
    "ManifestError",
    "load_manifest",
    "save_manifest",
    "manifest_from_shards",
    "KNOWN_FAMILIES",
]


KNOWN_FAMILIES = ("graph", "chunks", "sources", "objects")


class ManifestError(ValueError):
    """Raised when a manifest file is missing or malformed."""


def manifest_from_shards(
    family: str,
    shards: Sequence[Shard],
    *,
    schema_version: str = "0.1.0",
    dependencies: Sequence[str] = (),
) -> Manifest:
    """Construct a :class:`Manifest` and compute the self hash from the
    canonical shard list.
    """

    if family not in KNOWN_FAMILIES:
        raise ManifestError(
            f"unknown knowledge family: {family!r}; expected one of "
            f"{KNOWN_FAMILIES}"
        )
    base = Manifest(
        schemaVersion=schema_version,
        family=family,
        shards=tuple(shards),
        dependencies=tuple(dependencies),
        contentHash=None,
    )
    body = canonical_dump_json(_manifest_body(base))
    return base.with_content_hash(content_address_bytes(body))


def save_manifest(path: Path, manifest: Manifest) -> Path:
    """Write a manifest to disk and return the written path.

    The manifest is serialised with its self ``contentHash`` already
    filled in; callers SHOULD compute the hash via
    :func:`manifest_from_shards` before saving so the file content is
    stable.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _manifest_body(manifest)
    if manifest.contentHash is not None:
        payload["contentHash"] = manifest.contentHash
    body = canonical_dump_json(payload)
    path.write_bytes(body)
    return path


def load_manifest(path: Path) -> Manifest:
    """Read a manifest from disk.

    The self-hash is recomputed (against the body without the
    contentHash field) and verified against the stored hash; a
    mismatch raises :class:`ManifestError` so hydrate can surface the
    corruption to the operator.
    """

    if not path.is_file():
        raise ManifestError(f"manifest not found: {path}")
    body = path.read_bytes()
    payload = canonical_load_json(body)
    if not isinstance(payload, Mapping):
        raise ManifestError(f"manifest body is not a mapping: {path}")
    shards: list[Shard] = []
    for entry in payload.get("shards", []):
        shards.append(Shard(
            id=entry["id"],
            path=entry["path"],
            contentHash=entry["contentHash"],
            sourceHash=entry.get("sourceHash"),
            count=int(entry.get("count", 0)),
        ))
    manifest = Manifest(
        schemaVersion=payload["schemaVersion"],
        family=payload["family"],
        shards=tuple(shards),
        dependencies=tuple(payload.get("dependencies", ())),
        contentHash=payload.get("contentHash"),
    )
    body_for_hash = canonical_dump_json(payload_for_self_hash(payload))
    expected = content_address_bytes(body_for_hash)
    if manifest.contentHash and manifest.contentHash != expected:
        raise ManifestError(
            f"manifest {path} self-hash mismatch: declared "
            f"{manifest.contentHash!r}, computed {expected!r}"
        )
    return manifest


def _manifest_body(manifest: Manifest) -> dict:
    """Return the canonical-mapping body used for self-hash and write."""

    # Use the canonical ``dataclass_to_dict`` helper so identifier
    # arrays (``dependencies``) are sorted deterministically and
    # ``shards`` is sorted by ``id`` before serialisation. The self-hash
    # requires the body be canonical *without* the ``contentHash``
    # field; we drop it before serialisation.
    body = dataclass_to_dict(manifest)
    shards = sorted(body.get("shards", []), key=lambda s: s.get("id", ""))
    body["shards"] = shards
    body.pop("contentHash", None)
    return body


def payload_for_self_hash(payload: Mapping[str, object]) -> dict:
    """Return the payload body with the ``contentHash`` field removed."""

    out = {k: v for k, v in payload.items() if k != "contentHash"}
    return out