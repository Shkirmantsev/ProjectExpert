"""Phase 8 §56 default Security Classifier.

The default classifier owns an in-memory
``source_id -> ceiling`` mapping. Persistent configuration
lives under the canonical tree per §7.1.

The classifier defaults unlabelled documents to ``PUBLIC``
so a missing field never silently leaks ``RESTRICTED``
content.

When a :class:`DefaultSecurityAuditRecorder` is wired, the
classifier emits a ``security.classify`` audit event for
every ``classify_document`` invocation so the §56 audit
vocabulary contract is fully honoured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from pi_platform.ports.security.audit import (
    SecurityAuditOp,
    SecurityAuditPort,
    SecurityEvent,
)
from pi_platform.ports.security.classification import (
    DEFAULT_LEVEL,
    ClassificationLevel,
    DocumentClassification,
    RANK,
    SecurityClassificationPort,
    SourceClassification,
    coerce_level,
)


__all__ = ["DefaultSecurityClassifier"]


@dataclass
class DefaultSecurityClassifier(SecurityClassificationPort):
    """§56 default classifier."""

    _ceilings: Dict[str, ClassificationLevel] = field(default_factory=dict)
    _audit: Optional[SecurityAuditPort] = field(
        default=None, repr=False,
    )

    def attach_audit(self, audit: SecurityAuditPort) -> None:
        self._audit = audit

    def set_ceiling(
        self, source_id: str, level: ClassificationLevel,
    ) -> None:
        self._ceilings[source_id] = level

    def classify_source(self, source_id: str) -> ClassificationLevel:
        return self._ceilings.get(source_id, DEFAULT_LEVEL)

    def ceiling_for(self, source_id: str) -> ClassificationLevel:
        return self.classify_source(source_id)

    def ceilings(self) -> Tuple[SourceClassification, ...]:
        return tuple(
            SourceClassification(source_id=source_id,
                                 ceiling=level)
            for source_id, level in sorted(self._ceilings.items())
        )

    def classify_document(
        self, document_id: str, raw_level: Optional[str],
        source_id: str = "",
    ) -> DocumentClassification:
        level = coerce_level(raw_level)
        ceiling = self.ceiling_for(source_id)
        if ceiling != DEFAULT_LEVEL and RANK[level] > RANK[ceiling]:
            level = ceiling
        result = DocumentClassification(
            document_id=document_id, level=level, source_id=source_id,
        )
        if self._audit is not None:
            try:
                self._audit.record(SecurityEvent(
                    operation=SecurityAuditOp.CLASSIFY,
                    result=level.value,
                    resource=f"document={document_id} source={source_id}",
                ))
            except Exception:
                # Audit emission MUST be best-effort.
                pass
        return result
