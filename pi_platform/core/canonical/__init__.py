"""Canonical subpackage entry point.

Re-exports the public Phase 1 symbols so callers can import the value
types, the serializer, the content addressing utility, the manifest
helpers and the OKF profile via a single namespace:

    from platform.core.canonical import (
        Chunk, Manifest, KnowledgeState, Metadata,
        content_address, manifest_from_shards,
        OkfV02Profile, validate_wiki_bundle,
    )
"""

from .content_address import (
    chunk_content_address,
    content_address,
    content_address_bytes,
    content_address_for_canonical,
    object_path,
)
from .manifest import (
    KNOWN_FAMILIES,
    ManifestError,
    load_manifest,
    manifest_from_shards,
    save_manifest,
)
from .okf import (
    DEFAULT_OKF_VERSION,
    OKF_PLATFORM_PREFIX,
    OKF_RESERVED_FILES,
    OkfAdapter,
    OkfV02Profile,
    OkfValidationError,
    parse_frontmatter,
    validate_wiki_bundle,
)
from .serializer import (
    canonical_dump_json,
    canonical_dump_yaml,
    canonical_load_json,
    canonical_load_yaml,
    normalize_identifier_list,
    normalize_optional_str,
    normalize_str,
)
from .value_types import (
    Chunk,
    ContextualChunk,
    Document,
    Entity,
    Evidence,
    KnowledgeState,
    Manifest,
    Metadata,
    ProjectVersion,
    Relation,
    RuntimeChange,
    Section,
    Shard,
    Source,
    TaskContext,
    dataclass_from_dict,
    dataclass_to_dict,
    from_canonical_json,
    to_canonical_json,
)

__all__ = [
    "KNOWN_FAMILIES",
    "DEFAULT_OKF_VERSION",
    "OKF_PLATFORM_PREFIX",
    "OKF_RESERVED_FILES",
    "Chunk",
    "ContextualChunk",
    "Document",
    "Entity",
    "Evidence",
    "KnowledgeState",
    "Manifest",
    "ManifestError",
    "Metadata",
    "OkfAdapter",
    "OkfV02Profile",
    "OkfValidationError",
    "ProjectVersion",
    "Relation",
    "RuntimeChange",
    "Section",
    "Shard",
    "Source",
    "TaskContext",
    "canonical_dump_json",
    "canonical_dump_yaml",
    "canonical_load_json",
    "canonical_load_yaml",
    "chunk_content_address",
    "content_address",
    "content_address_bytes",
    "content_address_for_canonical",
    "dataclass_from_dict",
    "dataclass_to_dict",
    "from_canonical_json",
    "load_manifest",
    "manifest_from_shards",
    "normalize_identifier_list",
    "normalize_optional_str",
    "normalize_str",
    "object_path",
    "parse_frontmatter",
    "save_manifest",
    "to_canonical_json",
    "validate_wiki_bundle",
]