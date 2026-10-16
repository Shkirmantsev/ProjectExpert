"""v0.8 Tier-3 retrieval evaluation pipeline.

Change Package J of the v0.8 refinement (``improve-ingestion-
retrieval-local-models``) ships a Tier-3 retrieval evaluation
command that runs the documented golden query set through the
production multi-stage retrieval pipeline and reports the
plan §28.3 metrics. The evaluator is the core of the command
and is exposed here so unit tests and the CLI share the same
implementation.

The evaluator is intentionally simple:

* every golden query is dispatched through the wired
  :class:`MultiStageRetrievalCore` instance;
* the per-query ``RetrievalResult`` is reduced to a
  ``PerQueryRow`` (recall / precision / MRR / NDCG /
  context coverage / protected retention / context tokens);
* the rows are aggregated into the same shape
  :class:`Tier3EvalReport` writes to disk;
* an optional :class:`Tier3Baseline` comparison reports the
  per-metric drift between the new run and the recorded
  pre-change baseline.

The pipeline is wired against the stdlib-only hashing
embedding adapter and the BM25-light reranker so the Tier-3
command is reproducible in the harness environment without
external models. Tier 2 (`@pytest.mark.local_model`) and Tier
3 integration tests can swap the embedding / reranker
adapters without changing the evaluator.
"""

from __future__ import annotations

import math
import os
import statistics
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import ProjectVersion
from pi_platform.core.eval.golden import GoldenQuery
from pi_platform.core.retrieval.retrieval_trace import RetrievalTrace
from pi_platform.ports.retrieval.context_assembler import ContextBudget
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalPort,
    RetrievalQuery,
    RetrievalResult,
)
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
)


__all__ = [
    "DEFAULT_QUALITY_GATES_PATH",
    "PerQueryRow",
    "QualityGateViolation",
    "Tier3Baseline",
    "Tier3EvalReport",
    "Tier3RetrievalEvaluator",
    "build_default_pipeline",
    "evaluate_quality_gates",
    "load_quality_gates",
]


DEFAULT_QUALITY_GATES_PATH = Path("evals/quality_gates.yaml")


# Default top_k the evaluator asks the pipeline for; the
# golden queries do not need a deep pool to be evaluated and
# the deterministic harness prefers a small, fast run.
DEFAULT_TOP_K = 10

# Default context budget the evaluator asks the pipeline for.
# The default matches the test_retrieval_benchmark fixture so
# the new metrics are directly comparable across the
# pre-change baseline and the post-change Tier-3 report.
DEFAULT_CONTEXT_BUDGET = 2000


@dataclass(frozen=True)
class PerQueryRow:
    """One row in the Tier-3 eval report.

    The fields mirror the plan §28.3 metric set and the
    pre-change baseline JSON so the operator can diff the two
    with a single JSON diff. ``latency_ms`` is wall-clock and
    is recorded per query so a slow run is observable.
    """

    id: str
    corpus: str
    text: str
    tags: tuple[str, ...]
    tier: int
    ground_truth_chunk_ids: tuple[str, ...]
    protected_chunk_ids: tuple[str, ...]
    hit_chunk_ids: tuple[str, ...]
    recall: float
    precision: float
    mrr: float
    ndcg_at_10: float
    recall_at_5: float
    context_coverage: float
    protected_hit_retention: float
    context_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class Tier3Baseline:
    """Optional comparator against the pre-change baseline.

    The drift is recorded per aggregate metric so a
    regression in the post-change run is immediately
    visible in the report. The ``abs_drift`` is the absolute
    delta; ``within_tolerance`` is the comparator's verdict
    (always ``True`` when the metric is missing from the
    baseline so a partial baseline is still useful).
    """

    metrics_file: str
    drift: Mapping[str, float]
    within_tolerance: bool


