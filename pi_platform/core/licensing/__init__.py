"""Licensing core package: policy, gate, inventory, SBOM emitter."""

from .gate import LicenseGate
from .inventory import (
    DEFAULT_DEPENDENCY_INVENTORY_PATH,
    DEFAULT_MODEL_LICENSE_PATH,
    DependencyInventory,
    ModelLicenseInventory,
    stub_inventory,
)
from .policy import (
    DEFAULT_ALLOW_LICENSES,
    DEFAULT_DENY_PATTERNS,
    DEFAULT_REVIEW_LICENSES,
    LicensePolicy,
    PolicyConfig,
)
from .sbom import (
    DEFAULT_NOTICE_PATH,
    DEFAULT_SBOM_PATH,
    emit_notice_file,
    emit_spdx_sbom,
)

__all__ = [
    "DEFAULT_ALLOW_LICENSES",
    "DEFAULT_DEPENDENCY_INVENTORY_PATH",
    "DEFAULT_DENY_PATTERNS",
    "DEFAULT_MODEL_LICENSE_PATH",
    "DEFAULT_NOTICE_PATH",
    "DEFAULT_REVIEW_LICENSES",
    "DEFAULT_SBOM_PATH",
    "DependencyInventory",
    "LicenseGate",
    "LicensePolicy",
    "ModelLicenseInventory",
    "PolicyConfig",
    "emit_notice_file",
    "emit_spdx_sbom",
    "stub_inventory",
]