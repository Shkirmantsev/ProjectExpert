"""Dependency graph construction and bounded traversal.

The graph is derived data: it is rebuilt from the manifests and locks of
a repository snapshot and is never persisted as a source of truth.

Traversal is breadth-first and *bounded*. It stops at the requested
depth, at the requested node count and at the first cycle it meets. A
cycle is a fact about the dependency graph, not an error: the node is
visited once and the closing edge is kept, so the caller can see that
the graph is cyclic.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional, Sequence

from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.research.records import (
    DependencyEdge,
    Package,
    PackageInstance,
)

__all__ = [
    "instance_id",
    "DependencyGraph",
    "TraversalOutcome",
    "traverse",
]


def instance_id(package: Package, *, lock_location: Optional[str] = None,
                workspace: Optional[str] = None,
                peer_context: Optional[str] = None) -> str:
    """Stable identity of a package *instance*.

    The identity incorporates the package identity and the artifact
    context, so two versions of one package, the same package in two
    workspaces and the same package under two peer contexts stay
    distinct nodes.
    """

    return content_address({
        "ecosystem": package.ecosystem,
        "name": package.name,
        "resolvedVersion": package.resolved_version,
        "declaredConstraint": package.declared_constraint,
        "lockLocation": lock_location,
        "workspace": workspace,
        "peerContext": peer_context,
    })


@dataclass
class DependencyGraph:
    """An immutable-by-convention view of one ecosystem snapshot."""

    ecosystem: str
    instances: tuple[PackageInstance, ...] = ()
    edges: tuple[DependencyEdge, ...] = ()
    snapshot_id: str = ""

    def __post_init__(self) -> None:
        self._by_id = {node.instance_id: node for node in self.instances}
        self._out: dict[str, list[DependencyEdge]] = {}
        for edge in self.edges:
            self._out.setdefault(edge.source_id, []).append(edge)

    # -- lookups ------------------------------------------------------------

    def node(self, instance_id_: str) -> Optional[PackageInstance]:
        return self._by_id.get(instance_id_)

    def by_name(self, name: str) -> tuple[PackageInstance, ...]:
        return tuple(node for node in self.instances if node.package.name == name)

    def out_edges(self, instance_id_: str) -> tuple[DependencyEdge, ...]:
        return tuple(self._out.get(instance_id_, ()))

    def roots(self) -> tuple[PackageInstance, ...]:
        """Instances nothing depends on (no incoming edge)."""

        referenced = {edge.target_id for edge in self.edges if edge.target_id}
        return tuple(node for node in self.instances
                     if node.instance_id not in referenced)


@dataclass
class TraversalOutcome:
    """The bounded result of one traversal."""

    nodes: tuple[PackageInstance, ...] = ()
    edges: tuple[DependencyEdge, ...] = ()
    why_paths: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    truncated: bool = False
    truncated_reason: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
            "whyPaths": {key: list(value) for key, value in self.why_paths.items()},
            "truncated": self.truncated,
            "truncatedReason": self.truncated_reason,
        }


def _root_ids(graph: DependencyGraph, roots: Iterable[str]) -> list[str]:
    return [root for root in roots if root in graph._by_id]


def traverse(graph: DependencyGraph, *, roots: Sequence[str], max_depth: int,
             max_nodes: int) -> TraversalOutcome:
    """Walk the graph breadth-first from ``roots``.

    ``max_depth`` counts edges: the roots are at depth 0 and a node
    reachable over ``max_depth`` edges is included. ``max_nodes`` caps
    the number of returned nodes. When a cap is reached the outcome is
    marked truncated and the reason is reported, so the caller can say
    that the graph is incomplete instead of implying it is complete.
    """

    start = _root_ids(graph, roots)
    if not start:
        return TraversalOutcome(truncated=False)

    visited: dict[str, int] = {root: 0 for root in start}
    order: list[str] = []
    why: dict[str, tuple[str, ...]] = {root: (root,) for root in start}
    selected_edges: list[DependencyEdge] = []
    queue: deque[tuple[str, int]] = deque((root, 0) for root in start)
    truncated = False
    reason: Optional[str] = None

    while queue:
        current, depth = queue.popleft()
        order.append(current)
        if len(order) > max_nodes:
            truncated = True
            reason = "max_nodes"
            break
        if depth >= max_depth:
            # The node is included, but its own dependencies are not.
            if graph.out_edges(current):
                truncated = True
                reason = "max_depth"
            continue
        for edge in graph.out_edges(current):
            selected_edges.append(edge)
            target = edge.target_id
            if target is None or target not in graph._by_id:
                # An unresolved target is reported as an edge with no
                # target node; it is not an invented node.
                continue
            if target in visited:
                continue
            visited[target] = depth + 1
            why[target] = why[current] + (target,)
            queue.append((target, depth + 1))
            if len(order) + len(queue) > max_nodes:
                truncated = True
                reason = "max_nodes"
                break
        if truncated:
            break

    if not truncated and queue:
        truncated = True
        reason = "max_depth"

    ordered = order[:max_nodes]
    keep = set(ordered)
    return TraversalOutcome(
        nodes=tuple(graph.node(node_id) for node_id in ordered if graph.node(node_id)),
        edges=tuple(edge for edge in selected_edges
                     if edge.source_id in keep),
        why_paths={node_id: why[node_id] for node_id in ordered if node_id in why},
        truncated=truncated,
        truncated_reason=reason,
    )
