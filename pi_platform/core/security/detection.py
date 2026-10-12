"""Phase 8 §56 Secret Detector core.

The default detector scans transient values
(chunk text, outgoing payloads, audit messages) with the
documented pattern bank from
:mod:`pi_platform.adapters.security.detection_patterns`
plus the high-entropy base64 heuristic.

The detector complements the Phase 7 Secret Provider; it
covers values the Secret Provider never resolved.

The detector does NOT raise on a finding; the calling
integration decides whether to drop, redact or emit an
audit record. When a :class:`DefaultSecurityAuditRecorder`
is wired, the detector emits a ``security.detect`` audit
event for every batch of findings (one event per scan);
the resource is the redacted finding list so raw values
never reach the audit log.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, Tuple

from pi_platform.adapters.security.detection_patterns import (
    DetectionPattern,
    default_pattern_bank,
)
from pi_platform.ports.security.audit import (
    SecurityAuditOp,
    SecurityAuditPort,
    SecurityEvent,
)
from pi_platform.ports.security.detection import (
    SecretDetectorPort,
    SecretFinding,
    SecretKind,
)


__all__ = ["DefaultSecretDetector", "shannon_entropy"]


HIGH_ENTROPY_MIN_LENGTH = 40
HIGH_ENTROPY_THRESHOLD = 4.5
# Conservative base64-ish alphabet; characters outside this
# set lower the entropy calculation.
_B64_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789+/=-_"
)


def shannon_entropy(value: str) -> float:
    """Return the Shannon entropy (bits / character) of
    ``value``.

    Empty values return ``0.0``; the function only counts
    characters that are part of the base64-ish alphabet
    toward the entropy. A line dominated by non-base64
    characters collapses to a single bucket, which lowers
    the entropy and naturally keeps the heuristic
    conservative.
    """

    if not value:
        return 0.0
    counts = Counter(value)
    total = len(value)
    base64_total = sum(
        freq for char, freq in counts.items()
        if char in _B64_CHARS
    )
    if base64_total == 0:
        return 0.0
    entropy = 0.0
    for char, freq in counts.items():
        if char not in _B64_CHARS:
            continue
        probability = freq / total
        entropy -= probability * math.log2(probability)
    return entropy


def _is_high_entropy_base64(value: str) -> bool:
    if len(value) < HIGH_ENTROPY_MIN_LENGTH:
        return False
    # Restrict to candidates that read like tokens
    # (base64 / base64url). Whitespace breaks the rule.
    if any(c.isspace() for c in value):
        return False
    return shannon_entropy(value) >= HIGH_ENTROPY_THRESHOLD


def _split_lines(value: str) -> Tuple[Tuple[int, str], ...]:
    if not value:
        return ()
    if "\n" not in value:
        return ((0, value),)
    return tuple(
        (index, line)
        for index, line in enumerate(value.splitlines())
    )


@dataclass
class DefaultSecretDetector(SecretDetectorPort):
    """§56 default Secret Detector."""

    _patterns: Tuple[DetectionPattern, ...] = field(
        default_factory=default_pattern_bank,
    )
    _min_entropy: float = HIGH_ENTROPY_THRESHOLD
    _audit: Optional[SecurityAuditPort] = field(
        default=None, repr=False,
    )

    def __post_init__(self) -> None:
        # Validates the configured pattern bank; a single
        # bad regex would otherwise surface only at scan
        # time. The detector does not fail loud on bad
        # patterns — it raises ValueError so the calling
        # configuration loader can react; a runtime
        # ``scan`` over a bad pattern would simply miss.
        for pattern in self._patterns:
            if pattern.regex is None:
                raise ValueError(
                    f"detection pattern {pattern.kind.value} "
                    f"carries a None regex"
                )

    def attach_audit(self, audit: SecurityAuditPort) -> None:
        self._audit = audit

    def scan(
        self, value: str, *, field: str = "value",
    ) -> Tuple[SecretFinding, ...]:
        findings: list[SecretFinding] = []
        if not value:
            return tuple(findings)
        for line_index, line in _split_lines(value):
            for pattern in self._patterns:
                for match in pattern.regex.finditer(line):
                    findings.append(SecretFinding(
                        field=field, value=match.group(0),
                        kind=pattern.kind,
                        line_index=line_index,
                    ))
            if _is_high_entropy_base64(line):
                findings.append(SecretFinding(
                    field=field, value=line,
                    kind=SecretKind.HIGH_ENTROPY_BASE64,
                    entropy=shannon_entropy(line),
                    line_index=line_index,
                ))
        result = tuple(findings)
        if self._audit is not None and result:
            self._emit_audit(result, field=field)
        return result

    def _emit_audit(
        self, findings: Tuple[SecretFinding, ...], *,
        field: str,
    ) -> None:
        if self._audit is None:
            return
        # The audit resource is the redacted finding list
        # so raw values never reach the audit log.
        redacted = [
            {"kind": f.kind.value, "line": f.line_index}
            for f in findings
        ]
        try:
            self._audit.record(SecurityEvent(
                operation=SecurityAuditOp.DETECT,
                result="FOUND",
                resource=f"field={field} findings={redacted}",
            ))
        except Exception:
            # Audit emission MUST be best-effort.
            pass

    def serialise(self) -> str:
        import json
        payload = {
            "version": "phase-8.0",
            "minEntropy": self._min_entropy,
            "patterns": [
                {"kind": p.kind.value, "description": p.description}
                for p in self._patterns
            ],
        }
        return json.dumps(payload, sort_keys=True,
                          separators=(",", ":"))
