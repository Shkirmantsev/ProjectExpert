"""Phase 7 §59 control-plane core (default implementations).

The core layer ships the default production adapters for
the Phase 7 control-plane ports. Adapters live under
``pi_platform/adapters/control/*`` and the CLI / MCP / hooks
glue code can swap any of them through the documented ports.
"""

from .audit import (
    DefaultAuditLog,
    DefaultOperationalLog,
)
from .flags import (
    DefaultFeatureFlagRegistry,
)
from .hooks import (
    DefaultHookRuntime,
)
from .policy import (
    DefaultPolicyEngine,
)
from .registry import (
    DefaultFeatureRegistry,
    DefaultPluginRegistry,
)
from .secrets import (
    DefaultSecretProvider,
)
from .ui_extensions import (
    DefaultUiExtensionRegistry,
)

__all__ = [
    "DefaultAuditLog",
    "DefaultFeatureFlagRegistry",
    "DefaultFeatureRegistry",
    "DefaultHookRuntime",
    "DefaultOperationalLog",
    "DefaultPluginRegistry",
    "DefaultPolicyEngine",
    "DefaultSecretProvider",
    "DefaultUiExtensionRegistry",
]