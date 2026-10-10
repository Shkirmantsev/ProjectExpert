"""Phase 7 §59.10 default Secret Provider.

The default provider parses the documented ``secret://``
and ``env://`` reference vocabulary and exposes a
redaction filter that replaces every resolved secret value
with the documented redacted form in MCP / A2A / audit /
LLM context channels.

The runtime database MUST NOT become a plain-text secret
vault; the provider persists :class:`SecretReference`
records only.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional

from pi_platform.ports.control.secrets import (
    InvalidSecretReferenceError,
    RedactionContext,
    SecretProviderPort,
    SecretReference,
    SecretResolutionError,
)


__all__ = ["DefaultSecretProvider"]


_SECRET_REF = re.compile(
    r"^secret://(?P<backend>[a-zA-Z0-9_-]+)/(?P<name>[a-zA-Z0-9._-]+)"
    r"(?:@(?P<version>[a-zA-Z0-9._-]+))?$"
)
_ENV_REF = re.compile(r"^env://(?P<name>[a-zA-Z0-9._-]+)$")


def _parse(raw: str) -> SecretReference:
    if not raw:
        raise InvalidSecretReferenceError(scheme="", raw=raw)
    if "://" not in raw:
        raise InvalidSecretReferenceError(scheme="", raw=raw)
    scheme, rest = raw.split("://", 1)
    if scheme not in {"secret", "env"}:
        raise InvalidSecretReferenceError(scheme=scheme, raw=raw)
    if scheme == "env":
        match = _ENV_REF.match(raw)
        if match is None:
            raise InvalidSecretReferenceError(scheme=scheme, raw=raw)
        return SecretReference(scheme="env", backend="env",
                                name=match.group("name"))
    match = _SECRET_REF.match(raw)
    if match is None:
        raise InvalidSecretReferenceError(scheme=scheme, raw=raw)
    return SecretReference(
        scheme="secret",
        backend=match.group("backend"),
        name=match.group("name"),
        version=match.group("version") or "",
    )


@dataclass
class DefaultSecretProvider(SecretProviderPort):
    """Default production Secret Provider."""

    _cache: dict[str, str] = field(default_factory=dict)
    _expires: dict[str, float] = field(default_factory=dict, repr=False)
    _backends: dict[str, Callable[[SecretReference], Optional[str]]
                    ] = field(default_factory=dict)
    _references: set[str] = field(default_factory=set)
    _ttl_seconds: int = 60

    def __post_init__(self) -> None:
        # Default backend: environment variables (no plaintext
        # persistence). The Phase 7 implementation never stores
        # resolved values to disk; the in-memory cache honours
        # the documented TTL and supports invalidation.
        self._backends.setdefault(
            "env",
            lambda ref: os.environ.get(ref.name),
        )

    def parse(self, raw: str) -> SecretReference:
        reference = _parse(raw)
        self._references.add(reference.canonical)
        return reference

    def resolve(self, reference: SecretReference, *,
                caller_capability: str = "secret.resolve") -> str:
        if caller_capability != "secret.resolve":
            # secret.reference is metadata-only; resolution
            # requires the higher capability.
            return reference.redacted_form
        cache_key = reference.canonical
        if cache_key in self._cache:
            expires_at = self._expires.get(cache_key)
            if expires_at is None or time.monotonic() < expires_at:
                return self._cache[cache_key]
            self.invalidate(reference)
        if reference.scheme == "env":
            backend_name = "env"
        else:
            backend_name = reference.backend
        backend = self._backends.get(backend_name)
        if backend is None:
            raise SecretResolutionError(
                reference=reference, reason=f"unknown backend {backend_name}",
            )
        value = backend(reference)
        if value is None:
            raise SecretResolutionError(
                reference=reference, reason="backend returned no value",
            )
        self._cache[cache_key] = value
        self._expires[cache_key] = time.monotonic() + self._ttl_seconds
        return value

    def redact(self, value: str, *,
               context: RedactionContext) -> str:
        # Replace EVERY occurrence of every resolved value,
        # including occurrences embedded inside a larger
        # field; longest values first so a secret that
        # contains another secret is not mangled.
        for canonical, cached in sorted(
                self._cache.items(),
                key=lambda kv: len(kv[1]), reverse=True):
            if cached and cached in value:
                ref = _parse(canonical)
                value = value.replace(cached, ref.redacted_form)
        return value

    def list_references(self) -> Iterable[SecretReference]:
        for raw in sorted(self._references):
            yield _parse(raw)

    def invalidate(self, reference: SecretReference) -> None:
        self._cache.pop(reference.canonical, None)
        self._expires.pop(reference.canonical, None)

    def register_backend(self, name: str,
                          backend: Callable[[SecretReference],
                                            Optional[str]]) -> None:
        self._backends[name] = backend

    def serialise(self) -> str:
        payload = {
            "references": sorted(self._references),
            "backends": sorted(self._backends.keys()),
            "ttlSeconds": self._ttl_seconds,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def has_resolved(self, value: str) -> bool:
        """True when ``value`` carries a previously resolved
        secret value, including as a substring of a larger
        field.
        """
        return any(cached and cached in value
                   for cached in self._cache.values())