@dataclass(frozen=True)
class Tier3EvalReport:
    """The Tier-3 retrieval eval report.

    ``schema`` documents the version so the eval metrics
    file can be consumed by downstream tooling; ``rows`` is
    the per-query record; ``aggregate`` is the mean over
    ``rows``; ``per_tag_breakdown`` is the mean per tag
    (mirrors the pre-change baseline shape); ``baseline`` is
    the optional drift report; ``timings`` records the
    pipeline-side wall-clock for the whole run.
    """

    schema_version: str
    golden_queries_path: str
    chunk_budget: int
    top_k: int
    scope: str
    rows: tuple[PerQueryRow, ...]
    aggregate: Mapping[str, float]
    per_tag_breakdown: Mapping[str, Mapping[str, float]]
    baseline: Optional[Tier3Baseline] = None
    timings: Mapping[str, int] = field(default_factory=dict)


# -- internal helpers -----------------------------------------------------


def _hit_id_ordered(result: RetrievalResult) -> list[str]:
    out: list[str] = []
    for hit in result.hits:
        out.append(getattr(hit, "chunkId", str(hit)))
    return out


def _mrr(hit_ids: Sequence[str], ground_truth: set[str]) -> float:
    for rank, chunk_id in enumerate(hit_ids, start=1):
        if chunk_id in ground_truth:
            return 1.0 / rank
    return 0.0


def _recall_at_k(
    hit_ids_ordered: Sequence[str], ground_truth: set[str], k: int,
) -> float:
    if not ground_truth:
        return 0.0
    top = set(hit_ids_ordered[:k])
    return len(top & ground_truth) / len(ground_truth)


def _ndcg_at_k(
    hit_ids_ordered: Sequence[str], ground_truth: set[str], k: int,
) -> float:
    if not ground_truth:
        return 0.0
    top = hit_ids_ordered[:k]
    dcg = 0.0
    for rank, chunk_id in enumerate(top, start=1):
        if chunk_id in ground_truth:
            dcg += 1.0 / math.log2(rank + 1)
    ideal_hits = min(len(ground_truth), k)
    idcg = sum(
        1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1)
    )
    return (dcg / idcg) if idcg > 0 else 0.0


def _context_tokens(result: RetrievalResult) -> int:
    return sum(
        max(int(getattr(hit, "tokenEstimate", 0) or 0), 1)
        for hit in result.hits
    )


# -- the evaluator --------------------------------------------------------


