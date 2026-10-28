"""Production-capability gate (open spec change PR 12, plan §64).

The :func:`run_production_capability_gate` function is the
release-blocking check that fails a build when a
``production_enabled`` model record in
:file:`distribution/licenses/model-licenses.json` is still
``pinned-stub`` or when a critical production component is still
a stub at runtime.

The gate is intentionally conservative: a single
``pinned-stub`` record with ``production_enabled: true`` fails
the build even when every other check would pass. The boundary
is documented in
:file:`openspec/changes/production-semantic-search-and-branch-reconciliation/excluded-profiles.md`.

Besides the license-inventory scan the gate runs the three
runtime probes the spec delta demands (plan §64):

* a production model adapter that raises
  :class:`EmbeddingModelError` *unconditionally* (the
  diagnostic stub / ``not bound`` contract) fails the build;
* an unavailable real USearch package (``usearch-stub``
  backend) fails the build;
* an unavailable real Docling binding (synthetic Docling
  adapter) fails the build.

Every production-enabled model must load and encode successfully in the
release lane. The explicit inventory-only lane checks metadata without
claiming that optional runtime capabilities have been verified.

The function is callable as a library entry point and as a CLI
through :mod:`pi_platform.cli.production_capability_gate`.
"""

from __future__ import annotations

import json
import os
import sys
import re
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from pi_platform.adapters.pdf import real_docling
from pi_platform.adapters.retrieval.embedding_model_factory import (
    EmbeddingModelFactory,
)
from pi_platform.adapters.runtime import usearch_dense_index
from pi_platform.ports.retrieval.embedding_model import EmbeddingModelError


__all__ = [
    "GateVerdict",
    "GateReport",
    "run_production_capability_gate",
    "gate_records_from_inventory",
    "is_docling_available",
    "is_real_usearch_available",
]


def is_docling_available() -> bool:
    """Real-Docling availability signal (vendor boundary).

    Delegates to
    :func:`pi_platform.adapters.pdf.real_docling.is_docling_available`
    so the gate never imports ``docling`` itself, and stays a
    patchable seam for tests whether they patch this module or the
    adapter boundary.
    """

    return real_docling.is_docling_available()


def is_real_usearch_available() -> bool:
    """Real-USearch availability signal.

    Delegates to
    :func:`pi_platform.adapters.runtime.usearch_dense_index.is_real_usearch_available`
    and stays a patchable seam for tests whether they patch this
    module or the adapter module.
    """

    return usearch_dense_index.is_real_usearch_available()


REPO_ROOT_HINT = (
    Path(__file__).resolve().parents[3]
    if "pi_platform" in str(Path(__file__).resolve())
    else Path.cwd()
)


@dataclass(frozen=True)
class GateVerdict:
    """The verdict for one check of the gate.

    ``name`` is the stable machine-readable check identifier the
    CLI report (``checks[].name``) prints; it is empty only for
    verdicts that predate named checks.
    """

    state: str
    detail: str
    name: str = ""


@dataclass(frozen=True)
class GateReport:
    """The full gate report."""

    passed: bool
    verdicts: tuple[GateVerdict, ...] = field(default_factory=tuple)
    skipped: tuple[GateVerdict, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "verdicts": [
                {
                    "name": v.name,
                    "state": v.state,
                    "detail": v.detail,
                }
                for v in self.verdicts
            ],
            "skipped": [
                {
                    "name": v.name,
                    "state": v.state,
                    "detail": v.detail,
                }
                for v in self.skipped
            ],
        }


