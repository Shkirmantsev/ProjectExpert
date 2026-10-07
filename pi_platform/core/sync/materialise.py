"""Materialise service: write runtime changes back to canonical.

The service is approval-gated. By default it returns
``REQUIRE_APPROVAL`` and only proceeds when an explicit
``approval_token`` is supplied and :class:`PolicyDecisionStub`
returns ``ALLOW``. LOCAL_ONLY-sourced changes are always excluded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from ...adapters.fs import LocalFilesystemAdapter
from ...core.canonical import (
    KNOWN_FAMILIES,
    Manifest,
    RuntimeChange,
    Shard,
    canonical_dump_json,
    canonical_load_json,
    manifest_from_shards,
)
from ...core.licensing import LicenseGate
from ...ports import (
    ApprovalGrant,
    ApprovalRejected,
    ApprovalRequest,
    ApprovalRequired,
    MaterialisePort,
    MaterialiseReport,
    PolicyDecision,
    TrustedApprovalBoundary,
)
from .policy_stub import PolicyDecisionStub
from .trusted_approval import ClosedTrustedApprovalBoundary, deny_if_denied
from .wal import WriteAheadLog

__all__ = ["MaterialiseService", "LocalOnlySource"]


log = logging.getLogger(__name__)


class LocalOnlySource(RuntimeError):
    """Marker exception raised when a runtime change set contains only
    LOCAL_ONLY sources; in that case the materialise is a no-op
    rather than a failure so the operator pipeline is not disrupted.
    """

    def __init__(self, excluded: tuple[str, ...]):
        super().__init__(
            f"only LOCAL_ONLY sources in change set: {excluded!r}"
        )
        self.excluded = excluded


@dataclass(frozen=True)
class DiffEntry:
    path: str
    status: str  # "added" | "modified" | "deleted"


class MaterialiseService(MaterialisePort):
    """Default Phase 1 materialise service."""

    def __init__(self, *,
                 filesystem: Optional[LocalFilesystemAdapter] = None,
                 wal: Optional[WriteAheadLog] = None,
                 policy: Optional[PolicyDecisionStub] = None,
                 license_gate: Optional[LicenseGate] = None,
                 boundary: Optional[TrustedApprovalBoundary] = None):
        self.filesystem = filesystem
        self.wal = wal
        self.policy = policy or PolicyDecisionStub()
        self.license_gate = license_gate
        # Default to the closed boundary: every write fails closed
        # until the platform operator wires an HMAC-signed boundary.
        # Both ``project.materialize_knowledge`` and
        # ``project.refresh_sources`` MUST fail closed until the
        # boundary accepts a scoped, signed token.
        self.boundary = boundary or ClosedTrustedApprovalBoundary()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def materialise_durable_changes(self, repo_root: Path, *,
                                   cache_root: Path,
                                   approval_token: Optional[str] = None,
                                   changes: Optional[Iterable[RuntimeChange]] = None,
                                   ) -> MaterialiseReport:
        fs = self.filesystem or LocalFilesystemAdapter(repo_root,
                                                     cache_root=cache_root)
        wal = self.wal or WriteAheadLog(cache_root)
        changes = tuple(changes or ())

        # Trusted write boundary — must reject DENY unconditionally
        # and require a boundary-verified token for REQUIRE_APPROVAL.
        # The prior implementation only checked non-empty token presence
        # and skipped DENY entirely; the prerequisite fix closes both
        # gaps (v0.8 §48 supply-chain invariants).
        deny_if_denied(self.policy, "materialise")
        decision = self.policy.decide("materialise")

        if decision is PolicyDecision.REQUIRE_APPROVAL:
            grant = self._verify_approval(repo_root, changes, approval_token)
            log.info(
                "approval verified: action=materialise repo=%s issuer=%s "
                "exp=%s",
                str(repo_root), grant.issuer, grant.not_after,
            )

        durable = [c for c in changes if not _is_local_only(c)]
        excluded_local = tuple(c.id for c in changes if _is_local_only(c))

        durable = [c for c in changes if not _is_local_only(c)]
        excluded_local = tuple(c.id for c in changes if _is_local_only(c))
        if not durable:
            wal.commit()
            return MaterialiseReport(
                diff_files=(),
                excluded_local_only=excluded_local,
                policy_decision=decision,
                okf_validation_errors=(),
            )

        mid = wal.begin()
        try:
            wal.append("begin", {"id": mid, "count": len(durable)})
            diff = list(self._write_durable_changes(fs, durable))
            wal.append("write", {"diff": [d.path for d in diff]})

            if self.license_gate is not None:
                passed, findings = self.license_gate.run(_empty_dependencies())
                if not passed:
                    raise RuntimeError(
                        f"license gate blocked materialise: {findings!r}"
                    )
            wal.append("commit", {"id": mid})
            wal.commit()
        except Exception:
            wal.append("abort", {"id": mid})
            raise

        return MaterialiseReport(
            diff_files=tuple(diff),
            excluded_local_only=excluded_local,
            policy_decision=decision,
            okf_validation_errors=(),
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _verify_approval(self, repo_root: Path,
                         changes: Iterable[RuntimeChange],
                         approval_token: Optional[str]
                         ) -> ApprovalGrant:
        """Verify the supplied token against the trusted boundary.

        ``raise ApprovalRequired`` when the token is missing for a
        REQUIRE_APPROVAL action; raise :class:`ApprovalRejected` for
        any boundary failure (forged signature, wrong action, wrong
        repository, change-superset mismatch, expired window, missing
        operator key). ``LOCAL_ONLY`` exclusion still applies: a token
        that authorises ``change_ids={a,b,c}`` does not permit
        materialising change ``d`` alongside.
        """
        if approval_token is None or approval_token == "":
            raise ApprovalRequired(
                "materialise requires an explicit approval_token; the "
                "default policy decision is REQUIRE_APPROVAL"
            )
        request = ApprovalRequest(
            action="materialise",
            repo_root=str(repo_root.resolve()),
            change_ids=tuple(c.id for c in changes),
        )
        return self.boundary.verify(request, approval_token)

    def _write_durable_changes(self, fs: LocalFilesystemAdapter,
                               changes: Iterable[RuntimeChange]
                               ) -> Iterable[DiffEntry]:
        by_family: dict[str, list[Shard]] = {family: [] for family in KNOWN_FAMILIES}
        for change in changes:
            family = change.kind if change.kind in KNOWN_FAMILIES else "objects"
            payload_bytes = canonical_dump_json(dict(change.payload))
            shard_path = _payload_to_shard_path(change.payload, payload_bytes)
            shard = Shard(
                id=change.id,
                path=shard_path,
                contentHash=_hash_of_payload(payload_bytes),
                sourceHash=change.source.contentHash,
                count=1,
            )
            (fs.knowledge_root / shard_path).parent.mkdir(parents=True,
                                                          exist_ok=True)
            (fs.knowledge_root / shard_path).write_bytes(payload_bytes)
            by_family[family].append(shard)
            yield DiffEntry(path=shard_path, status="added")

        for family, shards in by_family.items():
            if not shards:
                continue
            existing = _read_manifest(fs, family)
            merged = _merge_shards(existing, shards)
            manifest = manifest_from_shards(family, merged)
            target = fs.knowledge_root / "manifests" / f"{family}-manifest.yaml"
            from ...core.canonical import save_manifest
            save_manifest(target, manifest)
            yield DiffEntry(path=str(target.relative_to(fs.repo_root)),
                            status="modified")


def _is_local_only(change: RuntimeChange) -> bool:
    meta = change.source.metadata
    return (meta.businessDomain or "").upper() == "LOCAL_ONLY"


def _payload_to_shard_path(payload: dict, payload_bytes: bytes) -> str:
    """Map a runtime change payload to its canonical shard path.

    The mapping mirrors §10: chunk payloads land under
    ``chunks/<source-family>/``, entity payloads under
    ``graph/nodes/<family>/``, relation payloads under
    ``graph/edges/<family>/`` and everything else under the
    ``objects/<hash-prefix[0:2]>/<hash-rest>.json`` content-addressed
    tree.
    """

    from ...core.canonical import content_address_bytes
    kind = payload.get("kind", "object")
    family = payload.get("family", kind)
    if kind == "chunk":
        return f"chunks/{family}/{payload['id']}.json"
    if kind == "entity":
        return f"graph/nodes/{family}/{payload['id']}.json"
    if kind == "relation":
        return f"graph/edges/{family}/{payload['sourceId']}__{payload['targetId']}.json"
    digest = content_address_bytes(payload_bytes)
    return f"objects/{digest[:2]}/{digest[2:]}.json"


def _hash_of_payload(payload_bytes: bytes) -> str:
    from ...core.canonical import content_address_bytes
    return content_address_bytes(payload_bytes)


def _read_manifest(fs: LocalFilesystemAdapter, family: str) -> Manifest:
    path = fs.knowledge_root / "manifests" / f"{family}-manifest.yaml"
    if not path.is_file():
        return Manifest(
            schemaVersion="0.1.0",
            family=family,
            shards=(),
            dependencies=(),
            contentHash=None,
        )
    from ...core.canonical import load_manifest
    return load_manifest(path)


def _merge_shards(existing: Manifest, new: list[Shard]) -> list[Shard]:
    seen: dict[str, Shard] = {s.id: s for s in existing.shards}
    for shard in new:
        seen[shard.id] = shard
    return list(seen.values())


def _empty_dependencies():
    return ()