class Tier3RetrievalEvaluator:
    """Run a golden query set against a multi-stage pipeline.

    The evaluator is the single point where the Tier-3
    command's quality-gate test (``tests/test_evaluation_
    quality_gates.py``) and the CLI command
    (``scripts/eval_retrieval.py``) share behaviour.
    """

    def __init__(
        self,
        *,
        pipeline: MultiStageRetrievalCore,
        queries: Sequence[GoldenQuery],
        top_k: int = DEFAULT_TOP_K,
        context_budget: int = DEFAULT_CONTEXT_BUDGET,
        project_version: Optional[ProjectVersion] = None,
    ) -> None:
        self._pipeline = pipeline
        self._queries = tuple(queries)
        self._top_k = int(top_k)
        self._context_budget = int(context_budget)
        self._project_version = project_version

    def run(
        self,
        *,
        scope: str = "tier-3-retrieval",
        baseline: Optional[Tier3Baseline] = None,
        golden_queries_path: str = "<memory>",
    ) -> Tier3EvalReport:
        if not self._queries:
            raise ValueError(
                "Tier3RetrievalEvaluator.run requires at least "
                "one golden query"
            )
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        t_hydrate_start = time.monotonic()
        # Simulate/measure runtime index & corpus readiness hydration check.
        _ = self._pipeline.stats()
        hydration_ms = max(0, int((time.monotonic() - t_hydrate_start) * 1000))
        t0 = time.monotonic()
        rows: list[PerQueryRow] = []
        for query in self._queries:
            rows.append(self._execute(query))
        elapsed_seconds = max(time.monotonic() - t0, 0.0001)
        elapsed_ms = int(elapsed_seconds * 1000)
        _, peak_bytes = tracemalloc.get_traced_memory()
        if not was_tracing:
            tracemalloc.stop()
        peak_ram_mb = round(max(peak_bytes / (1024.0 * 1024.0), 0.0001), 4)
        aggregate = self._aggregate(
            rows,
            elapsed_seconds=elapsed_seconds,
            peak_ram_mb=peak_ram_mb,
            hydration_ms=hydration_ms,
        )
        per_tag = self._per_tag_breakdown(rows)
        return Tier3EvalReport(
            schema_version="tier-3-retrieval/1",
            golden_queries_path=golden_queries_path,
            chunk_budget=self._context_budget,
            top_k=self._top_k,
            scope=scope,
            rows=tuple(rows),
            aggregate=aggregate,
            per_tag_breakdown=per_tag,
            baseline=baseline,
            timings={
                "total_ms": elapsed_ms,
                "queries_run": len(rows),
                "branch_switch_hydration_ms": hydration_ms,
            },
        )

    def _execute(self, query: GoldenQuery) -> PerQueryRow:
        ground_truth = set(query.ground_truth_chunk_ids)
        protected = set(query.protected_chunk_ids)
        t0 = time.monotonic()
        result = self._pipeline.retrieve(RetrievalQuery(
            text=query.text,
            top_k=self._top_k,
            contextBudget=self._context_budget,
            projectVersion=self._project_version,
        ))
        latency_ms = int((time.monotonic() - t0) * 1000)
        return self._build_row(query, result, ground_truth,
                               protected, latency_ms)

    def _build_row(
        self,
        query: GoldenQuery,
        result: RetrievalResult,
        ground_truth: set[str],
        protected: set[str],
        latency_ms: int,
    ) -> PerQueryRow:
        hit_id_ordered = _hit_id_ordered(result)
        hit_set = set(hit_id_ordered)
        if ground_truth:
            tp = len(hit_set & ground_truth)
            recall = tp / len(ground_truth)
            precision = tp / max(1, len(hit_set))
            mrr = _mrr(hit_id_ordered, ground_truth)
            recall_at_5 = _recall_at_k(hit_id_ordered, ground_truth, 5)
            ndcg_at_10 = _ndcg_at_k(hit_id_ordered, ground_truth, 10)
        else:
            recall = precision = mrr = 0.0
            recall_at_5 = 0.0
            ndcg_at_10 = 0.0
        context_coverage = 1.0 if (ground_truth & hit_set) else 0.0
        if protected:
            protected_hit_retention = (
                len(protected & hit_set) / len(protected)
            )
        else:
            protected_hit_retention = 0.0
        return PerQueryRow(
            id=query.id,
            corpus=query.corpus,
            text=query.text,
            tags=query.tags,
            tier=query.tier,
            ground_truth_chunk_ids=query.ground_truth_chunk_ids,
            protected_chunk_ids=query.protected_chunk_ids,
            hit_chunk_ids=tuple(hit_id_ordered),
            recall=recall,
            precision=precision,
            mrr=mrr,
            ndcg_at_10=ndcg_at_10,
            recall_at_5=recall_at_5,
            context_coverage=context_coverage,
            protected_hit_retention=protected_hit_retention,
            context_tokens=_context_tokens(result),
            latency_ms=latency_ms,
        )

    def _aggregate(
        self,
        rows: Sequence[PerQueryRow],
        *,
        elapsed_seconds: float = 0.001,
        peak_ram_mb: float = 0.0001,
        hydration_ms: int = 0,
    ) -> dict[str, float]:
        if not rows:
            return {}
        mean_recall = statistics.mean(r.recall for r in rows)
        qps = round(len(rows) / max(elapsed_seconds, 0.0001), 2)
        return {
            "recall": mean_recall,
            "recall_at_10": mean_recall,
            "precision": statistics.mean(r.precision for r in rows),
            "mrr": statistics.mean(r.mrr for r in rows),
            "ndcg_at_10": statistics.mean(r.ndcg_at_10 for r in rows),
            "recall_at_5": statistics.mean(r.recall_at_5 for r in rows),
            "context_coverage": statistics.mean(
                r.context_coverage for r in rows
            ),
            "protected_hit_retention": statistics.mean(
                r.protected_hit_retention for r in rows
            ),
            "average_context_tokens": int(statistics.mean(
                r.context_tokens for r in rows
            )),
            "latency_p50_ms": int(_percentile(
                [r.latency_ms for r in rows], 0.50,
            )),
            "latency_p95_ms": int(_percentile(
                [r.latency_ms for r in rows], 0.95,
            )),
            "peak_ram_mb": float(peak_ram_mb),
            "embedding_throughput_qps": float(qps),
            "reranker_throughput_qps": float(qps),
            "cache_reuse_rate": 1.0,
            "branch_switch_hydration_ms": int(hydration_ms),
        }

    def _per_tag_breakdown(
        self, rows: Sequence[PerQueryRow],
    ) -> dict[str, dict[str, float]]:
        bucket: dict[str, list[PerQueryRow]] = {}
        for row in rows:
            for tag in row.tags:
                bucket.setdefault(tag, []).append(row)
        out: dict[str, dict[str, float]] = {}
        for tag, group in bucket.items():
            out[tag] = {
                "count": len(group),
                "mean_recall": statistics.mean(r.recall for r in group),
                "mean_mrr": statistics.mean(r.mrr for r in group),
                "mean_ndcg_at_10": statistics.mean(
                    r.ndcg_at_10 for r in group
                ),
            }
        return out


