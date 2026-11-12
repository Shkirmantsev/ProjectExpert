"""Semantic indexing service (open spec change PR 5, plan §24–§26).

Covers the ``semantic-index-service`` spec delta: persisted vector
records are the authoritative embedding storage, each embedding
profile owns exactly one vector namespace, only missing vectors are
computed, unchanged retrieval text always reuses its stored vector,
and switching the embedding model reuses existing source and chunk
knowledge while building or reusing the selected profile's
namespace.

The service is intentionally small: it accepts a list of
:class:`ActiveChunk` records (each carrying the canonical
``chunk_id``, ``content_hash``, ``retrieval_text`` and
``retrieval_text_hash`` produced upstream by the ingestion
pipeline), looks up the persisted :class:`VectorRecord` for every
chunk under the active embedding profile, embeds only the misses
through :meth:`EmbeddingModelPort.embed_request` with
``role=DOCUMENT``, persists the new records, adds them to the
USearch dense index, and produces the deterministic
``source_generation`` that the rest of the pipeline uses for atomic
generation activation.

The service deliberately does not own chunk discovery, parsing or
retrieval-text generation; those are upstream concerns. It also
does not own the Git snapshot, branch reconciliation or model
switching; those are downstream concerns that consume the
``source_generation`` this service produces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from typing import Callable, Iterable, Mapping, Sequence

from pi_platform.adapters.runtime.sqlite_vector_record_store import (
    encode_vector_payload,
)
from pi_platform.adapters.runtime.usearch_dense_index import (
    ANNIndexError,
    DenseKeyStore,
    USearchDenseIndex,
    compute_source_generation,
)
from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
    EmbeddingRequest,
    EmbeddingRole,
    EmbeddingTask,
)
from pi_platform.ports.retrieval.embedding_profile import EmbeddingProfile
from pi_platform.ports.runtime.vector_record_store import (
    VectorRecord,
    VectorRecordStorePort,
    VectorRecordStoreError,
)


__all__ = [
    "ActiveChunk",
    "IndexingReport",
    "SemanticIndexService",
    "SemanticIndexServiceError",
    "CrossProfileInsertRejected",
    "CountingEmbeddingModel",
    "InMemoryVectorRecordStore",
]


class SemanticIndexServiceError(RuntimeError):
    """Raised when the semantic index service cannot satisfy a request."""


class CrossProfileInsertRejected(SemanticIndexServiceError):
    """Raised when a vector under profile B is inserted into namespace A.

    The error is the only place where the cross-profile detection is
    surfaced. The error message MUST NOT leak the offending text or
    the chunk content beyond the involved identities (plan §25).
    """

    def __init__(self, *, target_profile: str, source_profile: str) -> None:
        super().__init__(
            f"vector with profile identity {source_profile[:8]}... "
            f"rejected from namespace of profile identity "
            f"{target_profile[:8]}... (redacted)"
        )
        self.target_profile = target_profile
        self.source_profile = source_profile


@dataclass(frozen=True)
class ActiveChunk:
    """One active chunk that should appear in the dense index.

    The service treats ``retrieval_text_hash`` as the authoritative
    reuse key: a chunk whose persisted vector record was produced
    from the same retrieval-text hash is reused without re-embedding;
    any change in retrieval-text hash forces a fresh embedding even
    if ``content_hash`` is also unchanged (the source code may have
    changed in ways that do not affect the retrieval-relevant text,
    e.g. only a comment was edited; in that case ``content_hash``
    changes but ``retrieval_text_hash`` does not, and the stored
    vector is still valid).
    """

    chunk_id: str
    content_hash: str
    retrieval_text: str
    retrieval_text_hash: str
    metadata: Mapping[str, object] = field(default_factory=dict)
    embedding_segments: tuple[str, ...] = ()
    image_path: str | None = None


@dataclass(frozen=True)
class IndexingReport:
    """The result of one :meth:`SemanticIndexService.embed_active_chunks` call.

    ``source_generation`` is the deterministic generation identifier
    the rest of the pipeline uses for atomic index activation
    (plan §29, §42). ``expected_vector_count`` is the number of
    chunks the service processed and MUST equal
    ``len(dense_index.stats()['vectors'])`` after a successful
    activation.
    """

    reused_count: int
    embedded_count: int
    skipped_count: int
    source_generation: str
    expected_vector_count: int
    persisted_chunk_ids: tuple[str, ...] = ()
    removed_chunk_ids: tuple[str, ...] = ()


class CountingEmbeddingModel(EmbeddingModelPort):
    """Test double recording how many embedding calls happen.

    The production :class:`SemanticIndexService` accepts any
    :class:`EmbeddingModelPort`; tests inject this double to assert
    that the reuse key actually prevents re-embedding.
    """

    def __init__(
        self,
        *,
        profile: EmbeddingProfile,
        vectors: Mapping[str, Sequence[float]] | None = None,
    ) -> None:
        self._profile = profile
        self._vectors: dict[str, list[float]] = {
            cid: list(v) for cid, v in (vectors or {}).items()
        }
        self.embed_calls: list[tuple[str, str]] = []
        self.embed_request_calls: list[EmbeddingRequest] = []

    def embed(self, text: str) -> Sequence[float]:
        self.embed_calls.append(("legacy", text))
        return self._deterministic_vector(text)

    def embed_batch(
        self, texts: Sequence[str],
    ) -> Sequence[Sequence[float]]:
        self.embed_calls.extend(("legacy_batch", t) for t in texts)
        return [self._deterministic_vector(t) for t in texts]

    def embed_request(self, request: EmbeddingRequest) -> Sequence[float]:
        self.embed_request_calls.append(request)
        return self._deterministic_vector(request.text)

    def embed_requests(
        self, requests: Sequence[EmbeddingRequest],
    ) -> Sequence[Sequence[float]]:
        self.embed_request_calls.extend(requests)
        return [self._deterministic_vector(r.text) for r in requests]

    def dimension(self) -> int:
        return self._profile.output_dimension

    def model_version(self) -> str:
        return self._profile.identity()

    def license_id(self) -> str:
        return "Apache-2.0"

    def profile(self) -> EmbeddingProfile:
        return self._profile

    def stats(self) -> Mapping[str, int]:
        return {
            "calls_legacy": len(self.embed_calls),
            "calls_request": len(self.embed_request_calls),
        }

    def _deterministic_vector(self, text: str) -> list[float]:
        if text in self._vectors:
            return list(self._vectors[text])
        # Deterministic unit-norm vector derived from a SHA-256 of
        # the text; ensures identical input produces identical
        # output across runs.
        import hashlib
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        out: list[float] = []
        for i in range(self._profile.output_dimension):
            byte = digest[i % len(digest)]
            # Map to [-1, 1] with deterministic offset per index.
            offset = ((byte + i * 17) % 256) / 255.0
            out.append(offset * 2.0 - 1.0)
        # L2 normalise so downstream cosine maths behaves.
        norm = sum(x * x for x in out) ** 0.5 or 1.0
        return [x / norm for x in out]


class InMemoryVectorRecordStore(VectorRecordStorePort):
    """Test double for :class:`VectorRecordStorePort`.

    Stores vectors in a plain dict; key collisions on
    ``(chunk_id, profile_hash)`` overwrite (matching the SQLite
    semantics documented in the port).
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], VectorRecord] = {}

    def put(self, record: VectorRecord) -> None:
        self._records[
            (record.chunk_id, record.embedding_profile_hash)
        ] = record

    def get(
        self, chunk_id: str, embedding_profile_hash: str,
    ) -> VectorRecord | None:
        return self._records.get((chunk_id, embedding_profile_hash))

    def delete(self, chunk_id: str, embedding_profile_hash: str) -> None:
        self._records.pop((chunk_id, embedding_profile_hash), None)

    def iter(
        self, embedding_profile_hash: str,
    ) -> Iterable[VectorRecord]:
        for (cid, prof), rec in self._records.items():
            if prof == embedding_profile_hash:
                yield rec

    def profile_hash_for(self, chunk_id: str) -> str | None:
        for (cid, prof), rec in self._records.items():
            if cid == chunk_id:
                return prof
        return None

    def stats(self) -> Mapping[str, int]:
        return {
            "records": len(self._records),
            "profile_hashes": len(
                {prof for _, prof in self._records.keys()}
            ),
        }


