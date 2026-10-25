"""Retrieval settings for the production UX (open spec change PR 11, plan §55–§57).

Covers the ``one-command-production-ux`` spec delta: the operator's
model selection, execution device, document-processing toggle and
bootstrap state MUST live in the runtime cache
(``.project-intelligence-cache/retrieval-settings.json``) and MUST
never be written into canonical Git.

The module owns three things:

* :class:`RetrievalSettings` — an immutable value object with
  strict schema validation (unknown keys, unknown model aliases,
  unknown devices and unknown bootstrap states are rejected);
* :func:`load_retrieval_settings` — returns the persisted settings,
  falling back to the documented production defaults when the file
  does not exist yet (a *fresh* install), and raising
  :class:`RetrievalSettingsError` when the file exists but is
  malformed (a *corrupt* file must never silently reset an
  operator's selection);
* :func:`save_retrieval_settings` — an atomic write (``.tmp`` +
  :func:`os.replace`) so a crash mid-write can never leave a
  truncated settings file behind.

The default values are the documented production defaults:
EmbeddingGemma 2 (alias ``gemma``), ``device="auto"``,
Docling document processing ON and ``bootstrap_state="not-started"``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Mapping, Union


__all__ = [
    "RetrievalSettings",
    "RetrievalSettingsError",
    "load_retrieval_settings",
    "save_retrieval_settings",
    "retrieval_settings_path",
    "validate_retrieval_settings",
    "normalise_model_alias",
    "normalise_device",
    "CACHE_DIR_NAME",
    "SETTINGS_FILE_NAME",
    "SETTINGS_TMP_SUFFIX",
    "DEFAULT_MODEL_ALIAS",
    "DEFAULT_DEVICE",
    "DEFAULT_DOCUMENT_PROCESSING_ENABLED",
    "DEFAULT_BOOTSTRAP_STATE",
    "PRODUCTION_MODEL_CHOICES",
    "PRODUCTION_ALIAS_TO_MODEL_ID",
    "MODEL_ID_TO_ALIAS",
    "PRODUCTION_ALIASES",
    "DEVICE_CHOICES",
    "BOOTSTRAP_STATES",
]


CACHE_DIR_NAME = ".project-intelligence-cache"
SETTINGS_FILE_NAME = "retrieval-settings.json"
LEGACY_SETTINGS_FILE_NAME = "settings.json"
SETTINGS_TMP_SUFFIX = ".tmp"

DEFAULT_MODEL_ALIAS = "gemma"
DEFAULT_DEVICE = "auto"
DEFAULT_DOCUMENT_PROCESSING_ENABLED = True
DEFAULT_BOOTSTRAP_STATE = "not-started"

# The two production-enabled models from
# ``distribution/licenses/model-licenses.json``.
PRODUCTION_MODEL_CHOICES = (
    "google/embeddinggemma-2",
    "Qwen/Qwen3-Embedding-0.6B",
    "openmycel/Qwen3-Embedding-0.6B-GGUF",
    "ggml-org/embeddinggemma-2-GGUF",
)
PRODUCTION_ALIAS_TO_MODEL_ID = {
    "gemma": "google/embeddinggemma-2",
    "qwen": "Qwen/Qwen3-Embedding-0.6B",
    "qwen-gguf": "openmycel/Qwen3-Embedding-0.6B-GGUF",
    "gemma-gguf": "ggml-org/embeddinggemma-2-GGUF",
}
MODEL_ID_TO_ALIAS = {
    model_id: alias for alias, model_id in PRODUCTION_ALIAS_TO_MODEL_ID.items()
}
MODEL_ID_TO_ALIAS["Qwen/Qwen3-Embedding-0.6B-GGUF"] = "qwen-gguf"
PRODUCTION_ALIASES = frozenset(PRODUCTION_ALIAS_TO_MODEL_ID)

DEVICE_CHOICES = ("auto", "cpu", "cuda", "mps", "vulkan")

BOOTSTRAP_STATES = (
    "not-started",
    "provisioning",
    "hydrating",
    "indexing",
    "ready",
    "error",
)


class RetrievalSettingsError(ValueError):
    """Raised when retrieval settings fail validation or cannot be read/written."""


def normalise_model_alias(value: Any) -> str:
    """Return the canonical alias for ``value`` (alias or model id).

    Raises :class:`RetrievalSettingsError` for anything that is not
    one of the two production models.
    """

    if not isinstance(value, str) or not value.strip():
        raise RetrievalSettingsError(
            "embedding_model_alias must be a non-empty string; expected one of "
            f"{sorted(PRODUCTION_ALIASES)}"
        )
    candidate = value.strip()
    if candidate in PRODUCTION_ALIAS_TO_MODEL_ID:
        return candidate
    lowered = candidate.lower()
    for alias, model_id in PRODUCTION_ALIAS_TO_MODEL_ID.items():
        if lowered == model_id.lower():
            return alias
    raise RetrievalSettingsError(
        f"unknown embedding model {value!r}; expected one of "
        f"{sorted(PRODUCTION_MODEL_CHOICES)} (aliases: {sorted(PRODUCTION_ALIASES)})"
    )


def normalise_device(value: Any) -> str:
    """Return the canonical device string for ``value``."""

    if not isinstance(value, str) or not value.strip():
        raise RetrievalSettingsError(
            f"device must be a non-empty string; expected one of {list(DEVICE_CHOICES)}"
        )
    device = value.strip().lower()
    if device not in DEVICE_CHOICES:
        raise RetrievalSettingsError(
            f"unknown device {value!r}; expected one of {list(DEVICE_CHOICES)}"
        )
    return device


def normalise_bootstrap_state(value: Any) -> str:
    """Return the canonical bootstrap state for ``value``."""

    if not isinstance(value, str) or not value.strip():
        raise RetrievalSettingsError(
            "bootstrap_state must be a non-empty string; expected one of "
            f"{list(BOOTSTRAP_STATES)}"
        )
    state = value.strip()
    if state not in BOOTSTRAP_STATES:
        raise RetrievalSettingsError(
            f"unknown bootstrap_state {value!r}; expected one of {list(BOOTSTRAP_STATES)}"
        )
    return state


@dataclass(frozen=True)
class RetrievalSettings:
    """Immutable operator-facing retrieval configuration.

    Construction normalises the model alias (an alias *or* a full
    Hugging Face model id is accepted and stored as the alias) and
    validates every field, so an invalid instance can never exist.
    """

    embedding_model_alias: str = DEFAULT_MODEL_ALIAS
    device: str = DEFAULT_DEVICE
    document_processing_enabled: bool = DEFAULT_DOCUMENT_PROCESSING_ENABLED
    bootstrap_state: str = DEFAULT_BOOTSTRAP_STATE

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "embedding_model_alias",
            normalise_model_alias(self.embedding_model_alias),
        )
        object.__setattr__(
            self, "device", normalise_device(self.device),
        )
        if not isinstance(self.document_processing_enabled, bool):
            raise RetrievalSettingsError(
                "document_processing_enabled must be a boolean, got "
                f"{type(self.document_processing_enabled).__name__}"
            )
        object.__setattr__(
            self, "bootstrap_state",
            normalise_bootstrap_state(self.bootstrap_state),
        )

    @property
    def model_id(self) -> str:
        """The Hugging Face model id for the active alias."""

        return PRODUCTION_ALIAS_TO_MODEL_ID[self.embedding_model_alias]

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-serialisable representation."""

        return {
            "embedding_model_alias": self.embedding_model_alias,
            "device": self.device,
            "document_processing_enabled": self.document_processing_enabled,
            "bootstrap_state": self.bootstrap_state,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RetrievalSettings":
        """Validate ``payload`` and build the settings value."""

        return validate_retrieval_settings(payload)


def validate_retrieval_settings(
    payload: Union[Mapping[str, Any], RetrievalSettings],
) -> RetrievalSettings:
    """Validate a settings payload (schema check) and return the value.

    Accepts an already-built :class:`RetrievalSettings` (returned
    as-is) or a mapping. Unknown keys, wrong types and unknown
    model/device/bootstrap values raise :class:`RetrievalSettingsError`.
    """

    if isinstance(payload, RetrievalSettings):
        return payload
    if not isinstance(payload, Mapping):
        raise RetrievalSettingsError(
            "retrieval settings payload must be a JSON object, got "
            f"{type(payload).__name__}"
        )
    allowed = {f.name for f in fields(RetrievalSettings)}
    alias_map = {
        "embedding_model": "embedding_model_alias",
        "embedding_device": "device",
        "docling_enabled": "document_processing_enabled",
    }
    ignored_Sync_keys = {"startup_profile", "dense_index", "model_cache_dir"}
    unknown = sorted(
        set(payload) - allowed - set(alias_map) - ignored_Sync_keys
    )
    if unknown:
        raise RetrievalSettingsError(
            f"unknown retrieval settings keys: {unknown}; allowed keys are "
            f"{sorted(allowed)}"
        )
    kwargs: dict[str, Any] = {}
    for src_key, dst_key in alias_map.items():
        if src_key in payload and dst_key not in payload:
            kwargs[dst_key] = payload[src_key]
    for name in allowed:
        if name in payload:
            kwargs[name] = payload[name]
    try:
        return RetrievalSettings(**kwargs)
    except RetrievalSettingsError:
        raise
    except TypeError as exc:  # pragma: no cover - defensive
        raise RetrievalSettingsError(f"invalid retrieval settings: {exc}") from exc


def retrieval_settings_path(target_repo: Path) -> Path:
    """Return the canonical settings path under ``target_repo``."""

    return Path(target_repo) / CACHE_DIR_NAME / SETTINGS_FILE_NAME


def legacy_settings_path(target_repo: Path) -> Path:
    """Return the ``.project-intelligence-cache/settings.json`` path."""

    return Path(target_repo) / CACHE_DIR_NAME / LEGACY_SETTINGS_FILE_NAME


def load_retrieval_settings(target_repo: Path) -> RetrievalSettings:
    """Load the persisted settings for ``target_repo``.

    * file absent → checks ``settings.json`` fallback, else returns
      the documented production defaults (fresh start);
    * file present and valid → the persisted settings;
    * file present but malformed → :class:`RetrievalSettingsError`
      (never a silent reset of the operator's selection).
    """

    path = retrieval_settings_path(target_repo)
    if not path.exists():
        alt = legacy_settings_path(target_repo)
        if alt.exists():
            path = alt
        else:
            return RetrievalSettings()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RetrievalSettingsError(
            f"cannot read retrieval settings at {path}: {exc}"
        ) from exc
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise RetrievalSettingsError(
            f"retrieval settings file is not valid JSON: {path}"
        ) from exc
    try:
        return validate_retrieval_settings(payload)
    except RetrievalSettingsError as exc:
        raise RetrievalSettingsError(
            f"retrieval settings file failed validation: {path}: {exc}"
        ) from exc


def save_retrieval_settings(settings: RetrievalSettings, target_repo: Path) -> Path:
    """Atomically persist ``settings`` under ``target_repo``.

    The payload is written to ``<file>.tmp`` (flushed and fsynced)
    and then moved into place with :func:`os.replace`, so a crash
    mid-write leaves either the previous file or the new file —
    never a truncated one. On failure the temporary file is removed
    and a :class:`RetrievalSettingsError` is raised with the original
    file left untouched.
    """

    validated = validate_retrieval_settings(settings)
    path = retrieval_settings_path(target_repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + SETTINGS_TMP_SUFFIX)
    body = json.dumps(validated.as_dict(), indent=2, sort_keys=True) + "\n"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise RetrievalSettingsError(
            f"failed to write retrieval settings to {path}: {exc}"
        ) from exc

    # Keep ``.project-intelligence-cache/settings.json`` synchronised so
    # ``RuntimeConfigurationResolver`` (PR 1) and ``RetrievalSettings``
    # (PR 11) always observe the exact same operator selection.
    sync_path = legacy_settings_path(target_repo)
    sync_tmp = sync_path.with_name(sync_path.name + SETTINGS_TMP_SUFFIX)
    sync_payload = dict(validated.as_dict())
    sync_payload.update({
        "embedding_model": validated.embedding_model_alias,
        "embedding_device": validated.device,
        "docling_enabled": validated.document_processing_enabled,
    })
    try:
        sync_body = json.dumps(sync_payload, indent=2, sort_keys=True) + "\n"
        with open(sync_tmp, "w", encoding="utf-8") as handle:
            handle.write(sync_body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(sync_tmp, sync_path)
    except OSError:
        try:
            os.unlink(sync_tmp)
        except OSError:
            pass
    return path