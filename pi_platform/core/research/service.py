"""The shared dependency research service.

One service serves every transport. It owns:

* the ecosystem adapter registry;
* the bounded graph traversal;
* the snapshot-bound cursors;
* the truthful status and completeness of every answer.

The service never guesses. A lock format it cannot read, a parser it
does not have and a dependency it cannot resolve are reported as
warnings with an explicit status, never as an empty success.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.research.graph import DependencyGraph, traverse
from pi_platform.core.research.policy import AcquisitionPolicy, ResearchLimits
from pi_platform.core.research.records import (
    Completeness,
    EcosystemSnapshot,
    InvalidResearchRequest,
    ResearchDenied,
    ResearchResult,
    ResearchStatus,
    ResearchUnsupported,
    StaleResearchCursor,
)
from pi_platform.ports.research.dependency_research import (
    DependencyAcquireRequest,
    DependencyReadRequest,
    DependencyResearchPort,
    DependencySearchRequest,
    DependencyTreeRequest,
)
from pi_platform.ports.research.ecosystem import EcosystemResearchPort

__all__ = ["DependencyResearchService", "ResearchCursor"]


@dataclass(frozen=True)
class ResearchCursor:
    """A continuation token of a truncated traversal.

    The cursor is bound to the snapshot, the query and the policy. A
    cursor from another snapshot, another query, another policy or
    another project is rejected instead of silently continuing the
    wrong traversal.
    """

    snapshot_id: str
    query: str
    policy: str
    project: str
    offset: int = 0

    def encode(self) -> str:
        payload = json.dumps({
            "snapshotId": self.snapshot_id,
            "query": self.query,
            "policy": self.policy,
            "project": self.project,
            "offset": self.offset,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @classmethod
    def decode(cls, token: str) -> "ResearchCursor":
        padded = token + "=" * (-len(token) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        except (ValueError, binascii.Error, UnicodeError) as exc:
            raise InvalidResearchRequest("malformed research cursor") from exc
        if not isinstance(payload, Mapping):
            raise InvalidResearchRequest("malformed research cursor")
        try:
            return cls(
                snapshot_id=str(payload["snapshotId"]),
                query=str(payload["query"]),
                policy=str(payload["policy"]),
                project=str(payload["project"]),
                offset=int(payload.get("offset", 0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidResearchRequest("malformed research cursor") from exc

    def validate(self, *, snapshot_id: str, query: str, policy: str,
                 project: str) -> None:
        if self.snapshot_id != snapshot_id:
            raise StaleResearchCursor(
                "the cursor belongs to another snapshot; the project changed")
        if self.query != query:
            raise StaleResearchCursor("the cursor belongs to another query")
        if self.policy != policy:
            raise StaleResearchCursor("the cursor belongs to another policy")
        if self.project != project:
            raise StaleResearchCursor("the cursor belongs to another project")


class DependencyResearchService(DependencyResearchPort):
    """The default dependency research service."""

    def __init__(self, *, project_root: Path,
                 adapters: Sequence[EcosystemResearchPort] = (),
                 acquisition_policy: Optional[AcquisitionPolicy] = None,
                 acquirer=None,
                 reader=None) -> None:
        self.project_root = Path(project_root)
        self._acquirer = acquirer
        # Without an explicit policy the acquirer's own policy governs:
        # the two must never disagree about what may be downloaded.
        self.acquisition_policy = (acquisition_policy
                                   or (acquirer.policy if acquirer is not None
                                       else AcquisitionPolicy()))
        self._reader = reader
        #: The members of the acquired artifacts, addressable by their
        #: evidence reference.
        self._library: dict[str, dict] = {}
        self._adapters: dict[str, EcosystemResearchPort] = {}
        for adapter in adapters:
            self.register(adapter)

    # -- registry ------------------------------------------------------------

    def register(self, adapter: EcosystemResearchPort) -> None:
        self._adapters[adapter.ecosystem] = adapter

    def adapter(self, ecosystem: str) -> EcosystemResearchPort:
        try:
            return self._adapters[ecosystem]
        except KeyError as exc:
            raise ResearchUnsupported(
                f"unsupported ecosystem: {ecosystem!r}; supported: "
                f"{sorted(self._adapters)}"
            ) from exc

    # -- port ----------------------------------------------------------------

    def tree(self, request: DependencyTreeRequest) -> ResearchResult:
        adapter = self.adapter(request.ecosystem)
        snapshot = adapter.collect(
            self.project_root,
            environment=request.environment,
            scopes=request.scopes,
        )
        graph = DependencyGraph(
            ecosystem=snapshot.ecosystem,
            instances=snapshot.instances,
            edges=snapshot.edges,
            snapshot_id=snapshot.snapshot_id,
        )
        project = str(self.project_root.resolve())
        snapshot_id = content_address({
            "project": project,
            "ecosystem": snapshot.ecosystem,
            "snapshot": snapshot.snapshot_id,
        })
        query = content_address({
            "package": request.package,
            "environment": request.environment,
            "scopes": sorted(request.scopes),
        })
        policy = request.limits.fingerprint

        offset = 0
        if request.cursor:
            cursor = ResearchCursor.decode(request.cursor)
            cursor.validate(snapshot_id=snapshot_id, query=query,
                            policy=policy, project=project)
            offset = cursor.offset

        roots = self._roots(graph, request.package)
        outcome = traverse(graph, roots=roots, max_depth=request.limits.max_depth,
                           max_nodes=request.limits.max_nodes)
        nodes = outcome.nodes[offset:]
        truncated = outcome.truncated or offset < len(outcome.nodes)

        status = ResearchStatus.COMPLETE
        if snapshot.completeness is not Completeness.COMPLETE or outcome.truncated:
            status = ResearchStatus.PARTIAL
        if not snapshot.instances:
            status = ResearchStatus.UNAVAILABLE

        cursor = None
        if truncated and nodes:
            next_cursor = ResearchCursor(
                snapshot_id=snapshot_id, query=query, policy=policy,
                project=project, offset=offset + len(nodes))
            cursor = next_cursor.encode()

        warnings = list(snapshot.warnings)
        if outcome.truncated_reason == "max_nodes":
            warnings.append(
                f"the traversal stopped at the node limit "
                f"({request.limits.max_nodes}); the graph is incomplete"
            )
        elif outcome.truncated_reason == "max_depth":
            warnings.append(
                f"the traversal stopped at the depth limit "
                f"({request.limits.max_depth}); deeper dependencies are not shown"
            )

        return ResearchResult(
            snapshot_id=snapshot_id,
            status=status,
            completeness=(snapshot.completeness if status is not
                          ResearchStatus.UNAVAILABLE else Completeness.NONE),
            operation="dependency.tree",
            nodes=tuple(nodes),
            edges=tuple(edge for edge in outcome.edges
                        if edge.source_id in {node.instance_id for node in nodes}),
            evidence=snapshot.evidence,
            warnings=tuple(warnings),
            truncated=truncated,
            cursor=cursor,
            limits=request.limits.as_dict(),
            scope={
                "ecosystem": request.ecosystem,
                "package": request.package,
                "environment": request.environment,
                "scopes": list(request.scopes),
                "project": project,
            },
            detail={"whyPaths": {key: list(value)
                                 for key, value in outcome.why_paths.items()}},
        )

    def search(self, request: DependencySearchRequest) -> ResearchResult:
        adapter = self.adapter(request.ecosystem)
        snapshot = adapter.collect(self.project_root)
        limit = max(1, min(int(request.limit or 1),
                           request.limits.max_symbol_hits))
        needle = (request.query or "").strip().lower()
        matches = []
        for symbol in snapshot.symbols:
            if needle and needle not in symbol.name.lower():
                continue
            if request.package_ref and symbol.package != request.package_ref:
                continue
            matches.append(symbol)
            if len(matches) >= limit:
                break
        truncated = len(matches) >= limit
        return ResearchResult(
            snapshot_id=snapshot.snapshot_id,
            status=(ResearchStatus.PARTIAL if truncated else ResearchStatus.COMPLETE),
            completeness=snapshot.completeness,
            operation="dependency.search",
            evidence=snapshot.evidence,
            excerpts=tuple(symbol.as_dict() for symbol in matches),
            warnings=snapshot.warnings,
            truncated=truncated,
            limits={**request.limits.as_dict(), "limit": limit},
            scope={
                "ecosystem": request.ecosystem,
                "packageRef": request.package_ref,
                "query": request.query,
            },
            detail={"matchCount": len(matches)},
        )

    def read(self, request: DependencyReadRequest) -> ResearchResult:
        """Read a bounded excerpt of library code.

        The artifact must have been acquired before: an inspection never
        reaches the network and a read never downloads anything.
        """

        if request.artifact and request.member:
            artifact = Path(request.artifact)
            member = request.member
        else:
            entry = self._library.get(request.evidence_ref)
            if entry is None:
                raise ResearchUnsupported(
                    "the evidence reference is unknown; acquire the package "
                    "before reading its code"
                )
            artifact = Path(entry["artifact"])
            member = entry["member"]
        if self._reader is None:
            raise ResearchUnsupported(
                "the library reader is not enabled in this deployment")
        return self._reader.read(
            artifact, member, symbol=request.symbol,
            start_line=request.start_line, end_line=request.end_line,
            max_lines=request.limits.max_code_lines,
            max_bytes=request.limits.max_code_bytes,
        )

    def acquire(self, request: DependencyAcquireRequest) -> ResearchResult:
        if not self.acquisition_policy.allows(request.source_id):
            raise ResearchDenied(
                f"the source {request.source_id!r} is not approved by the "
                "acquisition policy"
            )
        if self._acquirer is None:
            raise ResearchUnsupported(
                "artifact acquisition is not enabled in this deployment")
        result = self._acquirer.acquire(request, policy=self.acquisition_policy)
        self._register_artifact(result)
        return result

    def _register_artifact(self, result: ResearchResult) -> None:
        """Index the members of an acquired artifact.

        The members become addressable by their evidence reference, so
        a later read needs no path from the caller.
        """

        artifact = result.detail.get("artifact")
        if not isinstance(artifact, Mapping):
            return
        path = artifact.get("path")
        if not isinstance(path, str) or not path:
            return
        if self._reader is None:
            return
        try:
            index = self._reader.index(Path(path))
        except Exception:  # noqa: BLE001 - an unreadable artifact is not fatal
            return
        for item in index.files:
            reference = content_address({
                "kind": "library-member", "artifact": path,
                "member": item.path, "sha256": item.sha256,
            })
            self._library[reference] = {
                "artifact": path,
                "member": item.path,
                "kind": item.kind,
                "sha256": item.sha256,
            }
        object.__setattr__(result, "detail", {
            **dict(result.detail),
            "members": [item.as_dict() for item in index.files],
            "memberCount": len(index.files),
        })

    # -- capabilities --------------------------------------------------------

    def capabilities(self) -> dict:
        return {
            "service": "dependency-research",
            "project": str(self.project_root),
            "ecosystems": {
                name: adapter.capabilities()
                for name, adapter in sorted(self._adapters.items())
            },
            "acquisition": {
                "enabled": self._acquirer is not None,
                **self.acquisition_policy.as_dict(),
            },
        }

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _roots(graph: DependencyGraph, package: Optional[str]) -> list[str]:
        if package:
            matched = graph.by_name(package)
            if not matched:
                return []
            return [node.instance_id for node in matched]
        roots = [node.instance_id for node in graph.roots()]
        if roots:
            return roots
        # A closed cycle has no root: every instance is an entry point.
        return [node.instance_id for node in graph.instances]
