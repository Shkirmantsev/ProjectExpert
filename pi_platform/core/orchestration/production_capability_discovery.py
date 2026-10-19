"""Production capability discovery (open spec change PR 1, plan §61, §62).

The :class:`ProductionCapabilityReport` and the
:func:`build_production_capability_report` function emit the
documented truthful capability descriptor for the production
embedding, dense index and document processing components.

The report is consumed by the MCP ``describe_capabilities`` tool,
the REST ``/api/v1/admin/retrieval`` endpoint, the CLI
``retrieval-status`` command and the diagnostics panel
(:func:`pi_platform.core.control.diagnostics.v0_8_panels`).

Plan §61 / §62: a component is reported as one of
``real-and-available``, ``real-and-not-installed`` or ``disabled``,
together with its model identifier, immutable revision, output
dimension and execution device where applicable. A component that
raises :class:`EmbeddingModelError` from ``embed()`` is reported
as ``real-and-not-installed`` even when the import path resolves,
so an operator can never be told that a stub is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
)


__all__ = [
    "ComponentState",
    "ComponentReport",
    "ProductionCapabilityReport",
    "build_production_capability_report",
    "classify_embedding_adapter",
    "classify_dense_backend",
    "classify_documents_backend",
]


class ComponentState:
    """Three documented component states (plan §61)."""

    REAL_AND_AVAILABLE = "real-and-available"
    REAL_AND_NOT_INSTALLED = "real-and-not-installed"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ComponentReport:
    """One component report inside :class:`ProductionCapabilityReport`."""

    state: str
    provider: str
    model_id: str | None = None
    model_revision: str | None = None
    dimension: int | None = None
    device: str | None = None
    backend: str | None = None
    note: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"state": self.state, "provider": self.provider}
        for k in (
            "model_id", "model_revision", "dimension", "device",
            "backend", "note",
        ):
            v = getattr(self, k)
            if v is not None:
                result[k] = v
        for k, v in self.extra.items():
            result.setdefault(k, v)
        return result


@dataclass(frozen=True)
class ProductionCapabilityReport:
    """The full production capability report (plan §61)."""

    embedding: ComponentReport
    dense_index: ComponentReport
    documents: ComponentReport
    retrieval_composition: ComponentReport

    def as_dict(self) -> dict[str, Any]:
        return {
            "embedding": self.embedding.as_dict(),
            "denseIndex": self.dense_index.as_dict(),
            "documents": self.documents.as_dict(),
            "retrievalComposition": self.retrieval_composition.as_dict(),
        }


def classify_embedding_adapter(
    adapter: EmbeddingModelPort,
    *,
    provider: str,
) -> ComponentReport:
    """Classify a single embedding adapter as one of the three states.

    The classifier performs a single cheap embed probe
    (``adapter.embed("")``) so a stub adapter that raises
    :class:`EmbeddingModelError` is reported as
    ``real-and-not-installed`` rather than ``real-and-available``.
    The probe text is empty; the hashing adapter returns a
    deterministic zero vector for empty input and stays
    ``real-and-available``. Real production adapters also accept
    empty input (the ``_validate_vector`` checks only non-finite
    values, not non-zero norm).
    """

    profile = adapter.profile()
    base = {
        "provider": provider,
        "model_id": getattr(profile, "model_id", None),
        "model_revision": getattr(profile, "model_revision", None),
        "dimension": adapter.dimension(),
    }
    try:
        v = adapter.embed("")
        # Sanity: the returned vector must have the declared
        # dimension and contain finite values.
        if len(v) != base["dimension"]:
            return ComponentReport(
                state=ComponentState.REAL_AND_NOT_INSTALLED,
                note=(
                    f"adapter returned a vector of length {len(v)} but "
                    f"profile declares {base['dimension']}"
                ),
                **base,
            )
        for x in v:
            try:
                if not (float("-inf") < float(x) < float("inf")):
                    return ComponentReport(
                        state=ComponentState.REAL_AND_NOT_INSTALLED,
                        note="adapter returned a non-finite value",
                        **base,
                    )
            except (TypeError, ValueError):
                return ComponentReport(
                    state=ComponentState.REAL_AND_NOT_INSTALLED,
                    note="adapter returned a non-numeric value",
                    **base,
                )
        stats = dict(adapter.stats())
        if str(stats.get("real_binding", "1")) == "0":
            return ComponentReport(
                state=ComponentState.REAL_AND_NOT_INSTALLED,
                note=(
                    "the adapter is constructed but the real binding "
                    "is not loaded; install sentence-transformers and "
                    "the pinned model revision."
                ),
                **base,
            )
        return ComponentReport(
            state=ComponentState.REAL_AND_AVAILABLE, **base,
        )
    except EmbeddingModelError as exc:
        return ComponentReport(
            state=ComponentState.REAL_AND_NOT_INSTALLED,
            note=str(exc),
            **base,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return ComponentReport(
            state=ComponentState.REAL_AND_NOT_INSTALLED,
            note=f"unexpected error during probe: {exc!r}",
            **base,
        )


def classify_dense_backend(backend_name: str) -> ComponentReport:
    """Classify a dense backend by its reported ``backend`` name.

    The USearch adapter reports ``usearch-stub`` while it is still
    a stub; the production-capability-gate relies on this
    distinction to detect a stub in production.
    """

    if backend_name in {"usearch-stub"}:
        return ComponentReport(
            state=ComponentState.REAL_AND_NOT_INSTALLED,
            provider="usearch",
            backend=backend_name,
            note=(
                "the USearch adapter is still the in-memory stub; "
                "PR 6 of the production-hardening change binds the "
                "real usearch.Index."
            ),
        )
    if backend_name in {"usearch"}:
        return ComponentReport(
            state=ComponentState.REAL_AND_AVAILABLE,
            provider="usearch",
            backend=backend_name,
        )
    if backend_name in {"flat", "flat-memory"}:
        return ComponentReport(
            state=ComponentState.DISABLED,
            provider="flat-memory",
            backend=backend_name,
            note=(
                "the flat-memory backend is only allowed in the "
                "explicit minimal startup profile and in tests."
            ),
        )
    return ComponentReport(
        state=ComponentState.REAL_AND_NOT_INSTALLED,
        provider=backend_name or "unknown",
        backend=backend_name,
    )


def classify_documents_backend(
    docling_enabled: bool, *, docling_importable: bool,
) -> ComponentReport:
    """Classify the document processing backend."""

    if not docling_enabled:
        return ComponentReport(
            state=ComponentState.DISABLED,
            provider="docling",
            note=(
                "Docling document processing is disabled by the "
                "operator (PI_DOCLING_ENABLED=0)."
            ),
        )
    if docling_importable:
        return ComponentReport(
            state=ComponentState.REAL_AND_AVAILABLE,
            provider="docling",
        )
    return ComponentReport(
        state=ComponentState.REAL_AND_NOT_INSTALLED,
        provider="docling",
        note=(
            "Docling is enabled but the docling package is not "
            "installed; install the documents optional dependency "
            "group."
        ),
    )


def build_production_capability_report(
    *,
    embedding_adapter: EmbeddingModelPort | None,
    embedding_provider: str,
    dense_backend_name: str,
    docling_enabled: bool,
) -> ProductionCapabilityReport:
    """Build the production capability report from the active components.

    The function is the single entry point used by the MCP tool,
    the REST endpoint, the CLI command and the diagnostics panel.
    """

    if embedding_adapter is None:
        embedding = ComponentReport(
            state=ComponentState.DISABLED,
            provider=embedding_provider,
            note="no embedding adapter is bound",
        )
    else:
        embedding = classify_embedding_adapter(
            embedding_adapter, provider=embedding_provider,
        )

    dense = classify_dense_backend(dense_backend_name)

    try:
        import docling  # noqa: F401
        docling_importable = True
    except Exception:
        docling_importable = False

    documents = classify_documents_backend(
        docling_enabled, docling_importable=docling_importable,
    )

    retrieval_composition = ComponentReport(
        state=(
            ComponentState.REAL_AND_AVAILABLE
            if (
                embedding.state == ComponentState.REAL_AND_AVAILABLE
                and dense.state == ComponentState.REAL_AND_AVAILABLE
            )
            else ComponentState.REAL_AND_NOT_INSTALLED
        ),
        provider="unified-production-composition",
        backend="build_production_retrieval_runtime",
        note=(
            "the unified production composition is available only "
            "when both the embedding and dense components are "
            "real-and-available; otherwise the platform serves the "
            "minimal diagnostic composition."
        ),
    )

    return ProductionCapabilityReport(
        embedding=embedding,
        dense_index=dense,
        documents=documents,
        retrieval_composition=retrieval_composition,
    )
