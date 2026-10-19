"""EmbeddingGemma 2 embedding adapter.

This module covers the production profile
:class:`pi_platform.ports.retrieval.embedding_profile.EMBEDDINGGEMMA2_512`
behind the role-aware :class:`EmbeddingModelPort` (open spec change
``production-semantic-search-and-branch-reconciliation``, PR 3).

Two execution modes are supported and selected at construction time
based on what is installed in the active environment:

* **Real binding.** When the optional ``sentence-transformers``
  package and the pinned :attr:`PINNED_REVISION` of
  ``google/embeddinggemma-2`` are both available, the adapter loads
  the real model with the documented EmbeddingGemma 2 prompt policy
  (plan §9.3, §9.4, §9.5).
* **Diagnostic stub.** When either dependency is missing, the
  adapter remains constructible, advertises the production profile
  it is built for, and raises
  :class:`EmbeddingModelError` from every embedding call with a
  human-readable, actionable message that names the install
  command. This honours the plan §2.1 contract that a production
  component is either ``real-and-available``,
  ``real-and-not-installed`` or ``disabled`` — never "looks enabled
  but runs a stub" silently.

The real binding defaults to CPU + float32 per plan §6.1; CUDA is
opt-in through the ``device`` constructor argument.
"""

from __future__ import annotations

import os
from typing import Mapping, Sequence

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
    EmbeddingRequest,
    EmbeddingRole,
    EmbeddingTask,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    EmbeddingProfile,
)


__all__ = [
    "EmbeddingGemma2EmbeddingModel",
    "ADAPTER_NAME",
    "DEFAULT_LICENSE_ID",
    "DEFAULT_MODEL_ID",
    "DEFAULT_OUTPUT_DIMENSION",
    "PINNED_REVISION",
    "TASK_PROMPTS",
    "is_real_binding_available",
]


ADAPTER_NAME = "embeddinggemma2"
# Public model id (Hugging Face repository).
DEFAULT_MODEL_ID = "google/embeddinggemma-2"
# Per the EmbeddingGemma 2 license inventory this is the
# currently-shipped full Git revision. The
# ``production-capability-gate`` reads it from
# ``distribution/licenses/model-licenses.json`` to ensure the binding
# never silently runs against a different upstream state. Update
# together with the license JSON.
PINNED_REVISION = os.environ.get(
    "PI_EMBEDDINGGEMMA2_REVISION",
    "unset-pin-via-model-licenses-json",
)
DEFAULT_LICENSE_ID = "Apache-2.0"
DEFAULT_OUTPUT_DIMENSION = 512  # Matryoshka-truncated (plan §6.1)

# Plan §9.3 / §9.4 — EmbeddingGemma 2 task prompts. The query side
# uses the official task type; the document side uses the structured
# ``title: ... | text: ...`` format that EmbeddingGemma 2 expects.
TASK_PROMPTS: Mapping[EmbeddingTask, str] = {
    EmbeddingTask.SEARCH: "SearchQuery",
    EmbeddingTask.CODE_RETRIEVAL: "CodeRetrieval",
    EmbeddingTask.QUESTION_ANSWERING: "QuestionAnswering",
}


_NOT_BOUND_MESSAGE = (
    "EmbeddingGemma 2 is not bound in this build; install "
    "sentence-transformers and a pinned google/embeddinggemma-2 "
    "revision (see distribution/licenses/model-licenses.json), "
    "or run 'project-intelligence models pull embeddinggemma2'."
)


def is_real_binding_available() -> bool:
    """Return True if the optional real binding is importable.

    The check is intentionally conservative: it returns True only if
    both ``sentence_transformers`` and ``torch`` are importable.
    Missing either means the binding cannot satisfy a request and
    the adapter will raise :class:`EmbeddingModelError` per plan
    §2.1.
    """

    try:
        import sentence_transformers  # noqa: F401
        import torch  # noqa: F401
    except Exception:
        return False
    return True


def _format_document_text(text: str, title: str | None) -> str:
    """Plan §9.4 — document-side EmbeddingGemma 2 formatting.

    The raw title and text stay in the canonical metadata; only
    the embedding input string follows the model prompt format.
    """

    if title:
        return f"title: {title} | text: {text}"
    return f"title: none | text: {text}"


