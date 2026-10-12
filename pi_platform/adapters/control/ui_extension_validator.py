"""Phase 7 §59.16 no-arbitrary-JavaScript validator.

The validator is a thin wrapper around the documented
:func:`DefaultUiExtensionRegistry.validate` static logic
exposed as an importable helper so tests can exercise the
no-arbitrary-JS rule without standing up the full
registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pi_platform.core.control.ui_extensions import DefaultUiExtensionRegistry
from pi_platform.ports.control.ui_extensions import (
    InvalidUiExtensionDescriptorError,
    UiExtensionDescriptor,
)


__all__ = ["NoArbitraryJavaScriptValidator"]


@dataclass
class NoArbitraryJavaScriptValidator:
    """Validator that enforces the §59.16 no-arbitrary-
    JavaScript rule.
    """

    _registry: DefaultUiExtensionRegistry = field(
        default_factory=DefaultUiExtensionRegistry)

    def validate(self, descriptor: UiExtensionDescriptor) -> None:
        self._registry.validate(descriptor)