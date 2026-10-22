"""Runtime configuration resolver (open spec change PR 1, plan §19, §20).

The platform has many entry points (CLI flags, environment
variables, local runtime settings under
``.project-intelligence-cache/settings.json``, project-context
defaults, web control plane PUT). This module collapses all of
them into a single resolved :class:`RuntimeConfiguration` value
through the documented precedence chain (plan §19):

    command-line argument
        ↓
    environment variable
        ↓
    local runtime settings (.project-intelligence-cache/settings.json)
        ↓
    project-context default
        ↓
    built-in default

The resolver is the only entry point that performs resolution;
no other module is allowed to read environment variables or
runtime settings files directly.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


__all__ = [
    "RuntimeConfiguration",
    "RuntimeConfigurationResolver",
    "ConfigurationError",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_EMBEDDING_DEVICE",
    "DEFAULT_DENSE_INDEX",
    "DEFAULT_DOCLING_ENABLED",
    "DEFAULT_MODEL_CACHE_DIR",
    "DEFAULT_STARTUP_PROFILE",
    "ENV_OVERRIDE_PREFIX",
    "LOCAL_SETTINGS_RELATIVE_PATH",
]


DEFAULT_EMBEDDING_MODEL = "gemma"
DEFAULT_EMBEDDING_DEVICE = "auto"
DEFAULT_DENSE_INDEX = "usearch"
DEFAULT_DOCLING_ENABLED = True
DEFAULT_MODEL_CACHE_DIR = str(Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")))
DEFAULT_STARTUP_PROFILE = "production"
ENV_OVERRIDE_PREFIX = "PI_"
LOCAL_SETTINGS_RELATIVE_PATH = ".project-intelligence-cache/settings.json"

ENV_EMBEDDING_MODEL = "PI_EMBEDDING_MODEL"
ENV_EMBEDDING_DEVICE = "PI_EMBEDDING_DEVICE"
ENV_DENSE_INDEX = "PI_DENSE_INDEX"
ENV_DOCLING_ENABLED = "PI_DOCLING_ENABLED"
ENV_MODEL_CACHE = "PI_MODEL_CACHE"
ENV_STARTUP_PROFILE = "PI_STARTUP_PROFILE"


class ConfigurationError(ValueError):
    """Raised when a configuration value fails validation."""


@dataclass(frozen=True)
class RuntimeConfiguration:
    """The resolved runtime configuration used by the platform.

    The fields are the documented selection variables (plan §19).
    The resolver populates the value of every field from the
    highest-priority source available; once constructed the
    configuration is immutable.
    """

    startup_profile: str = DEFAULT_STARTUP_PROFILE
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_device: str = DEFAULT_EMBEDDING_DEVICE
    dense_index: str = DEFAULT_DENSE_INDEX
    docling_enabled: bool = DEFAULT_DOCLING_ENABLED
    model_cache_dir: str = DEFAULT_MODEL_CACHE_DIR
    sources: Mapping[str, str] = field(default_factory=dict)

    def as_dict(self) -> Mapping[str, Any]:
        return asdict(self)


class RuntimeConfigurationResolver:
    """Resolve :class:`RuntimeConfiguration` from the documented
    precedence chain.

    The resolver reads sources in priority order; the first source
    that names a field wins. The :attr:`RuntimeConfiguration.sources`
    mapping records which source supplied each field for the logs
    and the web control plane.
    """

    _FIELD_ENV_VARS: Mapping[str, str] = {
        "startup_profile": ENV_STARTUP_PROFILE,
        "embedding_model": ENV_EMBEDDING_MODEL,
        "embedding_device": ENV_EMBEDDING_DEVICE,
        "dense_index": ENV_DENSE_INDEX,
        "docling_enabled": ENV_DOCLING_ENABLED,
        "model_cache_dir": ENV_MODEL_CACHE,
    }

    _DEFAULTS: Mapping[str, Any] = {
        "startup_profile": DEFAULT_STARTUP_PROFILE,
        "embedding_model": DEFAULT_EMBEDDING_MODEL,
        "embedding_device": DEFAULT_EMBEDDING_DEVICE,
        "dense_index": DEFAULT_DENSE_INDEX,
        "docling_enabled": DEFAULT_DOCLING_ENABLED,
        "model_cache_dir": DEFAULT_MODEL_CACHE_DIR,
    }

    def __init__(
        self,
        *,
        cli_overrides: Mapping[str, Any] | None = None,
        env: Mapping[str, str] | None = None,
        local_settings: Mapping[str, Any] | None = None,
        project_defaults: Mapping[str, Any] | None = None,
        local_settings_path: Path | None = None,
    ) -> None:
        self._cli_overrides = dict(cli_overrides or {})
        self._env = dict(env if env is not None else os.environ)
        self._local_settings = dict(
            local_settings if local_settings is not None
            else self._read_local_settings(local_settings_path),
        )
        if project_defaults is None and local_settings_path is not None:
            from pi_platform.core.ingest.config import load_ingest_config
            root = Path(local_settings_path).resolve().parent.parent
            candidates = [root / "project-knowledge/project-context.yaml", root / "project-context.yaml"]
            project_defaults = {}
            for candidate in candidates:
                if candidate.is_file():
                    body = load_ingest_config(candidate)
                    project_defaults = body.get("runtime", body.get("retrieval", {}))
                    if not isinstance(project_defaults, Mapping):
                        raise ConfigurationError("project context runtime defaults must be a mapping")
                    break
        self._project_defaults = dict(project_defaults or {})

    @staticmethod
    def _read_local_settings(path: Path | None) -> dict[str, Any]:
        if path is None:
            return {}
        candidate = Path(path)
        if not candidate.exists():
            alt = candidate.parent / "retrieval-settings.json"
            if alt.exists():
                candidate = alt
            else:
                return {}
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                data = dict(json.load(f))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"failed to read local settings {candidate}: {exc}"
            ) from exc
        if "embedding_model_alias" in data and "embedding_model" not in data:
            data["embedding_model"] = data["embedding_model_alias"]
        if "device" in data and "embedding_device" not in data:
            data["embedding_device"] = data["device"]
        if (
            "document_processing_enabled" in data
            and "docling_enabled" not in data
        ):
            data["docling_enabled"] = data["document_processing_enabled"]
        return data

    def resolve(self) -> RuntimeConfiguration:
        """Apply the precedence chain and return the resolved config."""

        resolved: dict[str, Any] = {}
        sources: dict[str, str] = {}
        for field, default in self._DEFAULTS.items():
            value, source = self._resolve_field(field, default)
            resolved[field] = value
            sources[field] = source

        if resolved["startup_profile"] == "minimal":
            for field, value in {"embedding_model": "hashing", "dense_index": "flat", "docling_enabled": False}.items():
                if sources[field] == "built-in":
                    resolved[field] = value
        self._validate(resolved)
        return RuntimeConfiguration(sources=sources, **resolved)

    def _resolve_field(
        self, field: str, default: Any,
    ) -> tuple[Any, str]:
        if field in self._cli_overrides:
            return self._coerce(field, self._cli_overrides[field]), "cli"
        env_key = self._FIELD_ENV_VARS.get(field)
        if env_key and env_key in self._env and self._env[env_key] != "":
            return (
                self._coerce(field, self._env[env_key]), f"env:{env_key}",
            )
        if field in self._local_settings:
            return (
                self._coerce(field, self._local_settings[field]),
                "local-settings",
            )
        if field in self._project_defaults:
            return (
                self._coerce(field, self._project_defaults[field]),
                "project-context",
            )
        return default, "built-in"

    def _coerce(self, field: str, value: Any) -> Any:
        if field == "docling_enabled":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"1", "true", "yes", "on"}:
                    return True
                if lowered in {"0", "false", "no", "off", ""}:
                    return False
            if isinstance(value, int):
                return bool(value)
            raise ConfigurationError(
                f"cannot coerce {field}={value!r} to bool"
            )
        if field == "startup_profile":
            if value not in {"production", "minimal", "development"}:
                raise ConfigurationError(
                    f"invalid startup_profile {value!r}; expected one of "
                    f"production, minimal, development"
                )
            return value
        if field == "embedding_device":
            if value not in {"auto", "cpu", "cuda", "mps", "vulkan"}:
                raise ConfigurationError(
                    f"invalid embedding_device {value!r}; expected one of "
                    f"auto, cpu, cuda, mps, vulkan"
                )
            return value
        if field == "embedding_model":
            aliases = {"embeddinggemma2": "gemma", "qwen3": "qwen", "qwen3-embedding-0.6b": "qwen",
                       "google/embeddinggemma-2": "gemma", "qwen/qwen3-embedding-0.6b": "qwen",
                       "ggml-org/embeddinggemma-2-gguf": "gemma-gguf",
                       "qwen/qwen3-embedding-0.6b-gguf": "qwen-gguf"}
            lowered = str(value).strip().lower()
            return aliases.get(lowered, lowered)
        if field == "dense_index":
            return str(value).strip().lower()
        if field == "model_cache_dir":
            return str(value)
        return value

    def _validate(self, resolved: dict[str, Any]) -> None:
        # The production-capability-gate covers the rest; here we
        # only ensure the well-known constraints from plan §19.
        if resolved["dense_index"] not in {"usearch", "flat"}:
            raise ConfigurationError("dense_index must be usearch or flat")
        if resolved["startup_profile"] == "production" and resolved["dense_index"] != "usearch":
            raise ConfigurationError("production requires the real usearch dense backend; select minimal for flat")
        startup = resolved["startup_profile"]
        embedding = resolved["embedding_model"]
        if startup == "production" and embedding not in {"gemma", "qwen", "qwen-gguf", "gemma-gguf"}:
            # The production profile refuses the hashing alias and
            # any other non-real alias; the operator must either
            # select an explicit production alias or switch to the
            # ``minimal`` profile.
            if embedding in {"hashing"} or embedding not in {
                "gemma", "qwen", "qwen-gguf", "gemma-gguf",
            }:
                raise ConfigurationError(
                    f"startup_profile='production' but "
                    f"embedding_model='{embedding}' is not a real "
                    f"production alias. Select 'gemma' or 'qwen', "
                    f"or switch startup_profile to 'minimal'."
                )