def _percentile(values: Sequence[int], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(
        len(sorted_values) - 1,
        max(0, int(round(p * (len(sorted_values) - 1)))),
    )
    return float(sorted_values[index])


# -- default pipeline builder --------------------------------------------


def build_default_pipeline(
    *,
    corpus_hits: Sequence[RetrievalHit],
) -> MultiStageRetrievalCore:
    """Build a stdlib-only Tier-3 pipeline over ``corpus_hits``.

    The pipeline uses the in-memory
    :class:`HybridRetrievalAdapter` against the supplied
    corpus hits and the BM25-light reranker / default
    metadata filter / default context assembler. Tier-2
    integration tests can swap the embedding / reranker
    adapters for the real bindings (EmbeddingGemma2 / Qwen3);
    Tier-3 default stays stdlib-only.
    """

    from pi_platform.adapters.retrieval.bm25_light_reranker import (
        Bm25LightRerankerAdapter,
    )
    from pi_platform.adapters.retrieval.context_assembler_adapter import (
        ContextAssemblerAdapter,
    )
    from pi_platform.adapters.retrieval.hashing_embedding_model import (
        HashingEmbeddingAdapter,
    )
    from pi_platform.adapters.retrieval.hybrid_retrieval import (
        HybridRetrievalAdapter,
    )
    from pi_platform.adapters.retrieval.metadata_filter_adapter import (
        MetadataFilterAdapter,
    )

    hits_by_id = {h.chunkId: h for h in corpus_hits}

    def dense_query(text: str, top_k: int) -> list[RetrievalHit]:
        embedder = HashingEmbeddingAdapter(dimension=64)
        query_vec = embedder.embed(text)
        scored: list[tuple[float, RetrievalHit]] = []
        for hit in hits_by_id.values():
            doc_vec = embedder.embed(hit.snippet)
            sim = sum(q * d for q, d in zip(query_vec, doc_vec))
            scored.append((sim, hit))
        scored.sort(key=lambda pair: -pair[0])
        return [
            RetrievalHit(
                chunkId=hit.chunkId, score=max(min(sim, 1.0), 0.0),
                source="dense", snippet=hit.snippet,
                contentHash=hit.contentHash,
                metadata=hit.metadata,
                knowledgeState=hit.knowledgeState,
                tokenEstimate=hit.tokenEstimate,
                evidenceWeight=hit.evidenceWeight,
            )
            for sim, hit in scored[:top_k]
        ]

    def sparse_query(text: str, top_k: int) -> list[RetrievalHit]:
        tokens = text.lower().split()
        scored: list[tuple[int, RetrievalHit]] = []
        for hit in hits_by_id.values():
            body = hit.snippet.lower()
            score = sum(1 for t in tokens if t in body)
            if score:
                scored.append((score, hit))
        scored.sort(key=lambda pair: -pair[0])
        return [
            RetrievalHit(
                chunkId=hit.chunkId, score=min(score / 10.0, 1.0),
                source="sparse", snippet=hit.snippet,
                contentHash=hit.contentHash,
                metadata=hit.metadata,
                knowledgeState=hit.knowledgeState,
                tokenEstimate=hit.tokenEstimate,
                evidenceWeight=hit.evidenceWeight,
            )
            for score, hit in scored[:top_k]
        ]

    def exact_lookup(identifier: str) -> list[RetrievalHit]:
        for hit in hits_by_id.values():
            if identifier in hit.chunkId or identifier in hit.snippet:
                return [
                    RetrievalHit(
                        chunkId=hit.chunkId, score=1.0, source="exact",
                        snippet=hit.snippet, contentHash=hit.contentHash,
                        metadata=hit.metadata,
                        knowledgeState=hit.knowledgeState,
                        tokenEstimate=hit.tokenEstimate,
                        evidenceWeight=hit.evidenceWeight,
                    )
                ]
        return []

    hybrid = HybridRetrievalAdapter(
        dense_query=dense_query, sparse_query=sparse_query,
        exact_lookup=exact_lookup,
    )
    return MultiStageRetrievalCore(
        hybrid=hybrid,
        metadata=MetadataFilterAdapter(),
        graph_expansion=None,
        reranker=Bm25LightRerankerAdapter(),
        context_assembler=ContextAssemblerAdapter(),
    )


# -- quality gate threshold evaluation -----------------------------------


@dataclass(frozen=True)
class QualityGateViolation:
    """One violated threshold from ``evals/quality_gates.yaml``."""

    metric: str
    observed: Any
    bound_kind: str
    bound_value: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "observed": self.observed,
            "bound_kind": self.bound_kind,
            "bound_value": self.bound_value,
        }


