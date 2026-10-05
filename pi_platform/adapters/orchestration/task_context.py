"""Default task context builder adapter.

Wraps :class:`pi_platform.core.orchestration.task_context.DefaultTaskContextBuilder`
as a thin adapter so the registry / CLI can introspect the
same shape across the default and alternative builders.
"""

from __future__ import annotations

from pi_platform.core.orchestration.task_context import (
    DEFAULT_OKF_VERSION,
    DEFAULT_PROJECT_VERSION,
    DefaultTaskContextBuilder,
)


__all__ = [
    "DefaultTaskContextBuilderAdapter",
    "ADAPTER_NAME",
]


ADAPTER_NAME = "task-context-default"


class DefaultTaskContextBuilderAdapter(DefaultTaskContextBuilder):
    """Default §52 task context builder adapter."""

    def __init__(
        self, *,
        knowledge_schema_version: str = DEFAULT_PROJECT_VERSION,
        okf_versions: tuple[str, ...] = (DEFAULT_OKF_VERSION,),
    ) -> None:
        super().__init__(
            knowledge_schema_version=knowledge_schema_version,
            okf_versions=okf_versions,
        )
        self._name = ADAPTER_NAME

    @property
    def backend_name(self) -> str:
        return self._name