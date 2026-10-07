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
    "KnowledgeReadinessPort",
    "ReadinessSnapshot",
    "RuntimeNotReadyError",
    "MaterialisePort",
    "MaterialiseReport",
    "PolicyDecision",
    "PolicyDecisionPort",
    "ApprovalRequired",
    "ApprovalRequest",
    "ApprovalGrant",
    "ApprovalRejected",
    "TrustedApprovalBoundary",
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
class ReadinessSnapshot:
    """A bounded snapshot of the runtime readiness state.

    ``consistent`` is True only when the most recent
    hydrate/reconcile cycle succeeded AND no in-progress refresh
    is pending. ``current_head`` and ``working_tree_fingerprint``
    identify the runtime project version the snapshot describes;
    mismatched heads between snapshot and caller indicate a
    cross-version evidence attempt that the gate rejects.
    """

    consistent: bool
    current_head: str = ""
    working_tree_fingerprint: str = ""
    last_hydrate_at: int = 0       # unix seconds
    last_reconcile_at: int = 0
    reason: str = ""               # "" when consistent; else short reason
    in_progress: bool = False      # True while a refresh is mid-flight


class KnowledgeReadinessPort(abc.ABC):
    """Phase 6 prerequisite 3 — readiness gate.

    The port is the trusted single source of truth the MCP server
    (and any other tool serving project knowledge) consults before
    returning evidence. ``is_ready()`` returns True only when the
    latest hydrate / reconcile cycle is consistent. Any
    inconsistent snapshot MUST be rejected with a typed
    :class:`RuntimeNotReadyError` rather than served, even
    partially.
    """

    @abc.abstractmethod
    def snapshot(self) -> ReadinessSnapshot: ...

    @abc.abstractmethod
    def is_ready(self) -> bool: ...

    @abc.abstractmethod
    def record_hydrate(self, report: HydrateReport) -> None: ...

    @abc.abstractmethod
    def record_reconcile(self, report: ReconcileReport,
                         *, current_head: str,
                         working_tree_fingerprint: str) -> None: ...

    @abc.abstractmethod
    def record_failure(self, reason: str) -> None: ...

    @abc.abstractmethod
    def begin_refresh(self) -> None:
        """Mark a refresh as in progress; consumers see
        ``in_progress=True`` and the gate is NOT ready."""

    @abc.abstractmethod
    def end_refresh(self) -> None:
        """Mark the in-progress refresh as complete."""


class RuntimeNotReadyError(RuntimeError):
    """Raised by :class:`KnowledgeReadinessPort` consumers (the
    Phase 6 MCP server) when project knowledge cannot be served
    because the runtime is not in a consistent state.
    """

    def __init__(self, snapshot: ReadinessSnapshot):
        self.snapshot = snapshot
        reason = snapshot.reason or "runtime not ready"
        super().__init__(
            f"runtime not ready: {reason} "
            f"(consistent={snapshot.consistent} "
            f"in_progress={snapshot.in_progress})"
        )


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
# Trusted approval boundary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalRequest:
    """Scoped, time-bounded approval envelope presented for verification.

    The boundary uses this envelope to decide whether a caller-supplied
    token authorizes a specific write action against a specific
    repository and an explicit (possibly empty) set of change ids.
    """

    action: str           # "materialise" | "refresh_sources" | …
    repo_root: str        # canonical path of the target repository
    change_ids: tuple = ()  # allowed change ids; subset relation vs grant
    issued_at: int = 0    # unix seconds; 0 ⇒ unset (boundary stamps)


@dataclass(frozen=True)
class ApprovalGrant:
    """A verified, scope-matched approval token."""

    request: ApprovalRequest
    not_before: int  # unix seconds
    not_after: int   # unix seconds
    issuer: str      # operator id that issued the grant


class ApprovalRejected(RuntimeError):
    """Raised when an approval token is rejected by the boundary.

    The :attr:`reason` attribute holds one of the documented reason
    codes (see :class:`TrustedApprovalBoundary`).
    """

    REASONS = (
        "missing_token",
        "policy_denied",
        "forged_signature",
        "expired",
        "not_yet_valid",
        "wrong_action",
        "wrong_repository",
        "change_superset_mismatch",
        "malformed_token",
        "no_issuer_key",
    )

    def __init__(self, reason: str, message: str = ""):
        if reason not in self.REASONS:
            raise ValueError(
                f"unknown ApprovalRejected reason: {reason!r}; "
                f"allowed: {self.REASONS!r}"
            )
        super().__init__(message or reason)
        self.reason = reason


class TrustedApprovalBoundary(abc.ABC):
    """Issue and verify scoped, time-bounded approval tokens.

    The boundary owns an operator signing key. Tokens are issued by
    the boundary itself (or by an external operator process that
    holds the key) — never caller-supplied. Every verify() call
    enforces:

    * authenticity (HMAC signature against the operator key);
    * action match (token bound to the requested action);
    * repository match (token bound to the canonical repo path);
    * change-id scope (token change ids must be a subset of grant);
    * validity window (issued ≤ now < expires);
    * policy :data:`PolicyDecision.DENY` rejection.

    Any violation raises :class:`ApprovalRejected` with a typed
    reason. The boundary fails closed by default.
    """

    @abc.abstractmethod
    def issue(self, request: ApprovalRequest, *, ttl_seconds: int = 300,
              issuer: str = "operator") -> str: ...

    @abc.abstractmethod
    def verify(self, request: ApprovalRequest, token: Optional[str]
               ) -> ApprovalGrant: ...


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