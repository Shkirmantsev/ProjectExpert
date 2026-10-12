"""UI adapters (architecture §57).

Adapters only: HTTP transport, composition and the optional Open WebUI shim.
Domain behaviour lives in :mod:`pi_platform.core.ui`.
"""

from __future__ import annotations

from .composition import (
    OPEN_WEBUI_FLAG,
    CacheBackedHybridRetrieval,
    RetrievalOnlyOrchestrator,
    build_flag_registry,
    build_ui_service,
    is_open_webui_enabled,
)
from .http_server import DEFAULT_HOST, STATIC_ROOT, UiHttpServer
from .openai_compat import OpenAiCompatShim

__all__ = [
    "UiHttpServer",
    "DEFAULT_HOST",
    "STATIC_ROOT",
    "OpenAiCompatShim",
    "build_ui_service",
    "build_flag_registry",
    "is_open_webui_enabled",
    "RetrievalOnlyOrchestrator",
    "CacheBackedHybridRetrieval",
    "OPEN_WEBUI_FLAG",
]