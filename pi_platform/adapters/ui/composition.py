"""Composition root for the human UI deployment (architecture §57, §45.1).

Wires the UI service from concrete platform components. This is the only place
that knows which adapter implements which port; the UI domain service depends on
ports exclusively.

Retrieval is served by the runtime cache through a retrieval-only orchestrator:
the UI must answer simple questions without a coding harness and without a
large language model, and it must never fabricate evidence it does not have.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pi_platform.adapters.control.policy_engine import DefaultPolicyEngine
from pi_platform.adapters.fs import LocalFilesystemAdapter
from pi_platform.adapters.git.cli_adapter import GitCliAdapter
from pi_platform.core.canonical import KNOWN_FAMILIES, KnowledgeState, Metadata
from pi_platform.core.control.flags import (
    DefaultFeatureFlagRegistry,
    FeatureFlagContext,
    FeatureFlagScope,
    FeatureFlagState,
)
from pi_platform.core.licensing import LicenseGate, LicensePolicy
from pi_platform.core.retrieval.hybrid_retrieval import HybridRetrievalCore
from pi_platform.core.retrieval.metadata_filter import MetadataFilterCore
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
    RetrievalQuery,
    RetrievalResult,
)
from pi_platform.core.security.egress import DefaultEgressPolicy
from pi_platform.core.sync import (
    HydrateService,
    MaterialiseService,
    PolicyDecisionStub,
    ReconcileService,
    WriteAheadLog,
)
from pi_platform.core.sync.readiness import DefaultKnowledgeReadiness
from pi_platform.core.sync.trusted_approval import (
    ClosedTrustedApprovalBoundary,
    HmacTrustedApprovalBoundary,
)
from pi_platform.core.ui.rest_service import RestService, UiContext
from pi_platform.ports import HydrateReport, ReconcileReport, VersionIdentity
from pi_platform.ports.orchestration.query_orchestrator import (
    OrchestrationLevel,
    OrchestrationResult,
    QueryOrchestratorPort,
)
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit

__all__ = [
    "build_ui_service",
    "build_flag_registry",
    "hydrate_and_reconcile_target",
    "load_persisted_readiness",
    "persist_readiness",
    "is_open_webui_enabled",
    "RetrievalOnlyOrchestrator",
    "CacheBackedHybridRetrieval",
    "OPEN_WEBUI_FLAG",
    "READINESS_STATE_FILENAME",
]

OPEN_WEBUI_FLAG = "open-webui-adapter"
READINESS_STATE_FILENAME = "readiness.json"


class CacheBackedHybridRetrieval(HybridRetrievalCore):
    """Hybrid retrieval over the runtime cache and canonical project knowledge.

    The dense and sparse channels read the runtime SQLite entries, local
    ingestion cache, and canonical ``project-knowledge/`` tree when the
    cache is hydrated. An unhydrated cache yields no hits rather than invented
    ones, and the reason travels with the result as an uncertainty.
    """

    def __init__(
        self,
        cache_root: Path,
        *,
        repo_root: Optional[Path] = None,
        readiness: Optional[DefaultKnowledgeReadiness] = None,
        top_k: int = 10,
    ) -> None:
        self._cache_root = Path(cache_root)
        self._repo_root = Path(repo_root).resolve() if repo_root else None
        self._readiness = readiness
        self._top_k = top_k
        self._reason = ""
        super().__init__(
            dense_query=self._dense_query,
            sparse_query=self._sparse_query,
            exact_lookup=self._exact_lookup,
        )

    @property
    def reason(self) -> str:
        return self._reason

    def _collect_corpus_hits(self) -> list[RetrievalHit]:
        if self._readiness is not None and not self._readiness.is_ready():
            return []
        records: dict[str, RetrievalHit] = {}

        # 1. Runtime SQLite store (runtime.db)
        db_path = self._cache_root / "runtime.db"
        if db_path.is_file():
            try:
                with closing(sqlite3.connect(db_path)) as conn:
                    rows = conn.execute(
                        "SELECT content_hash, family, body_json FROM runtime_entries"
                    ).fetchall()
                for content_hash, family, body_json in rows:
                    try:
                        body = json.loads(body_json)
                    except ValueError:
                        continue
                    hit = _record_to_hit(content_hash, str(family), body)
                    if hit is not None:
                        records[hit.chunkId] = hit
            except sqlite3.Error:
                pass

        # 2. Local ingestion state (ingestion.json)
        ing_path = self._cache_root / "ingestion.json"
        if ing_path.is_file():
            try:
                saved = json.loads(ing_path.read_text(encoding="utf-8"))
                for key, raw in (saved.get("records") or {}).items():
                    try:
                        body = json.loads(raw) if isinstance(raw, str) else raw
                    except ValueError:
                        continue
                    hit = _record_to_hit(str(key), "chunks", body)
                    if hit is not None:
                        records[hit.chunkId] = hit
            except (OSError, ValueError):
                pass

        # 3. Canonical Wiki pages in project-knowledge/wiki
        if self._repo_root is not None:
            wiki_root = self._repo_root / "project-knowledge" / "wiki"
            if wiki_root.is_dir():
                for md_path in sorted(wiki_root.rglob("*.md")):
                    try:
                        text = md_path.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    cid = f"wiki:{md_path.relative_to(wiki_root).as_posix()}"
                    if cid not in records and text.strip():
                        records[cid] = RetrievalHit(
                            chunkId=cid,
                            score=0.5,
                            source="sparse",
                            snippet=text[:1000],
                            contentHash="",
                            metadata=Metadata(
                                documentId=cid,
                                version="0.1.0",
                                language="en",
                            ),
                            knowledgeState=KnowledgeState.VERIFIED,
                            tokenEstimate=max(1, len(text.split())),
                        )
        return list(records.values())

    def _dense_query(self, text: str, limit: int) -> Sequence[Any]:
        corpus = self._collect_corpus_hits()
        if not corpus or not text.strip():
            return ()
        from pi_platform.adapters.retrieval.hashing_embedding_model import (
            HashingEmbeddingAdapter,
        )

        embedder = HashingEmbeddingAdapter(dimension=64)
        q_vec = embedder.embed(text)
        scored: list[tuple[float, RetrievalHit]] = []
        for hit in corpus:
            d_vec = embedder.embed(hit.snippet or hit.chunkId)
            sim = sum(a * b for a, b in zip(q_vec, d_vec))
            if sim > 0.0:
                scored.append((min(max(sim, 0.0), 1.0), hit))
        scored.sort(key=lambda item: (-item[0], item[1].chunkId))
        return tuple(
            RetrievalHit(
                chunkId=h.chunkId,
                score=score,
                source="dense",
                snippet=h.snippet,
                contentHash=h.contentHash,
                metadata=h.metadata,
                knowledgeState=h.knowledgeState,
                tokenEstimate=h.tokenEstimate,
                evidenceWeight=h.evidenceWeight,
            )
            for score, h in scored[: max(1, limit)]
        )

    def _sparse_query(self, text: str, limit: int) -> Sequence[Any]:
        corpus = self._collect_corpus_hits()
        if not corpus or not text.strip():
            return ()
        from pi_platform.adapters.runtime.bm25_sparse_index import Bm25SparseIndex

        index = Bm25SparseIndex()
        by_id: dict[str, RetrievalHit] = {}
        for hit in corpus:
            by_id[hit.chunkId] = hit
            index.index_document(
                "chunks", hit.chunkId, f"{hit.chunkId} {hit.snippet}", {},
            )
        raw_hits = index.query(text, top_k=max(1, limit))
        if not raw_hits:
            return ()
        max_score = max((h.score for h in raw_hits), default=1.0) or 1.0
        out: list[RetrievalHit] = []
        for sh in raw_hits:
            base = by_id[sh.documentId]
            norm_score = min(max(sh.score / max_score, 0.0), 1.0)
            out.append(
                RetrievalHit(
                    chunkId=base.chunkId,
                    score=norm_score,
                    source="sparse",
                    snippet=base.snippet or sh.snippet,
                    contentHash=base.contentHash,
                    metadata=base.metadata,
                    knowledgeState=base.knowledgeState,
                    tokenEstimate=base.tokenEstimate,
                    evidenceWeight=base.evidenceWeight,
                )
            )
        return tuple(out)

    def _exact_lookup(self, identifier: str) -> Sequence[RetrievalHit]:
        corpus = self._collect_corpus_hits()
        if not corpus or not identifier:
            return ()
        matches: list[RetrievalHit] = []
        for hit in corpus:
            if identifier in hit.chunkId or identifier in hit.snippet:
                matches.append(
                    RetrievalHit(
                        chunkId=hit.chunkId,
                        score=1.0,
                        source="exact",
                        snippet=hit.snippet,
                        contentHash=hit.contentHash,
                        metadata=hit.metadata,
                        knowledgeState=hit.knowledgeState,
                        tokenEstimate=hit.tokenEstimate,
                        evidenceWeight=hit.evidenceWeight,
                    )
                )
        return tuple(matches)


def _record_to_hit(
    content_hash: str, family: str, body: Any,
) -> Optional[RetrievalHit]:
    if not isinstance(body, Mapping):
        return None
    chunk_id = str(body.get("id") or body.get("chunkId") or content_hash)
    snippet = str(
        body.get("contextualText")
        or body.get("rawText")
        or body.get("text")
        or body.get("description")
        or body.get("label")
        or ""
    )
    if not snippet:
        return None
    raw_meta = body.get("metadata")
    if isinstance(raw_meta, Mapping):
        meta = Metadata(
            documentId=str(raw_meta.get("documentId") or chunk_id),
            version=str(raw_meta.get("version") or "0.1.0"),
            language=str(raw_meta.get("language") or "und"),
        )
    else:
        meta = Metadata(documentId=chunk_id, version="0.1.0", language="und")
    return RetrievalHit(
        chunkId=chunk_id,
        score=0.5,
        source="sparse",
        snippet=snippet,
        contentHash=str(body.get("contentHash") or content_hash),
        metadata=meta,
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=max(1, len(snippet.split())),
    )


def persist_readiness(
    cache_root: Path, readiness: DefaultKnowledgeReadiness,
) -> Path:
    """Persist the readiness snapshot to ``<cache_root>/readiness.json``."""
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    snap = readiness.snapshot()
    payload = {
        "consistent": bool(snap.consistent),
        "in_progress": bool(snap.in_progress),
        "current_head": str(snap.current_head or ""),
        "working_tree_fingerprint": str(snap.working_tree_fingerprint or ""),
        "last_hydrate_at": int(snap.last_hydrate_at or 0),
        "last_reconcile_at": int(snap.last_reconcile_at or 0),
        "reason": str(snap.reason or ""),
    }
    target = cache_root / READINESS_STATE_FILENAME
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)
    return target


def load_persisted_readiness(
    cache_root: Path, readiness: DefaultKnowledgeReadiness,
) -> bool:
    """Load persisted readiness state from ``<cache_root>/readiness.json`` if present."""
    target = Path(cache_root) / READINESS_STATE_FILENAME
    if not target.is_file():
        return False
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(payload, Mapping):
        return False
    if not payload.get("consistent"):
        reason = str(payload.get("reason") or "")
        if reason:
            readiness.record_failure(reason)
        return False
    head = str(payload.get("current_head") or "")
    fp = str(payload.get("working_tree_fingerprint") or "")
    empty_families = {f: 0 for f in KNOWN_FAMILIES}
    readiness.record_hydrate(
        HydrateReport(
            project_version=VersionIdentity(
                gitHead=head,
                workingTreeFingerprint=fp,
                knowledgeSchemaVersion="0.1.0",
                embeddingModelVersion="unknown",
                indexSchemaVersion="0.1.0",
            ),
            families=empty_families,
            cache_hit_rates={f: 1.0 for f in KNOWN_FAMILIES},
        )
    )
    readiness.record_reconcile(
        ReconcileReport(
            families=empty_families,
            reused_shards=empty_families,
            re_ingested_shards=empty_families,
        ),
        current_head=head,
        working_tree_fingerprint=fp,
    )
    if payload.get("last_hydrate_at"):
        readiness._last_hydrate_at = int(payload["last_hydrate_at"])
    if payload.get("last_reconcile_at"):
        readiness._last_reconcile_at = int(payload["last_reconcile_at"])
    return True


def hydrate_and_reconcile_target(
    repo_root: Path,
    cache_root: Path,
    readiness: DefaultKnowledgeReadiness,
    *,
    lock_held: bool = False,
    persist_state: bool = True,
) -> Optional[HydrateReport]:
    """Hydrate and reconcile ``repo_root`` into ``cache_root`` and mark ``readiness`` ready.

    Fails closed on any hydration/reconciliation error by recording the
    failure reason on ``readiness`` and persisting ``consistent = False`` so
    ``/health/ready`` returns 503.
    """
    import hashlib
    from contextlib import nullcontext
    from pi_platform.core.sync import ProjectLock
    from pi_platform.ports import GitPortError

    repo_root = Path(repo_root).resolve()
    cache_root = Path(cache_root).resolve()
    canonical = str(repo_root).lower()
    lock_id = f"proj-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"
    fs = LocalFilesystemAdapter(repo_root, cache_root=cache_root)
    try:
        with (nullcontext() if lock_held else ProjectLock(lock_id, root=cache_root / "locks").acquire()):
            fs.ensure_cache_root()
            git_exclude = repo_root / ".git" / "info" / "exclude"
            if git_exclude.parent.is_dir():
                try:
                    existing_excl = (
                        git_exclude.read_text(encoding="utf-8")
                        if git_exclude.is_file()
                        else ""
                    )
                    if ".project-intelligence-cache" not in existing_excl:
                        prefix = "" if (not existing_excl or existing_excl.endswith("\n")) else "\n"
                        git_exclude.write_text(
                            existing_excl + prefix + ".project-intelligence-cache/\n",
                            encoding="utf-8",
                        )
                except OSError:
                    pass
            try:
                hydrate_report = HydrateService(filesystem=fs).restore_runtime(
                    repo_root, cache_root=cache_root,
                )
            except GitPortError:
                if (repo_root / ".git").exists():
                    raise
                empty_families = {f: 0 for f in KNOWN_FAMILIES}
                hydrate_report = HydrateReport(
                    project_version=VersionIdentity(
                        gitHead="unversioned",
                        workingTreeFingerprint="",
                        knowledgeSchemaVersion="0.1.0",
                        embeddingModelVersion="unknown",
                        indexSchemaVersion="0.1.0",
                    ),
                    families=empty_families,
                    cache_hit_rates={f: 1.0 for f in KNOWN_FAMILIES},
                )
            head = hydrate_report.project_version.gitHead
            fp = hydrate_report.project_version.workingTreeFingerprint
            previous_head = head
            readiness_file = cache_root / READINESS_STATE_FILENAME
            if readiness_file.is_file():
                try:
                    prev_payload = json.loads(
                        readiness_file.read_text(encoding="utf-8")
                    )
                    if isinstance(prev_payload, Mapping) and prev_payload.get("current_head"):
                        previous_head = str(prev_payload["current_head"])
                except (OSError, ValueError):
                    pass
            try:
                from pi_platform.core.sync.version_snapshot import (
                    RuntimeSnapshotService,
                )

                persisted_snap = RuntimeSnapshotService(
                    cache_root=cache_root
                ).read_snapshot()
                if persisted_snap is not None and persisted_snap.active.head:
                    previous_head = persisted_snap.active.head
            except Exception:
                pass
            reconcile_report = ReconcileService(filesystem=fs).reconcile_branch_switch(
                repo_root,
                previous_head=previous_head,
                current_head=head,
                cache_root=cache_root,
            )
            readiness.record_hydrate(hydrate_report)
            readiness.record_reconcile(
                reconcile_report,
                current_head=head,
                working_tree_fingerprint=fp,
            )
            if persist_state:
                persist_readiness(cache_root, readiness)
            return hydrate_report
    except Exception as exc:
        readiness.record_failure(str(exc))
        try:
            if persist_state:
                persist_readiness(cache_root, readiness)
        except OSError:
            pass
        return None


class RetrievalOnlyOrchestrator(QueryOrchestratorPort):
    """Deterministic orchestration: retrieval plus context assembly only.

    Escalation to a local or external model is intentionally not wired here.
    ``agent-delegation`` remains available through the UI API when an egress
    decision allows it.
    """

    def __init__(self, retrieval: Any) -> None:
        self._retrieval = retrieval
        self._calls = 0

    def orchestrate(
        self,
        query: str,
        *,
        level: Optional[int] = None,
        task_context: object = None,
        filters: object = None,
        project_version: object = None,
    ) -> OrchestrationResult:
        self._calls += 1
        result = self._retrieval.retrieve(
            RetrievalQuery(text=query, filters=filters, projectVersion=project_version)
        )
        return OrchestrationResult(
            level=OrchestrationLevel.RETRIEVAL
            if hasattr(OrchestrationLevel, "RETRIEVAL")
            else list(OrchestrationLevel)[0],
            query=query,
            retrieval=result,
            explanations=("retrieval-only orchestration",),
            budgetUsed=int(getattr(result, "budgetUsed", 0) or 0),
        )

    def escalate(self, orchestration: OrchestrationResult, *, reason: str) -> OrchestrationResult:
        raise NotImplementedError(
            "no local or external model is configured for this deployment"
        )

    def stats(self) -> dict[str, int]:
        return {"queries": self._calls}


def _approval_boundary() -> Any:
    key = os.environ.get("PI_APPROVAL_KEY") or os.environ.get("PI_UI_TOKEN") or ""
    if key:
        return HmacTrustedApprovalBoundary(key=key.encode("utf-8"))
    # Fail closed: without a key no token can be issued or verified, so the
    # materialize operation can never write canonical knowledge.
    return ClosedTrustedApprovalBoundary()


def build_flag_registry() -> DefaultFeatureFlagRegistry:
    """Register the Phase 9 feature flags.

    The OpenAI-compatible shim is enabled by default so the local model
    bundled in ``desktop-lite`` is wired up out of the box. Operators
    disable it per deployment profile by overriding the registry. The
    ``PI_OPEN_WEBUI_ADAPTER`` env var lets operators flip the flag
    without code changes.
    """
    registry = DefaultFeatureFlagRegistry()
    registry.register(
        OPEN_WEBUI_FLAG,
        state=FeatureFlagState.ENABLED,
        scope=FeatureFlagScope.DEPLOYMENT_PROFILE,
    )
    from pi_platform.core.control.multimodal import MULTIMODAL_FIGURES_FLAG

    registry.register(
        MULTIMODAL_FIGURES_FLAG,
        state=FeatureFlagState.EXPERIMENTAL,
        scope=FeatureFlagScope.DEPLOYMENT_PROFILE,
    )
    return registry


def is_open_webui_enabled(
    registry: DefaultFeatureFlagRegistry,
    *,
    deployment_profile: str = "",
    project_version: str = "",
) -> bool:
    """Resolve the Open WebUI flag for the current deployment context."""
    context = FeatureFlagContext(
        deployment_profile=deployment_profile, project_version=project_version
    )
    return registry.resolve(OPEN_WEBUI_FLAG, context=context) is FeatureFlagState.ENABLED


class PublishedRetrieval:
    """One atomic runtime pointer shared by UI, orchestration and MCP."""
    def __init__(self, readiness):
        self.readiness = readiness
        self.runtime = None

    def retrieve(self, query):
        from pi_platform.core.sync.readiness import assert_ready
        assert_ready(self.readiness)
        runtime = self.runtime
        if runtime is None:
            from pi_platform.ports import RuntimeNotReadyError
            from dataclasses import replace
            raise RuntimeNotReadyError(replace(self.readiness.snapshot(), consistent=False, reason="No retrieval generation published"))
        result = runtime.multi_stage_retrieval.retrieve(query)
        assert_ready(self.readiness)
        if runtime is not self.runtime:
            from pi_platform.ports import RuntimeNotReadyError
            from dataclasses import replace
            raise RuntimeNotReadyError(replace(self.readiness.snapshot(), consistent=False, reason="Retrieval generation changed during request"))
        return result

    def stats(self):
        if self.runtime is None:
            return {}
        return {**self.runtime.multi_stage_retrieval.stats(), **self.runtime.stage_report(),
                "source_failures": list(self.runtime.extra.get("source_failures", ())),
                "resolved_configuration": self.runtime.extra.get("resolved_configuration", {})}


def publish_runtime(service, runtime):
    service._retrieval.runtime = runtime
    service._graph = runtime.graph_expansion


def build_ui_service(
    *,
    repo_root: Path,
    cache_root: Optional[Path] = None,
    context: Optional[UiContext] = None,
    hydrate_on_start: bool = False,
    defer_runtime: bool = False,
) -> tuple[RestService, DefaultKnowledgeReadiness]:
    """Build the UI service for a target repository.

    Returns the service and the readiness seam so the caller can record hydrate
    and reconcile outcomes and report readiness separately from liveness.
    """
    repo_root = Path(repo_root)
    cache_root = Path(cache_root) if cache_root else repo_root / ".project-intelligence-cache"

    policy = DefaultPolicyEngine()
    git = GitCliAdapter()
    readiness = DefaultKnowledgeReadiness()
    if hydrate_on_start:
        hydrate_and_reconcile_target(repo_root, cache_root, readiness)
    else:
        load_persisted_readiness(cache_root, readiness)

    approval = _approval_boundary()
    egress = DefaultEgressPolicy(_policy_engine=policy)
    # ``MaterialiseService`` must share the same trusted approval boundary
    # that ``RestService`` uses to verify tokens. Otherwise a correctly
    # signed UI token would pass ``RestService.verify`` but be rejected by
    # the materialiser's default ``ClosedTrustedApprovalBoundary`` (§48).
    materialise = MaterialiseService(
        filesystem=LocalFilesystemAdapter(repo_root, cache_root=cache_root),
        wal=WriteAheadLog(cache_root),
        policy=PolicyDecisionStub(),
        license_gate=LicenseGate(LicensePolicy()),
        boundary=approval,
    )
    from pi_platform.adapters.ui.projections import build_read_projections
    projections = build_read_projections(repo_root=repo_root, cache_root=cache_root, git=git)
    retrieval = PublishedRetrieval(readiness)
    orchestrator = RetrievalOnlyOrchestrator(retrieval)
    try:
        from pi_platform.adapters.orchestration.capability_discovery import (
            DefaultCapabilityDiscoveryAdapter,
        )
        from pi_platform.adapters.orchestration.stub_local_llm import (
            StubLocalLLMAdapter,
        )

        cap_discovery = DefaultCapabilityDiscoveryAdapter(
            local_llm=StubLocalLLMAdapter(),
        )
    except Exception:
        cap_discovery = None

    service = RestService(
        repo_root=repo_root,
        policy=policy,
        orchestrator=orchestrator,
        retrieval=retrieval,
        git=git,
        readiness=readiness,
        approval=approval,
        egress=egress,
        materialise=materialise,
        graph=projections.get("graph"),
        freshness=projections.get("freshness"),
        runtime_store=projections.get("runtime_store"),
        capability_discovery=cap_discovery,
        sources=projections.get("sources"),
        wiki=projections.get("wiki"),
        conflicts=projections.get("conflicts"),
        context=context or UiContext(repo_root=repo_root),
    )
    if defer_runtime:
        readiness.begin_refresh()
    elif hydrate_on_start and readiness.is_ready():
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        from pi_platform.core.orchestration.repository_indexing import index_repository
        from pi_platform.core.control.retrieval_settings import load_retrieval_settings
        discovery = RepositorySourceDiscovery()
        runtime = index_repository(
            target=repo_root, cache_root=cache_root,
            inventory=discovery.discover(repo_root), previous_inventory=None,
            settings=load_retrieval_settings(repo_root),
        )
        publish_runtime(service, runtime)
    return service, readiness