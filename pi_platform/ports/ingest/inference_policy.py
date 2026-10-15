"""Inference policy value object (Change Package B5).

The :class:`InferencePolicy` is evaluated separately from the source
promotion / persistence policy (``LOCAL_ONLY | REFERENCE |
SNAPSHOT``): a source stored ``LOCAL_ONLY`` may still be processed by
a local model when the inference policy allows it. ADR-0027 records
the decision to keep the two policy axes independent.
"""

from __future__ import annotations

import enum


__all__ = [
    "InferencePolicy",
    "DEFAULT_INFERENCE_POLICY",
    "policy_allows",
]


class InferencePolicy(str, enum.Enum):
    """Which model exposure the current profile permits.

    Stable uppercase string values keep the policy indexable in
    canonical records and audit logs.
    """

    NO_MODEL = "NO_MODEL"
    LOCAL_MODEL_ALLOWED = "LOCAL_MODEL_ALLOWED"
    EXTERNAL_MODEL_ALLOWED = "EXTERNAL_MODEL_ALLOWED"


DEFAULT_INFERENCE_POLICY = InferencePolicy.NO_MODEL
"""Deterministic default: no model sees any content."""


def policy_allows(policy: InferencePolicy, *, model_kind: str) -> bool:
    """Return whether ``policy`` permits ``model_kind`` inference.

    ``model_kind`` is ``"local"`` or ``"external"``. External-model
    permission is the strictly more permissive axis, so
    ``EXTERNAL_MODEL_ALLOWED`` also permits local models; an unknown
    ``model_kind`` is rejected.
    """

    if model_kind not in ("local", "external"):
        raise ValueError(
            f"model_kind must be 'local' or 'external', got {model_kind!r}"
        )
    if not isinstance(policy, InferencePolicy):
        policy = InferencePolicy(policy)
    if policy is InferencePolicy.NO_MODEL:
        return False
    if policy is InferencePolicy.LOCAL_MODEL_ALLOWED:
        return model_kind == "local"
    return True