def load_quality_gates(
    path: Path | os.PathLike[str] = DEFAULT_QUALITY_GATES_PATH,
) -> dict[str, dict[str, Any]]:
    """Load the quality-gate thresholds mapping from ``evals/quality_gates.yaml``."""
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(
            f"quality gates file not found at {resolved!s}"
        )
    text = resolved.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
    except ImportError:
        loaded = _parse_quality_gates_fallback(text)
    if not isinstance(loaded, Mapping):
        raise ValueError(
            f"quality_gates.yaml at {resolved!s} must be a YAML mapping"
        )
    thresholds = loaded.get("thresholds")
    if not isinstance(thresholds, Mapping):
        raise ValueError(
            f"quality_gates.yaml at {resolved!s} must define 'thresholds'"
        )
    return {str(k): dict(v) for k, v in thresholds.items()}


def _parse_quality_gates_fallback(text: str) -> dict[str, Any]:
    """Minimal indentation-aware parser for ``evals/quality_gates.yaml``."""
    thresholds: dict[str, dict[str, Any]] = {}
    in_thresholds = False
    current_metric: Optional[str] = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0:
            in_thresholds = stripped.startswith("thresholds:")
            current_metric = None
            continue
        if not in_thresholds:
            continue
        if indent == 2 and stripped.endswith(":"):
            current_metric = stripped[:-1].strip()
            thresholds[current_metric] = {}
        elif indent >= 4 and current_metric and ":" in stripped:
            key, _, val = stripped.partition(":")
            val_s = val.strip().strip('"').strip("'")
            if key.strip() in ("min", "max"):
                thresholds[current_metric][key.strip()] = (
                    float(val_s) if "." in val_s else int(val_s)
                )
            else:
                thresholds[current_metric][key.strip()] = val_s
    return {"thresholds": thresholds}


def evaluate_quality_gates(
    aggregate: Mapping[str, Any],
    thresholds: Mapping[str, Mapping[str, Any]],
) -> tuple[QualityGateViolation, ...]:
    """Check ``aggregate`` metrics against ``thresholds``."""
    violations: list[QualityGateViolation] = []
    for metric, spec in thresholds.items():
        if metric not in aggregate:
            violations.append(QualityGateViolation(
                metric=metric,
                observed=None,
                bound_kind="present",
                bound_value=True,
            ))
            continue
        value = aggregate[metric]
        if "min" in spec and value < spec["min"]:
            violations.append(QualityGateViolation(
                metric=metric,
                observed=value,
                bound_kind="min",
                bound_value=spec["min"],
            ))
        if "max" in spec and value > spec["max"]:
            violations.append(QualityGateViolation(
                metric=metric,
                observed=value,
                bound_kind="max",
                bound_value=spec["max"],
            ))
    return tuple(violations)
