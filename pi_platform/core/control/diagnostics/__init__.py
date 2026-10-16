"""Phase 7 §59 Control Plane diagnostics extensions.

Change Package I of the v0.8 refinement (``improve-ingestion-
retrieval-local-models``) extends the Phase 7 Control Plane
diagnostics surface with the six v0.8 panels documented in plan
§32: Ingestion, Chunking, Embeddings, Retrieval, Accelerator and
Evaluation.

The panels are declarative :class:`UiExtensionDescriptor` records
registered through the existing
:class:`DefaultUiExtensionRegistry` so the no-arbitrary-JavaScript
rule from §59.16 keeps applying unchanged. Each panel carries a
JSON-schema ``configurationSchema`` describing the fields rendered
under it; the schema is intentionally read-only (status panels, not
settings) so the registry rejects any descriptor that would let a
panel mutate state outside the existing capability / policy gate.
"""

from __future__ import annotations


__all__: list[str] = []
"""Diagnostics package public surface.

The diagnostics submodules re-export their own ``__all__``; this
package is a namespace only and exposes nothing directly.
Explicitly pinning ``__all__`` to an empty list documents the
intent: callers reach the panels through
``pi_platform.core.control.diagnostics.v0_8_panels`` rather
than importing from the package root.
"""