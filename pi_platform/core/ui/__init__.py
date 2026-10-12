"""UI domain modules (architecture §57)."""

from __future__ import annotations

from .rest_service import (
    OPERATION_CAPABILITIES,
    RestService,
    UiContext,
    UiOperationDenied,
)

__all__ = [
    "OPERATION_CAPABILITIES",
    "RestService",
    "UiContext",
    "UiOperationDenied",
]