class SemanticIndexService:
    """Persistent semantic indexing service.

    The service combines a role-aware :class:`EmbeddingModelPort`,
    a :class:`VectorRecordStorePort` (the authoritative storage)
    and a :class:`USearchDenseIndex` (the disposable ANN index) to
    build or reuse the active profile's namespace. It is the single
    entry point :func:`build_production_retrieval_runtime` and the
    reconcile loop use to apply a chunk diff.

    The service keeps the embedding model call site explicit: only
    ``role=DOCUMENT`` requests are issued through this service so
    the asymmetric retrieval prompt policy (plan §9.3) stays inside
    the adapter. The query-side prompt is owned by the multi-stage
    retrieval port.
    """

    def __init__(
        self,
        *,
        embedding_model: EmbeddingModelPort,
        vector_record_store: VectorRecordStorePort,
        dense_index: USearchDenseIndex,
        dense_key_store: DenseKeyStore | None = None,
        batch_size: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        if batch_size is None:
            batch_size = 32 if os.environ.get("PI_EMBED_BATCHING", "0") == "1" else 1
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._batch_size = batch_size
        self._progress_callback = progress_callback
        self._embedding_model = embedding_model
        self._vector_record_store = vector_record_store
        self._dense_index = dense_index
        self._dense_key_store = dense_key_store
        self._embedding_profile = (
            embedding_model.profile()
            if hasattr(embedding_model, "profile")
            else None
        )
        if self._embedding_profile is None:
            raise SemanticIndexServiceError(
                "SemanticIndexService requires an embedding model that "
                "exposes an EmbeddingProfile via profile(); the chosen "
                "model does not."
            )
        self._embedding_profile_hash = self._embedding_profile.identity()
        # Init-time namespace validation: refuse to construct a
        # service whose dense index lives under a different profile
        # identity. The check is the structural guard the
        # cross-profile insert scenario in the spec relies on; the
        # per-insert guard further down is a runtime tripwire that
        # should never trigger in production.
        if (
            self._dense_index.embedding_profile_hash
            != self._embedding_profile_hash
        ):
            raise CrossProfileInsertRejected(
                target_profile=self._dense_index.embedding_profile_hash,
                source_profile=self._embedding_profile_hash,
            )

    def set_progress_callback(self, callback: Callable[[int, int], None] | None) -> None:
        """Report completed chunks only after durable vectors and dense insertion."""
        self._progress_callback = callback

    @property
    def embedding_profile_hash(self) -> str:
        return self._embedding_profile_hash

    def embed_active_chunks(
        self,
        chunks: Sequence[ActiveChunk],
    ) -> IndexingReport:
        """Embed (or reuse) the given chunks and return the report.

        The method never embeds a chunk whose persisted vector record
        already matches the chunk's ``retrieval_text_hash`` under
        the active embedding profile identity. New or changed chunks
        are embedded through the role-aware
        :meth:`EmbeddingModelPort.embed_request` with
        :attr:`EmbeddingRole.DOCUMENT`, persisted to the
        :class:`VectorRecordStorePort` and added to the dense index.

        The caller is responsible for committing the dense index and
        for atomically renaming the index file into place
        (:meth:`USearchDenseIndex._atomic_save`); this service only
        returns the deterministic ``source_generation`` that the
        commit step is supposed to use.
        """

        if not isinstance(chunks, Sequence):
            chunks = list(chunks)
        if not chunks:
            return IndexingReport(
                reused_count=0,
                embedded_count=0,
                skipped_count=0,
                source_generation=self._dense_index._source_generation,
                expected_vector_count=0,
                persisted_chunk_ids=(),
                removed_chunk_ids=(),
            )

        profile_hash = self._embedding_profile_hash
        reused: list[str] = []
        embedded: list[str] = []
        skipped: list[str] = []
        retrieval_text_hashes: list[str] = []
        active_chunk_ids: list[str] = []
        seen_chunk_ids: set[str] = set()

        unique_chunks = []
        for chunk in chunks:
            if not chunk.chunk_id or not chunk.retrieval_text or not chunk.retrieval_text_hash:
                raise SemanticIndexServiceError("ActiveChunk requires chunk_id, retrieval_text and retrieval_text_hash")
            if chunk.chunk_id in seen_chunk_ids:
                skipped.append(chunk.chunk_id)
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            active_chunk_ids.append(chunk.chunk_id)
            retrieval_text_hashes.append(chunk.retrieval_text_hash)
            unique_chunks.append(chunk)

        for start in range(0, len(unique_chunks), self._batch_size):
            batch = unique_chunks[start:start + self._batch_size]
            lookup = getattr(self._vector_record_store, "get_many", None)
            if lookup is not None:
                cached = lookup([chunk.chunk_id for chunk in batch], profile_hash)
            else:
                cached = {chunk.chunk_id: self._vector_record_store.get(chunk.chunk_id, profile_hash)
                          for chunk in batch}
            misses = []
            ready = []
            for chunk in batch:
                record = cached.get(chunk.chunk_id)
                vector = None
                if (record is not None
                    and record.chunk_id == chunk.chunk_id
                    and record.embedding_profile_hash == profile_hash
                    and record.created_from_retrieval_text_hash == chunk.retrieval_text_hash
                    and record.dimension == self._embedding_profile.output_dimension
                    and record.model_revision == self._embedding_profile.model_revision
                    and record.normalization == self._embedding_profile.normalization):
                    try:
                        vector = self._validate_vector(decode_vector_payload(record.vector_payload), chunk.chunk_id)
                    except (SemanticIndexServiceError, VectorRecordStoreError, ValueError):
                        vector = None
                if vector is None:
                    misses.append(chunk)
                else:
                    ready.append((chunk, vector))
                    reused.append(chunk.chunk_id)

            # Keep segment ownership explicit while flattening requests; every
            # segment is validated before its chunk's mean-pool projection.
            requests = []
            spans = []
            for chunk in misses:
                texts = chunk.embedding_segments or (chunk.retrieval_text,)
                spans.append((len(requests), len(texts)))
                requests.extend(EmbeddingRequest(text=text, role=EmbeddingRole.DOCUMENT,
                    task=EmbeddingTask.SEARCH, image_path=chunk.image_path) for text in texts)
            vectors = []
            try:
                for offset in range(0, len(requests), self._batch_size):
                    group = requests[offset:offset + self._batch_size]
                    result = self._embedding_model.embed_requests(group)
                    if len(result) != len(group):
                        raise SemanticIndexServiceError("embedding batch returned incompatible cardinality")
                    vectors.extend(result)
            except EmbeddingModelError as exc:
                raise SemanticIndexServiceError(f"embedding model raised for batch: {exc}") from exc
            records = []
            for chunk, (offset, count) in zip(misses, spans):
                parts = [self._validate_vector(vector, chunk.chunk_id)
                         for vector in vectors[offset:offset + count]]
                vector = parts[0]
                if count > 1:
                    vector = [sum(values) / count for values in zip(*parts)]
                    norm = sum(value * value for value in vector) ** 0.5
                    if not math.isfinite(norm) or norm == 0:
                        raise SemanticIndexServiceError("PDF projection returned a non-finite or zero vector")
                    vector = [value / norm for value in vector]
                vector = self._validate_vector(vector, chunk.chunk_id)
                records.append(VectorRecord(
                    chunk_id=chunk.chunk_id, content_hash=chunk.content_hash,
                    embedding_profile_hash=profile_hash,
                    model_revision=self._embedding_profile.model_revision,
                    dimension=len(vector), normalization=self._embedding_profile.normalization,
                    vector_payload=encode_vector_payload(vector, dtype="f"),
                    created_from_retrieval_text_hash=chunk.retrieval_text_hash,
                ))
                ready.append((chunk, vector))
            # Validate the complete response before persisting anything in this
            # batch. No transaction is open during model/HTTP work.
            put_many = getattr(self._vector_record_store, "put_many", None)
            if put_many is not None:
                put_many(records)
            else:
                for record in records:
                    self._vector_record_store.put(record)
            for chunk, vector in ready:
                if self._dense_index.embedding_profile_hash != profile_hash:
                    raise CrossProfileInsertRejected(target_profile=self._dense_index.embedding_profile_hash,
                                                     source_profile=profile_hash)
                self._dense_index.delete_chunk(chunk.chunk_id)
                try:
                    self._dense_index.index_chunk(chunk.chunk_id, vector, dict(chunk.metadata))
                except ANNIndexError as exc:
                    raise SemanticIndexServiceError(f"dense index rejected chunk {chunk.chunk_id!r}") from exc
            embedded.extend(chunk.chunk_id for chunk in misses)
            if self._progress_callback is not None:
                self._progress_callback(start + len(batch), len(unique_chunks))

        # Compute the deterministic generation identifier. The
        # generation includes every chunk id and retrieval text
        # hash, so any change (added / removed / modified chunk)
        # forces a new generation.
        new_generation = compute_source_generation(
            active_chunk_ids,
            retrieval_text_hashes=retrieval_text_hashes,
            embedding_profile_hash=profile_hash,
        )

        # Count validation: the dense index MUST contain exactly
        # ``len(active_chunk_ids)`` vectors for the activation to
        # be valid. If the count is off the service raises so the
        # caller can keep the previous generation active (the
        # caller does NOT activate the failed generation).
        dense_vector_count = int(
            self._dense_index.stats().get("vectors", 0)
        )
        if dense_vector_count != len(active_chunk_ids):
            raise SemanticIndexServiceError(
                f"count validation failed: dense index holds "
                f"{dense_vector_count} vectors but {len(active_chunk_ids)} "
                f"active chunks were processed; previous generation "
                f"remains active"
            )

        return IndexingReport(
            reused_count=len(reused),
            embedded_count=len(embedded),
            skipped_count=len(skipped),
            source_generation=new_generation,
            expected_vector_count=len(active_chunk_ids),
            persisted_chunk_ids=tuple(active_chunk_ids),
            removed_chunk_ids=(),
        )

    def _validate_vector(self, vector: Sequence[float], chunk_id: str) -> list[float]:
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in vector):
            raise SemanticIndexServiceError(f"embedding for chunk {chunk_id!r} contains invalid values")
        values = [float(value) for value in vector]
        if len(values) != self._embedding_profile.output_dimension:
            raise SemanticIndexServiceError(f"embedding for chunk {chunk_id!r} has incompatible dimensions")
        if not all(math.isfinite(value) for value in values):
            raise SemanticIndexServiceError(f"embedding for chunk {chunk_id!r} is not finite")
        squared_norm = sum(value * value for value in values)
        if self._embedding_profile.normalization == "l2" and abs(squared_norm - 1.0) > 0.02:
            raise SemanticIndexServiceError(f"embedding for chunk {chunk_id!r} is not normalized")
        return values

    def remove_chunks(self, chunk_ids: Sequence[str]) -> tuple[str, ...]:
        """Remove the given chunks from both the dense index and the
        vector store.

        Used by the reconcile loop to enforce the
        "removed chunk is no longer searchable" contract
        (open spec change PR 8). The method is idempotent: removing
        an unknown chunk is a no-op.
        """

        removed: list[str] = []
        for chunk_id in chunk_ids:
            if not chunk_id:
                continue
            record = self._vector_record_store.get(
                chunk_id, self._embedding_profile_hash,
            )
            if record is not None:
                self._vector_record_store.delete(
                    chunk_id, self._embedding_profile_hash,
                )
                removed.append(chunk_id)
            # Always attempt the dense delete so the index is
            # consistent even if the vector store was already
            # empty (e.g. after a partial restart).
            try:
                self._dense_index.delete_chunk(chunk_id)
            except Exception:  # noqa: BLE001
                # delete_chunk is idempotent in the adapter, but
                # if a backend raises we still want to record the
                # removal in the next reconcile cycle.
                pass
        return tuple(removed)


def decode_vector_payload(blob: bytes, *, dtype: str = "f") -> list[float]:
    """Decode a vector payload BLOB (mirrors
    :func:`pi_platform.adapters.runtime.sqlite_vector_record_store.decode_vector_payload`)."""

    from pi_platform.adapters.runtime.sqlite_vector_record_store import (
        decode_vector_payload as _impl,
    )
    return _impl(blob, dtype=dtype)
