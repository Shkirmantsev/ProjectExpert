"""First-start wizard (open spec change PR 11, plan §16–§18, §55, §99).

Covers the ``one-command-production-ux`` spec delta: when the runtime
cache has no model selection (``bootstrap_state == "not-started"``)
the web control plane MUST render a first-start wizard with

* the target repository confirmation,
* the two production embedding models (EmbeddingGemma 2 and
  Qwen3 Embedding 0.6B),
* the execution device choices (auto, CPU, GPU),
* the document-processing (Docling) toggle,

and MUST end with a single "initialise and build search index"
action. The wizard NEVER renders once bootstrap has started or
finished.

The module deliberately stays vendor-neutral: Docling availability is
read through :func:`pi_platform.adapters.pdf.real_docling.is_docling_available`
instead of importing :mod:`docling` directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from pi_platform.adapters.pdf.real_docling import is_docling_available
from pi_platform.core.control.retrieval_settings import (
    DEFAULT_BOOTSTRAP_STATE,
    DEFAULT_DEVICE,
    DEFAULT_DOCUMENT_PROCESSING_ENABLED,
    DEVICE_CHOICES,
    PRODUCTION_ALIAS_TO_MODEL_ID,
    PRODUCTION_MODEL_CHOICES,
    RetrievalSettings,
    load_retrieval_settings,
    normalise_device,
    normalise_model_alias,
)


__all__ = [
    "FirstStartWizard",
    "WizardValidationError",
    "INITIALISE_ACTION",
    "MODEL_LABELS",
]


INITIALISE_ACTION = "initialise_and_build_index"

MODEL_LABELS = {
    "google/embeddinggemma-2": "EmbeddingGemma 2",
    "Qwen/Qwen3-Embedding-0.6B": "Qwen3 Embedding 0.6B",
}


class WizardValidationError(ValueError):
    """Raised when a first-start wizard form submission is invalid."""


class FirstStartWizard:
    """Render and validate the first-start wizard.

    The wizard is stateless: every call reads the current
    :class:`RetrievalSettings` for the target repository, so the
    visible state always reflects the persisted bootstrap state.
    """

    def __init__(
        self,
        *,
        settings_loader: Callable[[Path], RetrievalSettings] | None = None,
    ) -> None:
        self._settings_loader = settings_loader or load_retrieval_settings

    # -- rendering ---------------------------------------------------

    def should_render(self, target_repo: Path) -> bool:
        """``True`` iff the wizard must render for ``target_repo``."""

        settings = self._settings_loader(Path(target_repo))
        return settings.bootstrap_state == "not-started"

    def render(self, target_repo: Path) -> dict[str, Any]:
        """Return the wizard schema for ``target_repo``.

        The schema always carries ``visible``; it is ``True`` only
        when ``bootstrap_state == "not-started"``. When not visible
        the schema reports the blocking state and no action.
        """

        target = Path(target_repo)
        settings = self._settings_loader(target)
        visible = settings.bootstrap_state == "not-started"
        schema: dict[str, Any] = {
            "visible": visible,
            "target_repo": str(target),
            "bootstrap_state": settings.bootstrap_state,
        }
        if not visible:
            schema["action"] = None
            schema["reason"] = (
                f"bootstrap_state is {settings.bootstrap_state!r}; the "
                "first-start wizard only renders before initialisation "
                '("not-started")'
            )
            return schema
        schema.update({
            "model_choices": [
                {
                    "alias": alias,
                    "model_id": model_id,
                    "label": MODEL_LABELS.get(model_id, model_id),
                }
                for alias, model_id in PRODUCTION_ALIAS_TO_MODEL_ID.items()
                if model_id in PRODUCTION_MODEL_CHOICES
            ],
            "device_choices": list(DEVICE_CHOICES),
            "document_processing_enabled": settings.document_processing_enabled,
            "document_processing_available": is_docling_available(),
            "action": INITIALISE_ACTION,
        })
        return schema

    # -- submission --------------------------------------------------

    def submit(self, wizard_form: Mapping[str, Any]) -> RetrievalSettings:
        """Validate a wizard form and return the resulting settings.

        The form accepts the model under ``model`` (alias or full
        model id), ``embedding_model_alias`` or ``model_id``; the
        device under ``device``; the Docling toggle under
        ``document_processing_enabled`` (or ``docling_enabled``);
        and an optional ``bootstrap_state``.

        Raises :class:`WizardValidationError` for an unknown model,
        an unknown device, a non-boolean toggle or a malformed form.
        The returned value is a fully valid
        :class:`RetrievalSettings`; callers persist it with
        :func:`pi_platform.core.control.retrieval_settings.save_retrieval_settings`.
        """

        if not isinstance(wizard_form, Mapping):
            raise WizardValidationError(
                "wizard form must be a mapping, got "
                f"{type(wizard_form).__name__}"
            )
        model = (
            wizard_form.get("model")
            or wizard_form.get("embedding_model_alias")
            or wizard_form.get("model_id")
        )
        if model is None:
            raise WizardValidationError(
                "wizard form is missing the embedding model choice "
                "(expected key 'model')"
            )
        alias = self._resolve_model_alias(model)
        device = self._resolve_device(
            wizard_form.get("device", DEFAULT_DEVICE)
        )
        document_processing = wizard_form.get(
            "document_processing_enabled",
            wizard_form.get(
                "docling_enabled", DEFAULT_DOCUMENT_PROCESSING_ENABLED,
            ),
        )
        if not isinstance(document_processing, bool):
            raise WizardValidationError(
                "document_processing_enabled must be a boolean, got "
                f"{type(document_processing).__name__}"
            )
        state = wizard_form.get("bootstrap_state", DEFAULT_BOOTSTRAP_STATE)
        try:
            return RetrievalSettings(
                embedding_model_alias=alias,
                device=device,
                document_processing_enabled=document_processing,
                bootstrap_state=state,
            )
        except ValueError as exc:
            raise WizardValidationError(str(exc)) from exc

    @staticmethod
    def _resolve_model_alias(model: Any) -> str:
        try:
            return normalise_model_alias(model)
        except ValueError as exc:
            raise WizardValidationError(
                f"unknown model {model!r}; expected one of "
                f"{list(PRODUCTION_MODEL_CHOICES)}"
            ) from exc

    @staticmethod
    def _resolve_device(device: Any) -> str:
        try:
            return normalise_device(device)
        except ValueError as exc:
            raise WizardValidationError(
                f"unknown device {device!r}; expected one of "
                f"{list(DEVICE_CHOICES)}"
            ) from exc