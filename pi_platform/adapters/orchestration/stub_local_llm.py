"""Stub LocalLLM adapter.

Wraps :class:`pi_platform.core.orchestration.local_llm.StubLocalLLMCore`
as a thin adapter so the registry / CLI can introspect the
same shape across the stub and the opt-in llama-cpp /
transformers backends. The stub ships in the default
container; the orchestrator degrades gracefully to L0 / L2
when the stub is the active adapter.
"""

from __future__ import annotations

from pi_platform.core.orchestration.local_llm import (
    STUB_FAMILY,
    STUB_LICENSE_ID,
    STUB_MODEL_VERSION,
    StubLocalLLMCore,
)


__all__ = [
    "StubLocalLLMAdapter",
    "ADAPTER_NAME",
]


ADAPTER_NAME = "local-llm-stub"


class StubLocalLLMAdapter(StubLocalLLMCore):
    """Default stub LocalLLM adapter."""

    def __init__(self) -> None:
        super().__init__()
        self._name = ADAPTER_NAME

    @property
    def backend_name(self) -> str:
        return self._name


# Re-export the documented constants for the license inventory.
FAMILY = STUB_FAMILY
MODEL_VERSION = STUB_MODEL_VERSION
LICENSE_ID = STUB_LICENSE_ID