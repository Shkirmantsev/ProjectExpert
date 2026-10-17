"""Plan §32 Control Plane v0.8 panel descriptors.

Each panel is a :class:`UiExtensionDescriptor` of kind
``STATUS_PANEL`` registered through the existing
:class:`DefaultUiExtensionRegistry`. The descriptor schema is the
Phase 7 §59.16 declarative shape, so the registry's no-arbitrary-
JavaScript rule keeps applying unchanged. Every panel carries a
JSON-schema ``configurationSchema`` describing the fields rendered
under it; the schema is intentionally read-only so the panels stay
status surfaces, not configuration sinks.

Panels shipped here (Change Package I of the v0.8 refinement):

* ``ui.v0_8.ingestion`` — active PDF parser, OCR mode, page batch
  size, in-flight ingestion jobs.
* ``ui.v0_8.chunking`` — active tokenizer, target / max / min token
  budgets, active chunk profile.
* ``ui.v0_8.embeddings`` — active embedding model / revision,
  device, dimension, normalization, index profile compatibility.
* ``ui.v0_8.retrieval`` — dense / lexical candidate pools,
  primary / reserve sizes, reranker profile, retrieval-trace
  exposure.
* ``ui.v0_8.accelerator`` — host accelerator health, device, free
  memory, CPU-fallback state.
* ``ui.v0_8.evaluation`` — latest Tier-3 benchmark report summary.

Conventions: ``from __future__ import annotations``, frozen
dataclasses for value types, absolute imports, docstrings on every
public symbol, ``# -- internal helpers --`` separator for private
helpers, ``__all__`` listing every public symbol.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Sequence

from pi_platform.core.control.ui_extensions import DefaultUiExtensionRegistry
from pi_platform.ports.control.ui_extensions import (
    UiExtensionDescriptor,
    UiExtensionKind,
    UiExtensionRegistryPort,
)


__all__ = [
    "PANEL_IDS",
    "V08_PANEL_VERSION",
    "V08PanelSet",
    "build_v0_8_panels",
    "iter_v0_8_panel_descriptors",
    "register_v0_8_panels",
    "serialise_v0_8_panels",
]


# Bumped when a panel schema changes incompatibly. The dashboards
# read this to know whether their cached panel bundle is still
# valid; the registry serialisation already exposes the schema.
V08_PANEL_VERSION = "0.8.0"

# Stable panel IDs. The ``ui.v0_8.`` prefix namespaces the v0.8
# refinement panels so the existing Phase 7 status panels stay
# registered alongside them without colliding.
PANEL_IDS: tuple[str, ...] = (
    "ui.v0_8.ingestion",
    "ui.v0_8.chunking",
    "ui.v0_8.embeddings",
    "ui.v0_8.retrieval",
    "ui.v0_8.accelerator",
    "ui.v0_8.evaluation",
)


@dataclass(frozen=True)
class V08PanelSet:
    """The six v0.8 Control Plane panels as a frozen bundle.

    The :func:`build_v0_8_panels` factory always returns one panel
    per documented section so callers can address the bundle as a
    single value. Registering through
    :meth:`DefaultUiExtensionRegistry.register` is optional and
    idempotent — the same panel can be registered against multiple
    registries (production, eval, control-plane shell, etc.).
    """

    panels: tuple[UiExtensionDescriptor, ...]

    def by_id(self, panel_id: str) -> UiExtensionDescriptor | None:
        """Return the panel whose ``id`` equals ``panel_id`` or
        :data:`None` if the bundle does not carry it.
        """

        for panel in self.panels:
            if panel.id == panel_id:
                return panel
        return None

    def ids(self) -> tuple[str, ...]:
        """Return the panel IDs in declaration order."""

        return tuple(panel.id for panel in self.panels)


# -- internal helpers -----------------------------------------------------


def _schema(fields: Sequence[tuple[str, str, str]]) -> str:
    """Return the JSON-schema ``properties`` block for ``fields``.

    Each field is a ``(name, type, description)`` triple. The schema
    is intentionally read-only (``readOnly: true`` per property and
    ``additionalProperties: false`` at the root) so the panel is a
    status surface, not a configuration sink.
    """

    properties: dict[str, dict] = {}
    for name, type_name, description in fields:
        properties[name] = {
            "type": type_name,
            "description": description,
            "readOnly": True,
        }
    return json.dumps(
        {
            "type": "object",
            "title": f"v0.8 panel schema {V08_PANEL_VERSION}",
            "additionalProperties": False,
            "properties": properties,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


# Per-panel field triples. ``(name, type, description)``.
_INGESTION_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("pdfParser", "string",
     "Active PDF parser adapter identifier (Docling, pdfplumber)."),
    ("ocrMode", "string",
     "Active OCR policy: native_text | selective | full_page."),
    ("pageBatchSize", "integer",
     "Pages per parse batch for resumable ingestion."),
    ("activeJobs", "integer",
     "Number of in-flight ingestion jobs (RUNNING / PAUSED)."),
)

_CHUNKING_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("tokenizer", "string",
     "Active tokenizer identifier (Whitespace, Hashing, "
     "EmbeddingGemma2)."),
    ("targetTokens", "integer",
     "Target token count per chunk under the active profile."),
    ("maxTokens", "integer",
     "Hard token cap enforced by the token-budget normalizer."),
    ("chunkProfile", "string",
     "Active chunker strategy (Markdown, Java, protocol, hybrid)."),
)

_EMBEDDINGS_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("activeModel", "string",
     "Active EmbeddingProfile descriptor identifier."),
    ("modelRevision", "string",
     "Pinned model revision (sha256 of the canonical profile)."),
    ("device", "string",
     "Active device: cpu | cuda | mps | accelerator."),
    ("dimension", "integer",
     "Embedding vector dimension."),
    ("normalization", "string",
     "Active vector normalization (none | l2 | unit-length)."),
    ("indexCompatibility", "string",
     "ANN namespace compatibility vs the active profile."),
)

_RETRIEVAL_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("denseCandidates", "integer",
     "Dense candidate pool size per query."),
    ("lexicalCandidates", "integer",
     "Sparse candidate pool size per query."),
    ("primaryPoolSize", "integer",
     "PRIMARY selection pool budget."),
    ("reservePoolSize", "integer",
     "RESERVE selection pool budget."),
    ("rerankerProfile", "string",
     "Active reranker profile (minimal | quality | quality-qwen3)."),
    ("debugTrace", "boolean",
     "Whether the retrieval trace is attached to the API response."),
)

_ACCELERATOR_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("health", "string",
     "Latest accelerator /health response status."),
    ("device", "string",
     "Accelerator device (cuda / mps / cpu-fallback)."),
    ("memory", "string",
     "Free GPU memory reported by the accelerator (human readable)."),
    ("fallbackState", "string",
     "CPU fallback state (active | inactive | disabled)."),
)

_EVALUATION_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("latestReport", "string",
     "Path to the latest Tier-3 retrieval evaluation report."),
    ("lastRunAt", "string",
     "ISO-8601 timestamp of the latest report."),
    ("scope", "string",
     "Evaluation scope (synthetic / generated-pdf / multilingual)."),
)


def build_v0_8_panels() -> V08PanelSet:
    """Return the six v0.8 Control Plane panels.

    The descriptors are deterministic; calling the factory twice
    yields byte-identical registries. ``configuration_schema`` is a
    compact JSON string so the existing
    :meth:`DefaultUiExtensionRegistry.serialise` contract keeps its
    byte-stable shape.
    """

    panels: list[UiExtensionDescriptor] = [
        UiExtensionDescriptor(
            id="ui.v0_8.ingestion",
            kind=UiExtensionKind.STATUS_PANEL,
            title="Ingestion",
            description=(
                "Plan §32 Ingestion panel: PDF parser, OCR mode, page "
                "batch size and active ingestion jobs."
            ),
            icon="ingestion",
            route="/diagnostics/ingestion",
            configuration_schema=_schema(_INGESTION_FIELDS),
        ),
        UiExtensionDescriptor(
            id="ui.v0_8.chunking",
            kind=UiExtensionKind.STATUS_PANEL,
            title="Chunking",
            description=(
                "Plan §32 Chunking panel: active tokenizer, target / "
                "max token budgets, active chunk profile."
            ),
            icon="chunking",
            route="/diagnostics/chunking",
            configuration_schema=_schema(_CHUNKING_FIELDS),
        ),
        UiExtensionDescriptor(
            id="ui.v0_8.embeddings",
            kind=UiExtensionKind.STATUS_PANEL,
            title="Embeddings",
            description=(
                "Plan §32 Embeddings panel: active model / revision, "
                "device, dimension, normalization, index compatibility."
            ),
            icon="embeddings",
            route="/diagnostics/embeddings",
            configuration_schema=_schema(_EMBEDDINGS_FIELDS),
        ),
        UiExtensionDescriptor(
            id="ui.v0_8.retrieval",
            kind=UiExtensionKind.STATUS_PANEL,
            title="Retrieval",
            description=(
                "Plan §32 Retrieval panel: dense / lexical candidate "
                "pools, primary / reserve sizes, reranker profile, "
                "retrieval-trace exposure."
            ),
            icon="retrieval",
            route="/diagnostics/retrieval",
            configuration_schema=_schema(_RETRIEVAL_FIELDS),
        ),
        UiExtensionDescriptor(
            id="ui.v0_8.accelerator",
            kind=UiExtensionKind.STATUS_PANEL,
            title="Accelerator",
            description=(
                "Plan §32 Accelerator panel: health, device, free "
                "memory, CPU-fallback state."
            ),
            icon="accelerator",
            route="/diagnostics/accelerator",
            configuration_schema=_schema(_ACCELERATOR_FIELDS),
        ),
        UiExtensionDescriptor(
            id="ui.v0_8.evaluation",
            kind=UiExtensionKind.STATUS_PANEL,
            title="Evaluation",
            description=(
                "Plan §32 Evaluation panel: latest Tier-3 retrieval "
                "benchmark report."
            ),
            icon="evaluation",
            route="/diagnostics/evaluation",
            configuration_schema=_schema(_EVALUATION_FIELDS),
        ),
    ]
    return V08PanelSet(panels=tuple(panels))


def register_v0_8_panels(
    registry: UiExtensionRegistryPort,
    *,
    panel_set: V08PanelSet | None = None,
) -> V08PanelSet:
    """Register the six v0.8 panels on ``registry``.

    Returns the :class:`V08PanelSet` actually registered so the
    caller can refresh the registry's other side-effects (audit
    log, hooks, etc.) without recomputing the panel set. The
    factory :func:`build_v0_8_panels` is invoked lazily so the
    caller can supply a pre-built set for snapshot tests.
    """

    bundle = panel_set if panel_set is not None else build_v0_8_panels()
    if isinstance(registry, DefaultUiExtensionRegistry):
        # The default registry rejects duplicate IDs, so it is safe
        # to call ``register`` again with the same set; the second
        # call is a no-op when every panel already exists.
        existing = {descriptor.id for descriptor in registry.list()}
        for descriptor in bundle.panels:
            if descriptor.id in existing:
                continue
            registry.register(descriptor)
    else:
        for descriptor in bundle.panels:
            registry.register(descriptor)
    return bundle


def serialise_v0_8_panels(
    registry: UiExtensionRegistryPort,
) -> str:
    """Return the registry serialisation containing the v0.8 panels.

    The serialisation reuses the registry's own byte-stable
    serialise contract so the panel set can be embedded in the
    project knowledge snapshot without an extra layer. The
    returned string covers every descriptor the registry holds
    (not only the v0.8 panels); callers that need a v0.8-only
    slice should filter the result themselves or build a
    dedicated registry.
    """

    return registry.serialise()


def iter_v0_8_panel_descriptors(
    panel_set: V08PanelSet | None = None,
) -> Iterable[UiExtensionDescriptor]:
    """Yield each v0.8 panel descriptor in declaration order."""

    bundle = panel_set if panel_set is not None else build_v0_8_panels()
    return iter(bundle.panels)