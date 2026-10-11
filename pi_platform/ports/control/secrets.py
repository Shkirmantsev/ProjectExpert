"""Phase 7 §59.10 Secret Provider port.

The Secret Provider resolves the ``secret://`` and
``env://`` reference vocabulary and exposes a redaction
filter for MCP / A2A / audit / LLM context channels.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional


__all__ = [
    "InvalidSecretReferenceError",
    "RedactionContext",
    "SecretProviderPort",
    "SecretReference",
    "SecretResolutionError",
]


class RedactionContext(str, enum.Enum):
    """The four documented channels the redaction filter
    applies to.
    """

    MCP_RESPONSE = "mcp"
    A2A_PAYLOAD = "a2a"
    AUDIT_PAYLOAD = "audit"
    LLM_CONTEXT = "llm"


@dataclass(frozen=True)
class SecretReference:
    """The parsed form of a ``secret://`` or ``env://``
    reference.
    """

    scheme: str  # "secret" or "env"
    backend: str  # "local", "enterprise", ...
    name: str
    version: str = ""

    def as_dict(self) -> dict:
        return {
            "scheme": self.scheme,
            "backend": self.backend,
            "name": self.name,
            "version": self.version,
        }

    @property
    def canonical(self) -> str:
        if self.scheme == "env":
            return f"env://{self.name}"
        if self.version:
            return f"secret://{self.backend}/{self.name}@{self.version}"
        return f"secret://{self.backend}/{self.name}"

    @property
    def redacted_form(self) -> str:
        return f"{self.canonical}[REDACTED]"


class InvalidSecretReferenceError(RuntimeError):
    """Raised when a reference does not match the documented
    vocabulary.
    """

    def __init__(self, *, scheme: str, raw: str) -> None:
        self.scheme = scheme
        self.raw = raw
        super().__init__(
            f"invalid-secret-reference: scheme={scheme!r} raw={raw!r}"
        )


class SecretResolutionError(RuntimeError):
    """Raised when a secret backend cannot resolve a
    reference. The calling consumer translates this error
    into ``DENY`` when the calling capability is
    ``secret.resolve``.
    """

    def __init__(self, *, reference: SecretReference, reason: str) -> None:
        self.reference = reference
        self.reason = reason
        super().__init__(
            f"secret-resolution-error: reference="
            f"{reference.canonical!r} reason={reason!r}"
        )


class SecretProviderPort(abc.ABC):
    """§59.10 Secret Provider port."""

    @abc.abstractmethod
    def parse(self, raw: str) -> SecretReference: ...

    @abc.abstractmethod
    def resolve(self, reference: SecretReference,
                *, caller_capability: str = "secret.resolve") -> str: ...

    @abc.abstractmethod
    def redact(self, value: str, *,
               context: RedactionContext) -> str: ...

    @abc.abstractmethod
    def list_references(self) -> Iterable[SecretReference]: ...

    @abc.abstractmethod
    def invalidate(self, reference: SecretReference) -> None: ...

    @abc.abstractmethod
    def serialise(self) -> str: ...

    def has_resolved(self, value: str) -> bool:
        """Return ``True`` when ``value`` carries a previously
        resolved secret value, including as a substring of
        a larger field.

        The default implementation returns ``False`` so the
        abstract port remains backward compatible with any
        existing adapter; the production in-process
        :class:`DefaultSecretProvider` overrides this and the
        Phase 8 redaction pipeline consults the override.
        """

        return False