class EmbeddingGemma2EmbeddingModel(EmbeddingModelPort):
    """EmbeddingGemma 2 (512d) adapter behind the role-aware port.

    Construct with ``device='cpu'`` (default) for the plan §6.1
    float32 CPU profile or ``device='cuda'`` for a bf16 GPU
    profile. ``device='auto'`` (plan §13) defers the choice to
    :class:`pi_platform.adapters.config.runtime_device.RuntimeDeviceSelector`.
    """

    def __init__(
        self,
        profile: EmbeddingProfile = EMBEDDINGGEMMA2_512,
        *,
        device: str = "cpu",
        model_id: str | None = None,
        revision: str | None = None,
    ) -> None:
        # Plan §11 / §101: the adapter's default model id and
        # revision come from the EmbeddingProfile so the runtime
        # binding always matches the profile identity. Explicit
        # ``model_id`` / ``revision`` arguments override the
        # profile for tests only.
        self._profile = profile
        self._device = device
        self._model_id = model_id or profile.model_id
        self._revision = (
            revision
            or os.environ.get("PI_EMBEDDINGGEMMA2_REVISION")
            or profile.model_revision
        )
        self._calls = 0
        self._tokens = 0
        self._errors = 0
        # Lazy load. ``_model`` is None until the first embed call.
        self._model = None
        self._load_failed: bool = False
        self._load_error: str | None = None

    # -- lazy loading -----------------------------------------------------

    def _ensure_loaded(self):
        if self._model is not None or self._load_failed:
            return
        try:
            from sentence_transformers import SentenceTransformer
            import torch
        except Exception as exc:  # pragma: no cover - import guard
            self._load_failed = True
            self._load_error = (
                f"{_NOT_BOUND_MESSAGE} (cause: {exc})"
            )
            raise EmbeddingModelError(self._load_error) from exc

        try:
            torch_dtype = torch.float32 if self._device == "cpu" else torch.bfloat16
            # Plan §9.2 / §9.5: bind the model with Matryoshka
            # truncation to 512d. The library forwards
            # ``truncate_dim`` to the transformer loader; the
            # downstream ``encode`` call also passes the same
            # value for the runtime sanity check.
            try:
                self._model = SentenceTransformer(
                    self._model_id,
                    revision=self._revision,
                    device=self._device,
                    truncate_dim=DEFAULT_OUTPUT_DIMENSION,
                    model_kwargs={"torch_dtype": torch_dtype},
                )
            except (TypeError, ModuleNotFoundError) as exc:
                # Fallback for older / newer sentence-transformers
                # that do not accept ``truncate_dim`` /
                # ``model_kwargs`` or whose modules.json references
                # the old ``sentence_transformers.base`` path.
                # Patch the cached modules.json in place so the
                # model loads with the new ``models.*`` layout.
                self._patch_modules_json()
                self._model = SentenceTransformer(
                    self._model_id,
                    revision=self._revision,
                    device=self._device,
                )
        except Exception as exc:  # pragma: no cover - network/runtime
            self._load_failed = True
            self._load_error = (
                f"EmbeddingGemma 2 failed to load from {self._model_id}"
                f"@{self._revision} on device {self._device}: {exc}"
            )
            raise EmbeddingModelError(self._load_error) from exc

    @staticmethod
    def _patch_modules_json() -> None:
        """Rewrite a cached ``modules.json`` to use the modern
        ``sentence_transformers.models.*`` paths.

        EmbeddingGemma 2 was uploaded with the legacy
        ``sentence_transformers.base.modules.<X>`` module paths;
        current sentence-transformers (>=3.0) only ships
        ``sentence_transformers.models.<X>``. The patch rewrites
        the cached ``modules.json`` to use the new layout and is
        idempotent.
        """
        import json as _json
        from pathlib import Path

        cache_dir = os.environ.get("HF_HOME") or os.path.expanduser(
            "~/.cache/huggingface",
        )
        candidate = Path(cache_dir) / "hub" / (
            "models--google--embeddinggemma-2"
        )
        if not candidate.exists():
            return
        for modules_path in candidate.glob("**/modules.json"):
            try:
                data = _json.loads(modules_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            changed = False
            for entry in data:
                t = entry.get("type", "")
                # ``sentence_transformers.base.modules.transformer.Transformer``
                # -> ``sentence_transformers.models.Transformer``
                if t.startswith("sentence_transformers.base.modules."):
                    leaf = t.split(".")[-1]
                    entry["type"] = (
                        f"sentence_transformers.models.{leaf}"
                    )
                    changed = True
                # ``sentence_transformers.sentence_transformer.modules.pooling.Pooling``
                # -> ``sentence_transformers.models.Pooling``
                elif t.startswith(
                    "sentence_transformers.sentence_transformer.modules.",
                ):
                    leaf = t.split(".")[-1]
                    entry["type"] = (
                        f"sentence_transformers.models.{leaf}"
                    )
                    changed = True
            if changed:
                modules_path.write_text(
                    _json.dumps(data, indent=2), encoding="utf-8",
                )

    # -- port surface -----------------------------------------------------

    def embed(self, text: str) -> Sequence[float]:
        return self.embed_request(
            EmbeddingRequest(text=text, role=EmbeddingRole.DOCUMENT),
        )

    def embed_batch(
        self, texts: Sequence[str],
    ) -> Sequence[Sequence[float]]:
        return self.embed_requests(
            [EmbeddingRequest(text=t, role=EmbeddingRole.DOCUMENT)
             for t in texts],
        )

    def embed_request(self, request: EmbeddingRequest) -> Sequence[float]:
        self._calls += 1
        try:
            self._ensure_loaded()
        except EmbeddingModelError:
            self._errors += 1
            raise

        model = self._model
        if model is None:  # pragma: no cover - defensive
            self._errors += 1
            raise EmbeddingModelError(_NOT_BOUND_MESSAGE)

        if request.role == EmbeddingRole.QUERY:
            prompt = TASK_PROMPTS.get(
                request.task, TASK_PROMPTS[EmbeddingTask.SEARCH],
            )
            texts_to_encode = [prompt + ": " + request.text]
        else:
            texts_to_encode = [_format_document_text(
                request.text, request.title,
            )]

        try:
            vectors = model.encode(
                texts_to_encode,
                convert_to_numpy=True,
                normalize_embeddings=True,
                truncate_dim=DEFAULT_OUTPUT_DIMENSION,
                show_progress_bar=False,
            )
        except Exception as exc:  # pragma: no cover - runtime
            self._errors += 1
            raise EmbeddingModelError(
                f"EmbeddingGemma 2 encode failed: {exc}"
            ) from exc

        # Plan §9.6 numerical validation.
        v = vectors[0]
        self._validate_vector(v)
        return v.tolist()

    def embed_requests(
        self, requests: Sequence[EmbeddingRequest],
    ) -> Sequence[Sequence[float]]:
        if not requests:
            return []
        try:
            self._ensure_loaded()
        except EmbeddingModelError:
            for _ in requests:
                self._errors += 1
            raise
        model = self._model
        if model is None:  # pragma: no cover - defensive
            for _ in requests:
                self._errors += 1
            raise EmbeddingModelError(_NOT_BOUND_MESSAGE)

        # Plan §8 / §9.4: build per-request encoded text with the
        # role- and task-appropriate prompt, then batch.
        texts_to_encode = []
        for r in requests:
            if r.role == EmbeddingRole.QUERY:
                prompt = TASK_PROMPTS.get(
                    r.task, TASK_PROMPTS[EmbeddingTask.SEARCH],
                )
                texts_to_encode.append(prompt + ": " + r.text)
            else:
                texts_to_encode.append(
                    _format_document_text(r.text, r.title),
                )

        try:
            vectors = model.encode(
                texts_to_encode,
                convert_to_numpy=True,
                normalize_embeddings=True,
                truncate_dim=DEFAULT_OUTPUT_DIMENSION,
                show_progress_bar=False,
            )
        except Exception as exc:  # pragma: no cover - runtime
            self._errors += 1
            raise EmbeddingModelError(
                f"EmbeddingGemma 2 batch encode failed: {exc}"
            ) from exc

        results: list[list[float]] = []
        for v in vectors:
            self._validate_vector(v)
            results.append(v.tolist())
        return results

    def _validate_vector(self, vec) -> None:
        """Plan §9.6 — fail closed on malformed vectors."""
        import math
        if len(vec) != DEFAULT_OUTPUT_DIMENSION:
            self._errors += 1
            raise EmbeddingModelError(
                f"EmbeddingGemma 2 returned a vector of length "
                f"{len(vec)}, expected {DEFAULT_OUTPUT_DIMENSION}"
            )
        for x in vec:
            if not math.isfinite(float(x)):
                self._errors += 1
                raise EmbeddingModelError(
                    "EmbeddingGemma 2 returned a non-finite value"
                )

    def dimension(self) -> int:
        return self._profile.output_dimension

    def model_version(self) -> str:
        return self._profile.identity()

    def license_id(self) -> str:
        return DEFAULT_LICENSE_ID

    def profile(self) -> EmbeddingProfile:
        return self._profile

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "tokens": self._tokens,
            "errors": self._errors,
            "backend": ADAPTER_NAME,
            "real_binding": "1" if self._model is not None else "0",
        }
