"""Phase 7 §59.16 default UI Extension Registry.

The default registry accepts only declarative UI descriptors
and enforces the no-arbitrary-JavaScript rule from §59.16.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

from pi_platform.core.control.audit import _safe_record
from pi_platform.ports.control.ui_extensions import (
    InvalidUiExtensionDescriptorError,
    UiExtensionDescriptor,
    UiExtensionKind,
    UiExtensionRegistryPort,
    _FORBIDDEN_FIELDS,
    _FORBIDDEN_PATTERNS,
)


__all__ = ["DefaultUiExtensionRegistry"]


_FORBIDDEN_PATTERN = re.compile(
    "|".join(re.escape(p) for p in _FORBIDDEN_PATTERNS),
    re.IGNORECASE,
)

# Substring tokens that must never appear anywhere in any
# string field of a descriptor. The §59.16 no-arbitrary-JS
# rule rejects these even when the surrounding markup is
# well-formed.
_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "onclick",
    "onerror",
    "onload",
    "onmouseover",
    "eval(",
    "function(",
)


def _walk_strings(payload: object) -> Iterable[tuple[list[str], str]]:
    """Yield ``(path, value)`` for every string nested in
    ``payload``.
    """
    if isinstance(payload, str):
        yield [], payload
        return
    if isinstance(payload, list):
        for i, item in enumerate(payload):
            for sub_path, value in _walk_strings(item):
                yield [f"[{i}]", *sub_path], value
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            for sub_path, nested in _walk_strings(value):
                yield [f".{key}", *sub_path], nested


@dataclass
class DefaultUiExtensionRegistry(UiExtensionRegistryPort):
    """Default production UI Extension Registry."""

    _items: dict[str, UiExtensionDescriptor] = field(default_factory=dict)
    _audit_hook: Optional[object] = field(default=None, repr=False)

    def register(self, descriptor: UiExtensionDescriptor) -> None:
        # Validate the kind first so the descriptor never
        # reaches the field-level validator with a malformed
        # kind.
        if not isinstance(descriptor.kind, UiExtensionKind):
            raise InvalidUiExtensionDescriptorError(
                field_name="kind",
                value=str(descriptor.kind),
                reason="unknown kind",
            )
        self.validate(descriptor)
        if descriptor.id in self._items:
            raise InvalidUiExtensionDescriptorError(
                field_name="id",
                value=descriptor.id,
                reason="duplicate descriptor id",
            )
        self._items[descriptor.id] = descriptor
        self._audit(operation="ui_extension.register", result="allowed",
                    descriptor_id=descriptor.id)

    def unregister(self, descriptor_id: str) -> None:
        removed = self._items.pop(descriptor_id, None)
        if removed is not None:
            self._audit(operation="ui_extension.unregister",
                        result="allowed", descriptor_id=descriptor_id)

    def list(self) -> Iterable[UiExtensionDescriptor]:
        for descriptor_id in sorted(self._items):
            yield self._items[descriptor_id]

    def validate(self, descriptor: UiExtensionDescriptor) -> None:
        # Top-level fields must belong to the documented schema.
        allowed = {"id", "kind", "title", "description", "icon",
                   "route", "configurationSchema"}
        declared = set(descriptor.as_dict().keys())
        forbidden = declared - allowed
        if forbidden:
            raise InvalidUiExtensionDescriptorError(
                field_name=",".join(sorted(forbidden)),
                value=",".join(sorted(forbidden)),
                reason="field outside the documented schema",
            )
        # Walk every string value for forbidden patterns.
        for path, value in _walk_strings(descriptor.as_dict()):
            joined = "".join(path)
            lowered = value.lower()
            if lowered in _FORBIDDEN_FIELDS:
                raise InvalidUiExtensionDescriptorError(
                    field_name=joined or "<root>",
                    value=value,
                    reason=f"forbidden field token {value!r}",
                )
            for token in _FORBIDDEN_TOKENS:
                if token in lowered:
                    raise InvalidUiExtensionDescriptorError(
                        field_name=joined or "<root>",
                        value=value,
                        reason=f"forbidden token {token!r}",
                    )
            if _FORBIDDEN_PATTERN.search(lowered):
                reason = "forbidden pattern"
                if "data:" in lowered:
                    reason = "forbidden pattern (data URI)"
                elif "<script" in lowered or "</script>" in lowered:
                    reason = "forbidden pattern (<script>)"
                elif "<iframe" in lowered or "</iframe>" in lowered:
                    reason = "forbidden pattern (<iframe>)"
                elif "javascript:" in lowered:
                    reason = "forbidden pattern (javascript: URI)"
                raise InvalidUiExtensionDescriptorError(
                    field_name=joined or "<root>",
                    value=value,
                    reason=reason,
                )

    def serialise(self) -> str:
        payload = {
            "items": [
                d.as_dict()
                for d in sorted(self._items.values(), key=lambda d: d.id)
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def _audit(self, *, operation: str, result: str,
               descriptor_id: str) -> None:
        _safe_record(
            self._audit_hook,
            operation=operation,
            result=result,
            resource=descriptor_id,
        )

    def attach_audit_log(self, audit_log: object) -> None:
        self._audit_hook = audit_log