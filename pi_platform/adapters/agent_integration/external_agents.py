"""Phase 10 §51 external coding agent adapters.

Each supported external agent identity gets one
:class:`pi_platform.ports.a2a.ExternalAgentPort` implementation.
The implementations are intentionally small and deterministic: they
advertise the agent's metadata through :meth:`metadata`, expose a
:func:`submit` that the orchestrator calls once the policy gate has
approved the delegation, and a :meth:`health` helper used by the
quality-gates suites.

The adapters in v1.0 are *callable only* — they do not shell out to
real vendor tooling. The structural shape matches what a future
build will need (each adapter already declares its
``ExternalAgentMetadata`` so the orchestrator can select by
identity). A future change can replace any single adapter's
:func:`submit` with a real CLI/A2A call without affecting the rest
of the system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pi_platform.ports.a2a import (
    A2aTaskStatus,
    ExternalAgentMetadata,
    ExternalAgentPort,
    ReverseDelegationResult,
    ReverseDelegationTask,
)


__all__ = [
    "claude_code_metadata",
    "codex_metadata",
    "opencode_metadata",
    "hermes_metadata",
    "generic_mcp_metadata",
    "generic_a2a_metadata",
    "StaticAgentAdapter",
    "build_default_external_agent_registry",
]


_BASE_PROTOCOL_TAGS = ("reverse-delegation", "phase-10")


def _meta(
    *,
    identity: str,
    display_name: str,
    interface_kind: str,
    license_id: str,
    tags: Sequence[str] = (),
) -> ExternalAgentMetadata:
    return ExternalAgentMetadata(
        identity=identity,
        display_name=display_name,
        interface_kind=interface_kind,
        api_version="phase-10/1",
        license=license_id,
        transport_options={"stub": True},
        tags=tuple(_BASE_PROTOCOL_TAGS) + tuple(tags),
    )


def claude_code_metadata() -> ExternalAgentMetadata:
    """The Claude Code agent identity metadata."""
    return _meta(
        identity="claude-code",
        display_name="Claude Code",
        interface_kind="cli",
        license_id="Apache-2.0",
        tags=("agent", "claude-code"),
    )


def codex_metadata() -> ExternalAgentMetadata:
    """The Codex/ChatGPT agent identity metadata."""
    return _meta(
        identity="codex",
        display_name="Codex",
        interface_kind="api",
        license_id="Apache-2.0",
        tags=("agent", "codex"),
    )


def opencode_metadata() -> ExternalAgentMetadata:
    """The OpenCode agent identity metadata."""
    return _meta(
        identity="opencode",
        display_name="OpenCode",
        interface_kind="cli",
        license_id="MIT",
        tags=("agent", "opencode"),
    )


def hermes_metadata() -> ExternalAgentMetadata:
    """The Hermes remote agent identity metadata (stub)."""
    return _meta(
        identity="hermes",
        display_name="Hermes",
        interface_kind="api",
        license_id="Apache-2.0",
        tags=("agent", "hermes"),
    )


def generic_mcp_metadata() -> ExternalAgentMetadata:
    """The generic-MCP agent identity metadata."""
    return _meta(
        identity="generic-mcp",
        display_name="Generic MCP agent",
        interface_kind="mcp",
        license_id="Apache-2.0",
        tags=("agent", "mcp"),
    )


def generic_a2a_metadata() -> ExternalAgentMetadata:
    """The generic-A2A agent identity metadata."""
    return _meta(
        identity="generic-a2a",
        display_name="Generic A2A agent",
        interface_kind="a2a",
        license_id="Apache-2.0",
        tags=("agent", "a2a"),
    )


class StaticAgentAdapter(ExternalAgentPort):
    """Default deterministic :class:`ExternalAgentPort` implementation."""

    def __init__(
        self,
        metadata: ExternalAgentMetadata,
        *,
        supported_tasks: bool = True,
        response_factory=None,
    ) -> None:
        self._metadata = metadata
        self._supported = supported_tasks
        self._response_factory = response_factory

    def metadata(self) -> ExternalAgentMetadata:
        return self._metadata

    def submit(self, task: ReverseDelegationTask) -> ReverseDelegationResult:
        if not self._supported:
            return ReverseDelegationResult(
                task_id=task.task_id,
                status=A2aTaskStatus.UNSUPPORTED,
                error="external agent does not support outbound tasks in this build",
            )
        if self._response_factory is not None:
            output = self._response_factory(task)
            return ReverseDelegationResult(
                task_id=task.task_id,
                status=A2aTaskStatus.COMPLETED,
                output=output,
            )
        return ReverseDelegationResult(
            task_id=task.task_id,
            status=A2aTaskStatus.COMPLETED,
            output={
                "agentIdentity": self._metadata.identity,
                "taskContextKeys": list(task.bounded_context.keys()),
            },
        )

    def health(self) -> Mapping[str, Any]:
        return {"identity": self._metadata.identity, "supported": self._supported}


def build_default_external_agent_registry() -> dict[str, StaticAgentAdapter]:
    """Return the default mapping of agent identity → adapter.

    The mapping is stable across processes. Operators may edit the
    adapters through :class:`StaticAgentAdapter.__init__` flags.
    """
    return {
        claude_code_metadata().identity: StaticAgentAdapter(claude_code_metadata()),
        codex_metadata().identity: StaticAgentAdapter(codex_metadata()),
        opencode_metadata().identity: StaticAgentAdapter(opencode_metadata()),
        hermes_metadata().identity: StaticAgentAdapter(hermes_metadata(), supported_tasks=False),
        generic_mcp_metadata().identity: StaticAgentAdapter(generic_mcp_metadata()),
        generic_a2a_metadata().identity: StaticAgentAdapter(generic_a2a_metadata()),
    }
