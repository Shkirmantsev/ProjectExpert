"""Phase 8 §56 Redaction Pipeline port.

The pipeline composes the Phase 7 Secret Provider redaction
with classification-driven redaction. Both steps run in
order; the pipeline MUST assert the no-resolved-value
invariant by calling :class:`SecretProvider.has_resolved`
after the second step.
"""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass
from typing import Mapping, Tuple

from pi_platform.ports.control.policy import Role
from pi_platform.ports.control.secrets import RedactionContext


__all__ = [
    "RedactionResult",
    "RedactionPipelinePort",
    "RedactionFailureError",
    "RedactionStep",
]


@dataclass(frozen=True)
class RedactionStep:
    """A single documented pipeline step.

    Attributes:
        name: short identifier used in audit payloads
            (``"phase7_secret_provider"``,
            ``"phase8_classification_driven"``).
        description: human-readable description.
    """

    name: str
    description: str = ""


@dataclass(frozen=True)
class RedactionResult:
    """The structured pipeline result.

    Attributes:
        value: the redacted output value.
        steps: tuple of the documented pipeline steps
            that fired on this invocation.
        audit_emitted: ``True`` when an audit record was
            emitted; the calling integration may use the
            flag to avoid double emission.
    """

    value: str
    steps: Tuple[RedactionStep, ...]
    audit_emitted: bool = True


class RedactionFailureError(RuntimeError):
    """Raised when the pipeline detects a leaked resolved
    secret value after both steps.
    """

    def __init__(self, *, reason: str, value: str) -> None:
        self.reason = reason
        self.value = value
        super().__init__(
            f"redaction-failure: reason={reason!r} "
            f"value={value!r}"
        )


class RedactionPipelinePort(abc.ABC):
    """§56 Redaction Pipeline port."""

    @abc.abstractmethod
    def redact(
        self, value: str, *, channel: RedactionContext,
        classification: str, actor_role: Role,
        actor_capabilities: Tuple[str, ...] = (),
    ) -> RedactionResult:
        """Run the documented two-step pipeline and
        return the :class:`RedactionResult`. Implementations
        MUST assert the no-resolved-value invariant.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def steps(self) -> Tuple[RedactionStep, ...]:
        """Return the documented pipeline step identifiers,
        in execution order.
        """
        raise NotImplementedError

    def serialise(self) -> str:
        """Byte-stable JSON serialisation of the pipeline
        composition.
        """
        payload = {
            "steps": [{"name": s.name, "description": s.description}
                       for s in self.steps()],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
