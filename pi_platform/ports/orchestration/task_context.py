"""Task context builder port for the v0.8 Phase 5
orchestration layer.

Covers architecture section §52 (Task Context Bundles). The
:class:`TaskContextBuilderPort` builds the bounded ephemeral
:class:`TaskContextBundle` that the Phase 5
:class:`QueryOrchestratorPort` emits at L2 and that the
Phase 6 MCP server forwards to external strong agents.

The bundle is an ephemeral transport artifact, NOT canonical
knowledge. The bundle aggregates the requirement, the
relevant OpenSpec, the Wiki sections, the source code, the
interfaces, the dependencies, the architecture constraints,
the graph neighbourhood, the tests and the Git diff for
the bounded context the agent receives.
"""

from __future__ import annotations

import abc
import hashlib
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence


__all__ = [
    "RequirementSlot",
    "OpenSpecSlot",
    "WikiSlot",
    "CodeSlot",
    "InterfaceSlot",
    "DependencySlot",
    "ArchitectureSlot",
    "EntitySlot",
    "TestSlot",
    "DiffSlot",
    "TaskContextBundle",
    "TaskContextBuilderError",
    "TaskContextBuilderPort",
    "BUNDLE_SLOT_PRIORITY",
]


class TaskContextBuilderError(RuntimeError):
    """Raised when the task context builder cannot build a bundle."""


# §52 priority: requirement > openSpec > tests > source code >
# interfaces > dependencies > architecture > graph > wiki > diff.
BUNDLE_SLOT_PRIORITY: tuple[str, ...] = (
    "requirement",
    "openSpec",
    "tests",
    "sourceCode",
    "interfaces",
    "dependencies",
    "architectureConstraints",
    "graphNeighbourhood",
    "wikiSections",
    "gitDiff",
)


@dataclass(frozen=True)
class RequirementSlot:
    identifier: str
    title: str = ""
    sourcePath: str = ""
    contentHash: str = ""


@dataclass(frozen=True)
class OpenSpecSlot:
    capabilityId: str
    specPath: str = ""
    rationale: str = ""


@dataclass(frozen=True)
class WikiSlot:
    title: str
    path: str = ""
    summary: str = ""


@dataclass(frozen=True)
class CodeSlot:
    filePath: str
    symbol: str = ""
    lineStart: int = 0
    lineEnd: int = 0
    snippet: str = ""


@dataclass(frozen=True)
class InterfaceSlot:
    name: str
    kind: str = ""
    path: str = ""


@dataclass(frozen=True)
class DependencySlot:
    name: str
    version: str = ""
    license: str = ""


@dataclass(frozen=True)
class ArchitectureSlot:
    constraint: str
    adrPath: str = ""


@dataclass(frozen=True)
class EntitySlot:
    entityId: str
    family: str = ""
    label: str = ""


@dataclass(frozen=True)
class TestSlot:
    name: str
    path: str = ""


@dataclass(frozen=True)
class DiffSlot:
    filePath: str
    diff: str = ""


@dataclass(frozen=True)
class TaskContextBundle:
    """§52 bounded task context bundle."""

    taskId: str
    goal: str
    budgetTokens: int
    requirement: Optional[RequirementSlot] = None
    openSpec: Sequence[OpenSpecSlot] = field(default_factory=tuple)
    wikiSections: Sequence[WikiSlot] = field(default_factory=tuple)
    sourceCode: Sequence[CodeSlot] = field(default_factory=tuple)
    interfaces: Sequence[InterfaceSlot] = field(default_factory=tuple)
    dependencies: Sequence[DependencySlot] = field(default_factory=tuple)
    architectureConstraints: Sequence[ArchitectureSlot] = field(default_factory=tuple)
    graphNeighbourhood: Sequence[EntitySlot] = field(default_factory=tuple)
    tests: Sequence[TestSlot] = field(default_factory=tuple)
    gitDiff: Sequence[DiffSlot] = field(default_factory=tuple)
    droppedSlots: Sequence[tuple[str, str]] = field(default_factory=tuple)
    explanations: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.budgetTokens <= 0:
            raise TaskContextBuilderError(
                f"budgetTokens must be positive, got {self.budgetTokens}"
            )
        if not self.taskId:
            raise TaskContextBuilderError("taskId must be a non-empty string")


class TaskContextBuilderPort(abc.ABC):
    """Abstract task context builder port."""

    @abc.abstractmethod
    def build(
        self, goal: str, *, budget_tokens: int = 4000,
        project_version: object = None,
        retrieval: object = None,
    ) -> TaskContextBundle: ...

    @abc.abstractmethod
    def validate(self, bundle: TaskContextBundle) -> Sequence[str]: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...


def _stable_task_id(goal: str, budget_tokens: int) -> str:
    digest = hashlib.blake2b(
        f"{goal}|{budget_tokens}".encode("utf-8"), digest_size=16,
    ).hexdigest()
    return f"task-{digest[:24]}"