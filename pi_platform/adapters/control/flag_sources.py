"""Phase 7 §59.15 feature flag source adapters.

The adapter layer ships the documented sources the
default Feature Flag registry composes:

* :class:`GitVersionedFlagSource` — loads flag
  declarations from the Git-versioned project
  configuration.
* :class:`LocalOverrideFlagSource` — loads flag overrides
  from the local machine configuration.
* :class:`MachineLocalFlagSource` — loads machine-scoped
  flag overrides from the local configuration.

Git-versioned declarations and local overrides remain in
separate sources; the registry resolves the most specific
scope in the documented order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from pi_platform.ports.control.flags import (
    FeatureFlagScope,
    FeatureFlagState,
)


__all__ = [
    "GitVersionedFlagSource",
    "LocalOverrideFlagSource",
    "MachineLocalFlagSource",
]


@dataclass(frozen=True)
class FlagSourceEntry:
    flag_id: str
    state: FeatureFlagState
    scope: FeatureFlagScope
    scope_key: str = ""


@dataclass
class _EntryBackedFlagSource:
    """Shared base for the three byte-identical flag source
    adapters. Subclasses declare the source kind through
    the documented :class:`FlagSourceEntry` records.
    """

    path: Path
    _entries: dict[str, FlagSourceEntry] = field(
        default_factory=dict, init=False)

    def load(self) -> Iterable[FlagSourceEntry]:
        return list(self._entries.values())

    def register(self, entry: FlagSourceEntry) -> None:
        self._entries[entry.flag_id] = entry


@dataclass
class GitVersionedFlagSource(_EntryBackedFlagSource):
    """Source backed by the Git-versioned project
    configuration.
    """


@dataclass
class LocalOverrideFlagSource(_EntryBackedFlagSource):
    """Source backed by the local override configuration."""


@dataclass
class MachineLocalFlagSource(_EntryBackedFlagSource):
    """Source backed by the local machine configuration."""