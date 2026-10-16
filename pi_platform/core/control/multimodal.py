"""Multimodal figures feature flag wiring (Change Package H).

Change Package H of the v0.8 refinement
(``improve-ingestion-retrieval-local-models``) adds the
``multimodal.figures`` feature flag. The flag is declared
``EXPERIMENTAL`` and defaults to ``DISABLED``; the real
CLIP / OpenCLIP binding ships in a follow-up change that
adds the corresponding optional dependency group.

The helper module exposes:

* :func:`build_default_multimodal_registry` — returns a
  :class:`DefaultFeatureFlagRegistry` pre-loaded with the
  ``multimodal.figures`` declaration;
* :func:`multimodal_figures_enabled` — convenience
  predicate that resolves the flag against a supplied
  context and returns a boolean;
* :func:`default_multimodal_context` — returns the
  default :class:`FeatureFlagContext` for an operator who
  has not customised the registry.

The flag is intentionally off-by-default so a Tier-1
harness run never accidentally enables the multimodal path.
"""

from __future__ import annotations

from typing import Optional

from pi_platform.core.control.flags import (
    DefaultFeatureFlagRegistry,
)
from pi_platform.ports.control.flags import (
    FeatureFlagContext,
    FeatureFlagPort,
    FeatureFlagScope,
    FeatureFlagState,
)


__all__ = [
    "MULTIMODAL_FIGURES_FLAG",
    "build_default_multimodal_registry",
    "default_multimodal_context",
    "multimodal_figures_enabled",
]


# The flag id is namespaced under ``multimodal.figures`` per
# the v0.8 Control Plane convention: the prefix names the
# domain (multimodal) and the suffix names the feature
# (figures). The flag id is referenced from the agent skill
# and from the Control Plane diagnostics panel.
MULTIMODAL_FIGURES_FLAG = "multimodal.figures"


def build_default_multimodal_registry() -> FeatureFlagPort:
    """Return a registry pre-loaded with the multimodal flags.

    The registry is returned as the abstract port so the
    caller (Control Plane / harness / operator shell) can
    swap it with a different implementation without
    breaking the contract.
    """

    registry = DefaultFeatureFlagRegistry()
    # Off-by-default; operators opt in by setting
    # PI_MULTIMODAL_FIGURES=1 or via the existing flag
    # override mechanism.
    registry.register(
        MULTIMODAL_FIGURES_FLAG,
        state=FeatureFlagState.EXPERIMENTAL,
        scope=FeatureFlagScope.DEPLOYMENT_PROFILE,
    )
    return registry


def default_multimodal_context(
    *, deployment_profile: str = "",
    user_id: str = "",
) -> FeatureFlagContext:
    """Return a default flag context for the multimodal registry.

    The context carries the deployment profile + user
    identity; the registry's scope resolution walks the
    documented precedence and resolves the flag against
    the most specific override.
    """

    return FeatureFlagContext(
        deployment_profile=deployment_profile,
        user_id=user_id,
    )


def multimodal_figures_enabled(
    registry: FeatureFlagPort,
    *,
    context: Optional[FeatureFlagContext] = None,
) -> bool:
    """Return ``True`` when the multimodal figures flag is enabled.

    The predicate swallows ``KeyError`` so a registry that
    has not been pre-loaded with the multimodal declaration
    returns ``False`` (the conservative off-by-default
    answer). The default registry produced by
    :func:`build_default_multimodal_registry` does carry the
    declaration; a hand-rolled registry used in tests may
    not.
    """

    ctx = context or default_multimodal_context()
    try:
        state = registry.resolve(MULTIMODAL_FIGURES_FLAG, context=ctx)
    except KeyError:
        return False
    return state is FeatureFlagState.ENABLED
