"""Default task context builder core.

Implements :class:`pi_platform.ports.orchestration.task_context.TaskContextBuilderPort`
with the bounded §52 task context bundle shape. The core
consumes a Phase 4 `MultiStageRetrievalResult` and emits a
`TaskContextBundle` whose cumulative token estimate is bounded
by the `budget_tokens` argument.

The builder applies the documented §52 slot priority
ordering (requirement > openSpec > tests > source code >
interfaces > dependencies > architecture > graph > wiki >
diff) when truncating lower-priority slots to honour the
budget.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Mapping, Sequence

from pi_platform.ports.orchestration.task_context import (
    BUNDLE_SLOT_PRIORITY,
    ArchitectureSlot,
    CodeSlot,
    DependencySlot,
    DiffSlot,
    EntitySlot,
    InterfaceSlot,
    OpenSpecSlot,
    RequirementSlot,
    TaskContextBuilderError,
    TaskContextBuilderPort,
    TaskContextBundle,
    TestSlot,
    WikiSlot,
    _stable_task_id,
)


__all__ = [
    "DefaultTaskContextBuilder",
    "DEFAULT_PROJECT_VERSION",
    "DEFAULT_OKF_VERSION",
    "REQUIREMENT_PATTERN",
    "OPENSPEC_PATTERN",
]


DEFAULT_PROJECT_VERSION = "0.1.0"
DEFAULT_OKF_VERSION = "0.2"

# A conservative requirement / OpenSpec identifier pattern. The
# regex matches the §21 / §17 canonical identifier shapes the
# Phase 1 / Phase 2 / Phase 3 subsystems emit.
REQUIREMENT_PATTERN = re.compile(r"\b(REQ|GEN|ILO|PSF|FPA|FIN)-\d+(?:\.\d+)*\b")
OPENSPEC_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}-[a-z][a-z0-9-]*\b")


def _token_estimate(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text.split()))


class DefaultTaskContextBuilder(TaskContextBuilderPort):
    """Default §52 task context builder."""

    def __init__(
        self, *, knowledge_schema_version: str = DEFAULT_PROJECT_VERSION,
        okf_versions: Sequence[str] = (DEFAULT_OKF_VERSION,),
    ) -> None:
        self._knowledge_schema_version = knowledge_schema_version
        self._okf_versions = tuple(okf_versions)
        self._calls = 0
        self._dropped = 0
        self._slot_counts: Counter[str] = Counter()

    def build(
        self, goal: str, *, budget_tokens: int = 4000,
        project_version: object = None,
        retrieval: object = None,
    ) -> TaskContextBundle:
        self._calls += 1
        task_id = _stable_task_id(goal, budget_tokens)
        requirement = self._extract_requirement(goal)
        openspec_slots = self._extract_openspec(goal)
        graph_slots = self._extract_graph(retrieval)
        test_slots = self._extract_tests(retrieval)
        code_slots = self._extract_source(retrieval)
        interface_slots = self._extract_interfaces(retrieval)
        dependency_slots = self._extract_dependencies(retrieval)
        architecture_slots = self._extract_architecture(retrieval)
        wiki_slots = self._extract_wiki(retrieval)
        diff_slots = self._extract_diff(retrieval)

        # Compute per-slot token estimates and truncate per the
        # documented §52 priority ordering.
        slot_data: dict[str, tuple[Sequence[object], int]] = {
            "requirement": (
                [requirement] if requirement is not None else [],
                _token_estimate(self._requirement_text(requirement))
                if requirement is not None else 0,
            ),
            "openSpec": (openspec_slots, sum(
                _token_estimate(s.rationale or s.capabilityId)
                for s in openspec_slots
            )),
            "tests": (test_slots, sum(
                _token_estimate(s.name + " " + s.path)
                for s in test_slots
            )),
            "sourceCode": (code_slots, sum(
                _token_estimate((s.snippet or "") + " " + s.filePath)
                for s in code_slots
            )),
            "interfaces": (interface_slots, sum(
                _token_estimate(s.name + " " + s.path)
                for s in interface_slots
            )),
            "dependencies": (dependency_slots, sum(
                _token_estimate(s.name + " " + s.version)
                for s in dependency_slots
            )),
            "architectureConstraints": (architecture_slots, sum(
                _token_estimate(s.constraint) for s in architecture_slots
            )),
            "graphNeighbourhood": (graph_slots, sum(
                _token_estimate(s.entityId + " " + s.label)
                for s in graph_slots
            )),
            "wikiSections": (wiki_slots, sum(
                _token_estimate(s.title + " " + s.summary)
                for s in wiki_slots
            )),
            "gitDiff": (diff_slots, sum(
                _token_estimate(s.diff) for s in diff_slots
            )),
        }
        kept: dict[str, Sequence[object]] = {}
        dropped: list[tuple[str, str]] = []
        remaining = budget_tokens
        for slot_name in BUNDLE_SLOT_PRIORITY:
            value, cost = slot_data[slot_name]
            if not value:
                continue
            if cost <= remaining:
                kept[slot_name] = list(value)
                remaining -= cost
            else:
                # Slot too large; drop entirely.
                dropped.append((slot_name, "budget_exhausted"))
                self._dropped += 1

        explanations = (
            f"goal={goal!r}",
            f"budget_tokens={budget_tokens}",
            f"task_id={task_id}",
            f"knowledge_schema_version={self._knowledge_schema_version}",
            f"okf_versions={list(self._okf_versions)}",
            f"kept_slots={sorted(kept.keys())}",
            f"dropped_slots={[name for name, _ in dropped]}",
        )
        bundle = TaskContextBundle(
            taskId=task_id,
            goal=goal,
            budgetTokens=budget_tokens,
            requirement=kept.get("requirement", [None])[0]
            if "requirement" in kept else None,
            openSpec=tuple(kept.get("openSpec", [])),
            tests=tuple(kept.get("tests", [])),
            sourceCode=tuple(kept.get("sourceCode", [])),
            interfaces=tuple(kept.get("interfaces", [])),
            dependencies=tuple(kept.get("dependencies", [])),
            architectureConstraints=tuple(
                kept.get("architectureConstraints", []),
            ),
            graphNeighbourhood=tuple(kept.get("graphNeighbourhood", [])),
            wikiSections=tuple(kept.get("wikiSections", [])),
            gitDiff=tuple(kept.get("gitDiff", [])),
            droppedSlots=tuple(dropped),
            explanations=explanations,
        )
        for name, _ in dropped:
            self._slot_counts[name] += 1
        for name in kept:
            self._slot_counts[name] += 1
        return bundle

    def validate(self, bundle: TaskContextBundle) -> Sequence[str]:
        problems: list[str] = []
        if not bundle.taskId:
            problems.append("taskId is empty")
        if bundle.budgetTokens <= 0:
            problems.append("budgetTokens must be positive")
        return tuple(problems)

    def stats(self) -> Mapping[str, int]:
        base = {
            "calls": self._calls,
            "dropped": self._dropped,
        }
        base.update(dict(self._slot_counts))
        return base

    # -- internal extractors --------------------------------------------

    def _extract_requirement(self, goal: str) -> RequirementSlot | None:
        match = REQUIREMENT_PATTERN.search(goal or "")
        if not match:
            return None
        identifier = match.group(0)
        return RequirementSlot(
            identifier=identifier, title=identifier, sourcePath="",
        )

    def _extract_openspec(self, goal: str) -> list[OpenSpecSlot]:
        slots: list[OpenSpecSlot] = []
        for match in OPENSPEC_PATTERN.finditer(goal or ""):
            capability_id = match.group(0)
            slots.append(OpenSpecSlot(
                capabilityId=capability_id,
                specPath=f"openspec/specs/{capability_id}/spec.md",
            ))
        return slots

    def _extract_graph(self, retrieval: object) -> list[EntitySlot]:
        if retrieval is None:
            return []
        expansion = getattr(retrieval, "graphExpansion", None)
        if expansion is None:
            return []
        return [
            EntitySlot(
                entityId=getattr(entity, "id", str(entity)),
                family=getattr(entity, "family", ""),
                label=getattr(entity, "label", ""),
            )
            for entity in getattr(expansion, "expandedEntities", [])
        ]

    def _extract_tests(self, retrieval: object) -> list[TestSlot]:
        if retrieval is None:
            return []
        candidates = getattr(retrieval, "hits", [])
        out: list[TestSlot] = []
        for hit in candidates:
            md = getattr(hit, "metadata", None)
            if md is not None and getattr(md, "family", "") == "Test":
                out.append(TestSlot(
                    name=getattr(hit, "chunkId", ""),
                    path=getattr(md, "sourcePath", ""),
                ))
        return out

    def _extract_source(self, retrieval: object) -> list[CodeSlot]:
        if retrieval is None:
            return []
        out: list[CodeSlot] = []
        for hit in getattr(retrieval, "hits", []):
            md = getattr(hit, "metadata", None)
            if md is not None and getattr(md, "className", None):
                out.append(CodeSlot(
                    filePath=getattr(md, "sourcePath", ""),
                    symbol=getattr(md, "className", ""),
                    snippet=getattr(hit, "snippet", "")[:200],
                ))
        return out

    def _extract_interfaces(self, retrieval: object) -> list[InterfaceSlot]:
        if retrieval is None:
            return []
        out: list[InterfaceSlot] = []
        for hit in getattr(retrieval, "hits", []):
            md = getattr(hit, "metadata", None)
            if md is not None and getattr(md, "family", "") == "Interface":
                out.append(InterfaceSlot(
                    name=getattr(hit, "chunkId", ""),
                    kind="interface",
                    path=getattr(md, "sourcePath", ""),
                ))
        return out

    def _extract_dependencies(self, retrieval: object) -> list[DependencySlot]:
        if retrieval is None:
            return []
        out: list[DependencySlot] = []
        for hit in getattr(retrieval, "hits", []):
            md = getattr(hit, "metadata", None)
            if md is not None and getattr(md, "family", "") == "Dependency":
                out.append(DependencySlot(
                    name=getattr(hit, "chunkId", ""),
                    version="",
                    license="",
                ))
        return out

    def _extract_architecture(self, retrieval: object) -> list[ArchitectureSlot]:
        if retrieval is None:
            return []
        out: list[ArchitectureSlot] = []
        for hit in getattr(retrieval, "hits", []):
            md = getattr(hit, "metadata", None)
            if md is not None and getattr(md, "family", "") == "ADR":
                out.append(ArchitectureSlot(
                    constraint=getattr(hit, "chunkId", ""),
                    adrPath=getattr(md, "sourcePath", ""),
                ))
        return out

    def _extract_wiki(self, retrieval: object) -> list[WikiSlot]:
        if retrieval is None:
            return []
        out: list[WikiSlot] = []
        for hit in getattr(retrieval, "hits", []):
            md = getattr(hit, "metadata", None)
            if md is not None and getattr(md, "family", "") == "DocumentationSource":
                out.append(WikiSlot(
                    title=getattr(hit, "chunkId", ""),
                    path=getattr(md, "sourcePath", ""),
                    summary=getattr(hit, "snippet", "")[:200],
                ))
        return out

    def _extract_diff(self, retrieval: object) -> list[DiffSlot]:
        # Git diff is not produced from the retrieval result; the
        # orchestrator wires this in via project_version when the
        # future Git-bound diff API lands.
        return []

    @staticmethod
    def _requirement_text(req: RequirementSlot | None) -> str:
        if req is None:
            return ""
        return " ".join([req.identifier, req.title, req.sourcePath])


def _stable_id(parts: Sequence[str]) -> str:
    digest = hashlib.blake2b(
        "|".join(parts).encode("utf-8"), digest_size=16,
    ).hexdigest()
    return digest[:24]