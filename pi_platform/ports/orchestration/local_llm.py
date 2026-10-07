"""Local LLM port for the v0.8 Phase 5 orchestration layer.

Covers architecture section §35 (Small Local LLM) and the
§5.4 model-license inventory contract. The
:class:`LocalLLMPort` exposes a pluggable local LLM surface
that the Phase 5 :class:`QueryOrchestratorPort` consumes for
L1 contextualisation when the capability is available; the
port is opt-in and the default container ships without a
model binding.
"""

from __future__ import annotations

import abc
from typing import Mapping, Optional


__all__ = [
    "LocalLLMPort",
    "LocalLLMError",
]


class LocalLLMError(RuntimeError):
    """Raised when the local LLM cannot satisfy a request."""


class LocalLLMPort(abc.ABC):
    """Abstract local LLM port."""

    @abc.abstractmethod
    def complete(
        self, prompt: str, *, max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str: ...

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @abc.abstractmethod
    def model_version(self) -> str: ...

    @abc.abstractmethod
    def license_id(self) -> str: ...

    @abc.abstractmethod
    def family(self) -> str: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...