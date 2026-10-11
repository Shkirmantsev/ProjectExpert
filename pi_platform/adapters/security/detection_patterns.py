"""Phase 8 §56 detection pattern bank.

Returns the documented Phase 8 regex bank used by
``DefaultSecretDetector`` and exposed for ad-hoc checks.

The bank is exported as a tuple of :class:`_Pattern`-shaped
dicts (kind, regex, description) that the detector can
iterate without modification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

from pi_platform.ports.security.detection import SecretKind


__all__ = ["DetectionPattern", "default_pattern_bank", "PATTERN_BANK_VERSION"]


PATTERN_BANK_VERSION = "phase-8.0"


@dataclass(frozen=True)
class DetectionPattern:
    """A single detection pattern entry."""

    kind: SecretKind
    regex: "re.Pattern[str]"
    description: str = ""


def default_pattern_bank() -> Tuple[DetectionPattern, ...]:
    """Return the canonical Phase 8 detection pattern bank.

    Order matters: more-specific patterns (e.g. ``JWT``)
    are evaluated before less-specific fallbacks
    (``GENERIC_API_KEY``). Adding new patterns later is a
    non-breaking additive change; removing a pattern is a
    breaking change to the documented detection
    vocabulary.
    """

    return (
        DetectionPattern(
            kind=SecretKind.AWS_ACCESS_KEY,
            regex=re.compile(r"AKIA[0-9A-Z]{16}"),
            description="AWS access key id",
        ),
        DetectionPattern(
            kind=SecretKind.GITHUB_TOKEN,
            regex=re.compile(r"ghp_[A-Za-z0-9]{36}"),
            description="GitHub personal access token (PAT)",
        ),
        DetectionPattern(
            kind=SecretKind.PEM_PRIVATE_KEY_HEADER,
            regex=re.compile(
                r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP |"
                r"ENCRYPTED )?PRIVATE KEY-----"
            ),
            description="PEM private-key header",
        ),
        DetectionPattern(
            kind=SecretKind.JWT_BEARER,
            regex=re.compile(
                r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
                r"\.[A-Za-z0-9_-]{10,}"
            ),
            description="JWT bearer (header.payload.signature)",
        ),
        DetectionPattern(
            kind=SecretKind.GENERIC_API_KEY,
            regex=re.compile(
                r"(?i)api[-_]?key[\"'`]?\s*[:=]\s*[\"'`]([A-Za-z0-9_\-]{16,})"
                r"[\"'`]"
            ),
            description="generic API key literal in text",
        ),
    )
