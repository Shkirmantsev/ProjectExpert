"""Phase 10 evaluation scenario base classes.

A :class:`Scenario` is the smallest unit exercised by a Phase 10
quality-gates test class. Each scenario records its outcome against
the shared :class:`pi_platform.core.eval.metrics.EvalMetrics` and
returns a :class:`ScenarioOutcome` value the test asserts on.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


from .metrics import EvalMetrics, EvalReport, collect


@dataclass
class ScenarioContext:
    """Per-scenario inputs shared with the metrics collector."""

    workspace: Path
    metrics: EvalMetrics
    correlation_id: str
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioOutcome:
    """Structured scenario outcome asserted by the test."""

    name: str
    passed: bool
    duration_ms: int
    failure_reason: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "durationMs": self.duration_ms,
            "failureReason": self.failure_reason,
        }


class Scenario(abc.ABC):
    """Abstract scenario base class."""

    name: str = ""

    @abc.abstractmethod
    def run(self, context: ScenarioContext) -> ScenarioOutcome:
        """Execute the scenario; implementations update ``context.metrics``."""


@dataclass
class StubCodingAgent:
    """Deterministic stub coding agent used by the retrieval-first and
    MCP tool-selection scenarios.

    The stub records tool calls. The suites assert the recorded call
    order and that no source-file scan happened before the first MCP
    retrieval tool.
    """

    identifier: str
    tool_calls: list[dict] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def call_tool(self, name: str, **kwargs: Any) -> dict:
        record = {"name": name, "args": dict(kwargs)}
        self.tool_calls.append(record)
        return record

    def read_file(self, path: str) -> None:
        self.files_read.append(path)

    def decide_with_existing_tools(self, *, question: str, allowed_tools: Sequence[str]) -> str:
        """Choose the first allowed retrieval tool to assert on order.

        The documented retrieval-first escalation order from §33 is
        ``exact lookup → sparse → dense → hybrid → graph → rerank``.
        We therefore prefer ``find_implementation`` (exact symbol
        lookup) when the question names a known identifier, and
        fall through to ``retrieve_context`` for free-form questions.
        """
        # Heuristic: an identifier is anything containing an uppercase
        # letter or an underscore. The stub does not actually parse
        # the question, but the priority below mirrors the spec.
        is_identifier = any(c.isupper() for c in question) or "_" in question
        priority = (
            ("find_implementation", "trace_requirement", "find_references", "get_entity")
            if is_identifier
            else ("retrieve_context", "search")
        )
        for needle in priority:
            for tool in allowed_tools:
                if tool.endswith(needle) or needle in tool:
                    self.call_tool(tool, query=question)
                    return tool
        for tool in allowed_tools:
            if "retrieve" in tool or "search" in tool:
                self.call_tool(tool, query=question)
                return tool
        return ""

    def reset(self) -> None:
        self.tool_calls.clear()
        self.files_read.clear()
        self.notes.clear()


def measure_ms(callable_: Callable[[], Any]) -> tuple[int, Any]:
    """Run ``callable_`` and return ``(duration_ms, result)``."""
    t0 = time.monotonic_ns()
    try:
        result = callable_()
    finally:
        dt_ns = time.monotonic_ns() - t0
    return (dt_ns // 1_000_000, result)
