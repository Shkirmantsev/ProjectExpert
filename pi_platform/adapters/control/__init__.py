"""Phase 7 §59 control-plane adapters (backends).

The adapter layer ships the optional storage backends the
core layer composes by default. The default in-memory
implementations under :mod:`pi_platform.core.control`
remain the authoritative production implementation; this
package supplies the swap-in storage backends (OS keychain,
encrypted local store, OpenTelemetry, JSONL audit sinks,
git-versioned feature flag source).
"""

from .audit_sinks import (
    JsonlAuditSink,
    JsonlOperationalSink,
    build_default_sink_pair,
    safe_unlink,
)
from .flag_sources import (
    GitVersionedFlagSource,
    LocalOverrideFlagSource,
    MachineLocalFlagSource,
)
from .policy_engine import (
    build_default_policy_engine,
)
from .secret_backends import (
    EncryptedLocalStoreBackend,
    EnvironmentBackend,
    KeychainBackend,
)
from .ui_extension_validator import (
    NoArbitraryJavaScriptValidator,
)

__all__ = [
    "EncryptedLocalStoreBackend",
    "EnvironmentBackend",
    "GitVersionedFlagSource",
    "JsonlAuditSink",
    "JsonlOperationalSink",
    "KeychainBackend",
    "LocalOverrideFlagSource",
    "MachineLocalFlagSource",
    "NoArbitraryJavaScriptValidator",
    "build_default_policy_engine",
    "build_default_sink_pair",
    "safe_unlink",
]