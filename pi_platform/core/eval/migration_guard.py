"""Phase 10 schema-version migration guard helpers.

Plan task 121 mandates that the platform refuse silent hydration
when canonical knowledge advertises a different
``knowledgeSchemaVersion``, ``embeddingModelVersion`` or
``indexSchemaVersion`` than the running runtime supports. This
module ships the typed errors and the helper that produces them
without mutating any canonical file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class SchemaMigrationError(RuntimeError):
    """Base error raised by :func:`check_schema_identity`."""


class IdentityInvalid(SchemaMigrationError):
    """A required identity field is missing or malformed."""


class Incompatible(SchemaMigrationError):
    """No migration path exists for the advertised version."""


class MigrationRequired(SchemaMigrationError):
    """A migration path exists for the advertised version.

    Carries the documented migration path string.
    """

    def __init__(self, message: str, *, migration_path: str) -> None:
        super().__init__(message)
        self.migration_path = migration_path


class WorkingTreeMismatch(SchemaMigrationError):
    """The captured working-tree fingerprint disagrees with HEAD."""


@dataclass(frozen=True)
class RuntimeSchemaVersions:
    """The three runtime-version stamps the platform exposes."""

    knowledge_schema: str
    embedding_model: str
    index_schema: str


def check_schema_identity(
    *,
    manifest: Mapping[str, object],
    runtime_versions: RuntimeSchemaVersions,
    migration_paths: Mapping[str, str] | None = None,
) -> None:
    """Raise a typed error when the manifest disagrees with the runtime.

    The check is additive and never mutates the manifest. The function
    accepts an optional ``migration_paths`` mapping for callers that
    want to advertise a path for a newer-than-runtime schema.
    """
    required = ("knowledgeSchemaVersion", "embeddingModelVersion", "indexSchemaVersion")
    for field_ in required:
        if not manifest.get(field_):
            raise IdentityInvalid(f"Missing identity field: {field_}")

    for manifest_field, runtime_field in (
        ("knowledgeSchemaVersion", runtime_versions.knowledge_schema),
        ("embeddingModelVersion", runtime_versions.embedding_model),
        ("indexSchemaVersion", runtime_versions.index_schema),
    ):
        advertised = str(manifest[manifest_field])
        if advertised == runtime_field:
            continue
        # Newer-than-runtime: try to find a documented path.
        if migration_paths and advertised in migration_paths:
            raise MigrationRequired(
                f"Schema migration required for {manifest_field}={advertised!r}",
                migration_path=migration_paths[advertised],
            )
        raise Incompatible(
            f"No compatible {manifest_field}: advertised={advertised!r} runtime={runtime_field!r}"
        )
