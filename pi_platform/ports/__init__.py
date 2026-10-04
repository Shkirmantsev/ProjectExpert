"""Port interfaces for the v0.8 Project Intelligence Platform.

The platform adopts the hexagonal/ports-and-adapters + micro-kernel
extension style required by §59 of the v0.8 architecture baseline.
The port modules in this file declare the abstract contracts every
Phase 1 capability exposes; adapters in :mod:`platform.adapters.*`
provide the default implementations and must not be imported from
:mod:`platform.core.*`.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

__all__ = [
    "GitPort",
    "GitPortError",
    "WorkingTreeChange",
    "WorkingTreeOverlayPort",
    "VersionIdentityPort",
    "VersionIdentity",
    "KnowledgeStateFilter",
    "HydratePort",
    "HydrateReport",
    "ReconcilePort",
    "ReconcileReport",
    "MaterialisePort",
    "MaterialiseReport",
    "PolicyDecision",
    "PolicyDecisionPort",
    "ApprovalRequired",
    "LicensePolicy",
    "LicenseGateFinding",
    "LicenseGatePort",
    "Dependency",
    "DependencyInventoryPort",
    "ModelLicense",
    "ModelLicenseInventoryPort",
]


# ---------------------------------------------------------------------------
# Git ports
# ---------------------------------------------------------------------------


class GitPortError(RuntimeError):
    """Raised when the Git adapter cannot satisfy a request."""


class GitPort(abc.ABC):
    """Abstract Git port.

    Phase 1 ships :class:`platform.adapters.git.cli_adapter.GitCliAdapter`
    as the default adapter. libgit2 support is added in Phase 2.
    """

    @abc.abstractmethod
    def head(self, repo_root: Path) -> str: ...

    @abc.abstractmethod
    def current_branch(self, repo_root: Path) -> Optional[str]: ...

    @abc.abstractmethod
    def status(self, repo_root: Path) -> Sequence["WorkingTreeChange"]: ...

    @abc.abstractmethod
    def lfs_pointer_for(self, repo_root: Path, path: Path) -> Optional[str]: ...


@dataclass(frozen=True)
class WorkingTreeChange:
    path: Path
    kind: str  # "modified" | "added" | "deleted" | "untracked" | "renamed"

    def as_dict(self) -> dict:
        return {"path": str(self.path), "kind": self.kind}


class WorkingTreeOverlayPort(abc.ABC):
    """Compute a deterministic overlay of the working-tree state."""

    @abc.abstractmethod
    def compute(self, repo_root: Path) -> bytes: ...


@dataclass(frozen=True)
class VersionIdentity:
    gitHead: str
    workingTreeFingerprint: str
    knowledgeSchemaVersion: str
    embeddingModelVersion: str
    indexSchemaVersion: str


class VersionIdentityPort(abc.ABC):
    """Resolve the structured runtime project version identity."""

    @abc.abstractmethod
    def compute(self, repo_root: Path, *,
                working_tree_fingerprint: str,
                knowledge_schema_version: str,
                index_schema_version: str) -> VersionIdentity: ...


# ---------------------------------------------------------------------------
# Sync ports
# ---------------------------------------------------------------------------


class KnowledgeStateFilter(enum.Enum):
    """Filter set used by sync services when reporting durable facts."""

    ALL = "all"
    DURABLE = "durable"  # exclude LOCAL_ONLY
    STALE = "stale"


@dataclass(frozen=True)
class HydrateReport:
    project_version: VersionIdentity
    families: Mapping[str, int]
    cache_hit_rates: Mapping[str, float]
    stale_fact_ids: tuple = ()


class HydratePort(abc.ABC):
    @abc.abstractmethod
    def restore_runtime(self, repo_root: Path, *,
                        cache_root: Path) -> HydrateReport: ...


@dataclass(frozen=True)
class ReconcileReport:
    families: Mapping[str, int]
    reused_shards: Mapping[str, int]
    re_ingested_shards: Mapping[str, int]
    stale_fact_ids: tuple = ()


class ReconcilePort(abc.ABC):
    @abc.abstractmethod
    def reconcile_branch_switch(self, repo_root: Path, *,
                                previous_head: str,
                                current_head: str,
                                cache_root: Path) -> ReconcileReport: ...


@dataclass(frozen=True)
class MaterialiseReport:
    diff_files: tuple
    excluded_local_only: tuple
    policy_decision: "PolicyDecision"
    okf_validation_errors: tuple = ()


class MaterialisePort(abc.ABC):
    @abc.abstractmethod
    def materialise_durable_changes(self, repo_root: Path, *,
                                   cache_root: Path,
                                   approval_token: Optional[str] = None,
                                   changes: Optional[Sequence] = None,
                                   ) -> MaterialiseReport: ...


# ---------------------------------------------------------------------------
# Policy ports (Phase 1 stub only)
# ---------------------------------------------------------------------------


class PolicyDecision(enum.Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PolicyDecisionPort(abc.ABC):
    @abc.abstractmethod
    def decide(self, action: str, target: Optional[str] = None) -> PolicyDecision: ...


class ApprovalRequired(RuntimeError):
    """Raised by :class:`MaterialisePort` when an approval token is
    required but not supplied."""


# ---------------------------------------------------------------------------
# Licensing ports
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Dependency:
    name: str
    version: str
    spdx: Optional[str] = None  # SPDX identifier; None ⇒ unknown
    source: Optional[str] = None
    scope: str = "runtime"  # "runtime" | "build" | "system" | "model"


@dataclass(frozen=True)
class LicenseGateFinding:
    dependency: Dependency
    decision: str  # "allow" | "review" | "deny"
    reason: str


class LicensePolicy(abc.ABC):
    @abc.abstractmethod
    def evaluate(self, dependency: Dependency) -> str: ...


class LicenseGatePort(abc.ABC):
    @abc.abstractmethod
    def run(self, dependencies: Iterable[Dependency]) -> tuple[bool, list[LicenseGateFinding]]: ...


class DependencyInventoryPort(abc.ABC):
    @abc.abstractmethod
    def load(self, path: Path) -> list[Dependency]: ...


@dataclass(frozen=True)
class ModelLicense:
    name: str
    version: str
    spdx: Optional[str]
    source: Optional[str] = None


class ModelLicenseInventoryPort(abc.ABC):
    @abc.abstractmethod
    def load(self, path: Path) -> list[ModelLicense]: ...