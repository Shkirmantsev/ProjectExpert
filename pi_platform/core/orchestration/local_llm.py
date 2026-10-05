"""Default stub LocalLLMPort core.

Implements :class:`pi_platform.ports.orchestration.local_llm.LocalLLMPort`
with a deterministic stub that ships in the default container.
The stub reports `is_available() == False` and returns an
empty string from `complete`, satisfying the §35
"commercially-usable license" and "CPU-capable deployment"
scenarios with no new runtime dependency.

Opt-in LLM backends (llama-cpp, transformers) are registered
as adapters under
:mod:`pi_platform.adapters.orchestration` when the
corresponding Python package is installed AND
`project-context.yaml:orchestrator.local_llm.family` is set
to the family's name. The orchestrator gracefully degrades to
L0 / L2 when the stub is the active adapter.
"""

from __future__ import annotations

from typing import Mapping

from pi_platform.ports.orchestration.local_llm import (
    LocalLLMError,
    LocalLLMPort,
)


__all__ = [
    "StubLocalLLMCore",
    "STUB_FAMILY",
    "STUB_MODEL_VERSION",
    "STUB_LICENSE_ID",
]


STUB_FAMILY = "stub"
STUB_MODEL_VERSION = "stub-1.0.0"
STUB_LICENSE_ID = "Apache-2.0"
STUB_MAX_TOKENS = 4


class StubLocalLLMCore(LocalLLMPort):
    """Deterministic stdlib-only stub LLM port."""

    family_name = STUB_FAMILY

    def __init__(self) -> None:
        self._calls = 0
        self._errors = 0
        self._tokens_in = 0
        self._tokens_out = 0

    def complete(
        self, prompt: str, *, max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str:
        self._calls += 1
        if not prompt:
            self._errors += 1
            raise LocalLLMError("empty prompt")
        if max_tokens <= 0:
            self._errors += 1
            raise LocalLLMError(
                f"max_tokens must be positive, got {max_tokens}"
            )
        char_budget = max_tokens * STUB_MAX_TOKENS
        self._tokens_in += len(prompt.split())
        completion = ""
        self._tokens_out += len(completion.split())
        if len(completion) > char_budget:
            self._errors += 1
            raise LocalLLMError(
                f"stub completion exceeded char_budget={char_budget}"
            )
        return completion

    def is_available(self) -> bool:
        return False

    def model_version(self) -> str:
        return STUB_MODEL_VERSION

    def license_id(self) -> str:
        return STUB_LICENSE_ID

    def family(self) -> str:
        return self.family_name

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "errors": self._errors,
            "tokens_in": self._tokens_in,
            "tokens_out": self._tokens_out,
        }