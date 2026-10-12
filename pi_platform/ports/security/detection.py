"""Phase 8 §56 Secret Detection port.

The detector scans transient values (chunk text, outgoing
payloads, audit messages) for high-signal patterns and
generic high-entropy base64 strings. The detector
complements the Phase 7 Secret Provider; it covers values
the Secret Provider never resolved.
"""

from __future__ import annotations

import abc
import enum
import json
from dataclasses import dataclass, field
from typing import Iterable, Tuple


__all__ = [
    "SecretKind",
    "SecretFinding",
    "SecretDetectorPort",
    "SecretDetectorError",
]


class SecretKind(str, enum.Enum):
    """§56 documented detection kinds."""

    AWS_ACCESS_KEY = "AWS_ACCESS_KEY"
    GITHUB_TOKEN = "GITHUB_TOKEN"
    PEM_PRIVATE_KEY_HEADER = "PEM_PRIVATE_KEY_HEADER"
    JWT_BEARER = "JWT_BEARER"
    HIGH_ENTROPY_BASE64 = "HIGH_ENTROPY_BASE64"
    GENERIC_API_KEY = "GENERIC_API_KEY"


@dataclass(frozen=True)
class SecretFinding:
    """A single secret detection finding.

    Attributes:
        field: free-form field label (e.g. ``"chunk.text"``).
        value: the redacted form of the matched value; raw
            values are redacted to ``[REDACTED:<kind>]``
            before any external serialisation.
        kind: the matched :class:`SecretKind`.
        entropy: Shannon entropy in bits / character
            (``None`` for regex / dictionary matches;
            ``>= 4.5`` for the documented entropy threshold
            on ``HIGH_ENTROPY_BASE64``).
        line_index: zero-based line index where the match
            was found (``0`` when the input has no
            newlines).
    """

    field: str
    value: str
    kind: SecretKind
    entropy: float = 0.0
    line_index: int = 0

    def redacted(self) -> "SecretFinding":
        """Return a copy with the value replaced by the
        documented ``[REDACTED:<kind>]`` form.
        """
        if self.value.startswith("[REDACTED:"):
            return self
        marker = f"[REDACTED:{self.kind.value}]"
        return SecretFinding(
            field=self.field, value=marker, kind=self.kind,
            entropy=self.entropy, line_index=self.line_index,
        )


class SecretDetectorError(RuntimeError):
    """Raised when a detector adapter fails irrecoverably."""


class SecretDetectorPort(abc.ABC):
    """§56 Secret Detector port."""

    @abc.abstractmethod
    def scan(self, value: str, *, field: str = "value") -> Tuple[SecretFinding, ...]:
        """Return zero or more ``SecretFinding`` records;
        the ``field`` parameter is recorded on every
        finding for downstream audit emission.
        """
        raise NotImplementedError

    def serialise(self) -> str:
        """Byte-stable JSON serialisation of the configured
        pattern bank.
        """
        payload = {
            "kinds": [k.value for k in SecretKind],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @property
    def kinds(self) -> Iterable[SecretKind]:  # pragma: no cover - info helper
        return tuple(SecretKind)


@dataclass
class _Pattern:
    """Compiled regex + metadata, used by the default
    detector implementation.
    """

    kind: SecretKind
    regex: object  # re.Pattern[str] but typing only by ref
    description: str = ""
