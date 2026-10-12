"""Phase 7 §59.16 UI Extension Registry port.

The registry accepts only declarative UI descriptors. The
validator rejects any descriptor carrying executable
JavaScript or any field outside the documented schema.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional


__all__ = [
    "InvalidUiExtensionDescriptorError",
    "UiExtensionDescriptor",
    "UiExtensionKind",
    "UiExtensionRegistryPort",
]


class UiExtensionKind(str, enum.Enum):
    """§59.16 documented descriptor shapes."""

    SETTINGS_PANEL = "settingsPanel"
    STATUS_PANEL = "statusPanel"
    DASHBOARD_WIDGET = "dashboardWidget"
    MENU_ITEM = "menuItem"


# Forbidden field set (no arbitrary JavaScript injection)
_FORBIDDEN_FIELDS: frozenset[str] = frozenset({
    "javascript",
    "js",
    "script",
    "onclick",
    "onerror",
    "onload",
    "onmouseover",
    "eval",
    "function",
    "settimeout",
    "setinterval",
})

# Forbidden string patterns inside any string field
_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    "<script",
    "</script>",
    "<iframe",
    "</iframe>",
    "javascript:",
    "data:",
    "vbscript:",
)


@dataclass(frozen=True)
class UiExtensionDescriptor:
    """The declarative UI extension descriptor."""

    id: str
    kind: UiExtensionKind
    title: str
    description: str = ""
    icon: str = ""
    route: str = ""
    configuration_schema: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "route": self.route,
            "configurationSchema": self.configuration_schema,
        }


class InvalidUiExtensionDescriptorError(RuntimeError):
    """Raised when a descriptor fails validation."""

    def __init__(self, *, field_name: str, value: str,
                 reason: str) -> None:
        self.field_name = field_name
        self.value = value
        self.reason = reason
        super().__init__(
            f"invalid-ui-extension-descriptor: field={field_name!r} "
            f"reason={reason!r} value={value!r}"
        )


class UiExtensionRegistryPort(abc.ABC):
    """§59.16 UI Extension Registry port."""

    @abc.abstractmethod
    def register(self, descriptor: UiExtensionDescriptor) -> None: ...

    @abc.abstractmethod
    def unregister(self, descriptor_id: str) -> None: ...

    @abc.abstractmethod
    def list(self) -> Iterable[UiExtensionDescriptor]: ...

    @abc.abstractmethod
    def validate(self,
                 descriptor: UiExtensionDescriptor) -> None: ...

    @abc.abstractmethod
    def serialise(self) -> str: ...