def _load_inventory(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def gate_records_from_inventory(inventory: dict) -> tuple[list[dict], list[dict]]:
    """Split the inventory into (production_enabled, excluded) records.

    The function is the single source of truth for the gate's
    record classification; it is the same algorithm the
    :class:`tests.test_production_capability_gate` tests assert.
    """

    production: list[dict] = []
    excluded: list[dict] = []
    for record in inventory.get("models", []):
        if record.get("production_enabled") is True:
            production.append(record)
        else:
            excluded.append(record)
    return production, excluded


def _classify_record(record: dict) -> GateVerdict:
    revision = (record.get("revision") or "").strip()
    status = (record.get("status") or "").strip()
    model_id = record.get("model_id", "<unknown>")
    profile = record.get("profile", "<unknown>")
    name = f"inventory:{model_id}"
    if revision == "pinned-stub" or status == "pinned-stub":
        return GateVerdict(
            state="FAIL",
            name=name,
            detail=(
                f"production_enabled record {model_id!r} (profile "
                f"{profile!r}) is still pinned-stub "
                f"(revision={revision!r}, status={status!r})"
            ),
        )
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        return GateVerdict(
            state="FAIL",
            name=name,
            detail=(
                f"production_enabled record {model_id!r} (profile "
                f"{profile!r}) has no immutable 40-character revision"
            ),
        )
    if not status or status not in {
        "active-default", "real-and-available", "real-and-available-when-bound",
    }:
        return GateVerdict(
            state="FAIL",
            name=name,
            detail=(
                f"production_enabled record {model_id!r} (profile "
                f"{profile!r}) has unexpected status {status!r}"
            ),
        )
    return GateVerdict(
        state="PASS",
        name=name,
        detail=(
            f"production_enabled record {model_id!r} (profile "
            f"{profile!r}) at revision {revision[:12]}... is pinned "
            f"and ready"
        ),
    )


# Markers that identify the documented stub / not-bound contract of
# a production adapter regardless of the wording a future stub
# chooses (plan §64: "not bound" and "pinned-stub" are release
# blockers).
_STUB_MARKERS = ("not bound", "pinned-stub", "usearch-stub")

# Plan §6.1: the real binding defaults to CPU + float32. The gate
# probes on CPU so the verdict does not depend on accelerator
# availability on the release runner.
_PROBE_DEVICE = "cpu"


def _probe_embedding_record(record: Mapping) -> GateVerdict:
    """Probe the production embedding adapter behind one record.

    Plan §64 fails the build when a production model adapter raises
    :class:`EmbeddingModelError` unconditionally — that is the
    diagnostic stub contract: the adapter raises for every input
    without ever having attempted to load its pinned weights, or it
    raises the documented ``not bound`` message.

    A failure to load pinned weights is a release failure, including offline,
    incompatible-dependency and incomplete-cache errors.
    """

    model_id = record.get("model_id", "<unknown>")
    profile = record.get("profile", "<unknown>")
    provider = record.get("provider", "")
    name = f"embedding:{model_id}"

    try:
        adapter = EmbeddingModelFactory().build(provider, device=_PROBE_DEVICE)
    except EmbeddingModelError as exc:
        return GateVerdict(
            state="FAIL",
            name=name,
            detail=(
                f"production_enabled record {model_id!r} (profile "
                f"{profile!r}) resolves to a not bound binding: {exc}"
            ),
        )

    try:
        vector = adapter.embed("production capability verification")
    except EmbeddingModelError as exc:
        message = str(exc)
        attempted_load = bool(getattr(adapter, "_load_failed", False))
        stub_like = (not attempted_load) or any(
            marker in message for marker in _STUB_MARKERS
        )
        if stub_like:
            return GateVerdict(
                state="FAIL",
                name=name,
                detail=(
                    f"production model adapter {model_id!r} (profile "
                    f"{profile!r}) raises EmbeddingModelError "
                    f"unconditionally: {message}"
                ),
            )
        return GateVerdict(
            state="FAIL", name=name,
            detail=f"production model {model_id!r} could not load pinned weights: {message}",
        )
    except Exception as exc:  # pragma: no cover - defensive
        return GateVerdict(
            state="FAIL",
            name=name,
            detail=(
                f"unexpected error while probing the production model "
                f"adapter {model_id!r} (profile {profile!r}): {exc!r}"
            ),
        )

    norm = math.sqrt(sum(float(v) ** 2 for v in vector))
    if not all(math.isfinite(float(v)) for v in vector) or not math.isfinite(norm) or abs(norm - 1.0) > 0.02:
        return GateVerdict(state="FAIL", name=name, detail=f"production model {model_id!r} returned a non-finite or non-normalized vector")
    if adapter.profile().model_revision != record.get("revision"):
        return GateVerdict(state="FAIL", name=name, detail=f"production model {model_id!r} revision does not match the release inventory")
    dimension = adapter.dimension()
    if len(vector) != dimension:
        return GateVerdict(
            state="FAIL",
            name=name,
            detail=(
                f"production model adapter {model_id!r} (profile "
                f"{profile!r}) returned {len(vector)} dimensions, "
                f"profile declares {dimension}"
            ),
        )
    return GateVerdict(
        state="PASS",
        name=name,
        detail=(
            f"embedding probe for {model_id!r} (profile {profile!r}) "
            f"returned a {dimension}-dimension vector"
        ),
    )


def _probe_dense_backend() -> GateVerdict:
    """Fail the build while the dense backend is still a stub."""

    name = "dense-index:usearch"
    if is_real_usearch_available():
        return GateVerdict(
            state="PASS",
            name=name,
            detail=(
                "the real USearch native package is importable; the "
                "dense backend resolves to 'usearch'"
            ),
        )
    return GateVerdict(
        state="FAIL",
        name=name,
        detail=(
            "the USearch native package is unavailable; the dense "
            "backend would resolve to the 'usearch-stub' backend"
        ),
    )


def _probe_documents_backend() -> GateVerdict:
    """Fail the build while documents would use a synthetic adapter."""

    name = "documents:docling"
    # Vendor boundary: reach Docling only through the adapter.
    if is_docling_available():
        return GateVerdict(
            state="PASS",
            name=name,
            detail=(
                "the real Docling binding is importable; the "
                "synthetic Docling adapter is not used"
            ),
        )
    return GateVerdict(
        state="FAIL",
        name=name,
        detail=(
            "the real Docling binding is unavailable "
            "(is_docling_available() returned False); the production "
            "path would have to fall back to a synthetic Docling "
            "adapter"
        ),
    )


def _probe_dependency_research() -> GateVerdict:
    """Fail the build when the research capability only acknowledges.

    The dependency research capability must answer with **evidence**: a
    status, the nodes it could resolve and the warnings that explain
    what it could not. An acknowledgement ("ok") or an echo of the
    requested coordinates is not a capability, and the gate says so.
    """

    name = "dependency-research:evidence"
    try:
        from pi_platform.adapters.research.composition import (
            build_dependency_research_service,
        )
        from pi_platform.ports.research.dependency_research import (
            DependencyTreeRequest,
        )
    except ImportError as exc:  # pragma: no cover - the module ships
        return GateVerdict(
            state="FAIL", name=name,
            detail=f"the dependency research service is not importable: {exc}",
        )
    try:
        service = build_dependency_research_service(project_root=REPO_ROOT_HINT)
        result = service.tree(DependencyTreeRequest(ecosystem="python"))
    except Exception as exc:  # noqa: BLE001 - the gate must not crash
        return GateVerdict(
            state="FAIL", name=name,
            detail=f"the dependency research service failed: {exc}",
        )
    payload = result.as_dict()
    status = payload.get("status")
    if status not in ("complete", "partial", "unavailable"):
        return GateVerdict(
            state="FAIL", name=name,
            detail=(
                f"the research answer carries the status {status!r}; an "
                "acknowledgement is not a capability"
            ),
        )
    if "nodes" not in payload or "warnings" not in payload:
        return GateVerdict(
            state="FAIL", name=name,
            detail=("the research answer has no nodes and no warnings; it "
                    "does not report what it could not resolve"),
        )
    nodes = payload.get("nodes") or ()
    if nodes:
        evidence = payload.get("evidence") or ()
        if not evidence:
            return GateVerdict(
                state="FAIL", name=name,
                detail=("the research answer reports nodes without any "
                        "evidence reference"),
            )
        names = {node.get("package", {}).get("name") for node in nodes}
        if len(names) < 2:
            return GateVerdict(
                state="FAIL", name=name,
                detail=("the research answer echoes a single coordinate "
                        "instead of a dependency graph"),
            )
    return GateVerdict(
        state="PASS", name=name,
        detail=(
            f"the research capability answers with evidence (status={status}, "
            f"nodes={len(nodes)})"
        ),
    )


def run_production_capability_gate(
    *,
    inventory_path: Path | None = None,
    repo_root: Path | None = None,
    runtime_checks: bool = True,
) -> GateReport:
    """Run the production-capability gate and return the report.

    ``inventory_path`` defaults to
    ``<repo_root>/distribution/licenses/model-licenses.json``;
    ``repo_root`` defaults to the project root inferred from the
    current file's path.

    The report contains one verdict per production-enabled record
    (license-inventory scan plus embedding probe), one verdict for
    the dense backend and one verdict for the documents backend.
    Only explicitly excluded records land in ``skipped``. Missing or broken
    production components fail. ``runtime_checks=False`` is the explicit
    inventory-only core CI lane, not a production release verdict.
    """

    repo = repo_root or REPO_ROOT_HINT
    inv_path = inventory_path or (
        repo / "distribution" / "licenses" / "model-licenses.json"
    )
    if inventory_path is None and repo_root is None and not inv_path.exists():
        inv_path = Path(sys.prefix) / "distribution/licenses/model-licenses.json"
    if not inv_path.exists():
        return GateReport(
            passed=False,
            verdicts=(
                GateVerdict(
                    state="FAIL",
                    name="inventory",
                    detail=f"inventory file not found at {inv_path}",
                ),
            ),
            skipped=(),
        )
    inventory = _load_inventory(inv_path)
    production, excluded = gate_records_from_inventory(inventory)

    verdicts: list[GateVerdict] = []
    runtime_skipped: list[GateVerdict] = []
    for record in production:
        verdicts.append(_classify_record(record))
        if not runtime_checks:
            continue
        probe = _probe_embedding_record(record)
        if probe.state == "SKIPPED":
            runtime_skipped.append(probe)
        else:
            verdicts.append(probe)
    if runtime_checks:
        verdicts.append(_probe_dense_backend())
        verdicts.append(_probe_documents_backend())
        verdicts.append(_probe_dependency_research())

    skipped = tuple(
        GateVerdict(
            state="SKIPPED",
            name=f"inventory:{r.get('model_id', '<unknown>')}",
            detail=(
                f"excluded record {r.get('model_id', '<unknown>')!r} "
                f"is out of gate scope"
            ),
        )
        for r in excluded
    ) + tuple(runtime_skipped)
    passed = all(v.state == "PASS" for v in verdicts)
    return GateReport(
        passed=passed,
        verdicts=tuple(verdicts),
        skipped=skipped,
    )
