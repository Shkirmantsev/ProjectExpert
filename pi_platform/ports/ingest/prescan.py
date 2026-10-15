"""PDF prescan port (E2)."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Dict, Optional


__all__ = [
    "PrescanResult",
    "PrescanPort",
    "PrescanError",
    "DEFAULT_PRESCAN_STRATEGY_VERSION",
]


DEFAULT_PRESCAN_STRATEGY_VERSION = "prescan/v1"


class PrescanError(RuntimeError):
    """Raised when the prescan cannot read the file."""


@dataclass(frozen=True)
class PrescanResult:
    """Cheap, byte-only precheck of a PDF (or any binary) file.

    The prescan NEVER opens the PDF parser; it samples headers,
    trailing trailer info, and a small slice of the body to
    decide whether the file is worth the heavy parse and whether
    it has a usable native text layer.
    """

    page_count: int
    metadata: Dict[str, str] = field(default_factory=dict)
    has_native_text: bool = False
    sample_text_chars: int = 0
    byte_hash: str = ""
    strategy_version: str = DEFAULT_PRESCAN_STRATEGY_VERSION
    file_size: int = 0


class PrescanPort(abc.ABC):
    """Adapter contract: a cheap, byte-only precheck of a file."""

    @abc.abstractmethod
    def scan(self, source_path: str) -> PrescanResult: ...
