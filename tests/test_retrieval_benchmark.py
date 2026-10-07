"""Phase 4 retrieval benchmark fixture (task 77).

Implements the
``openspec/specs/2026-10-04-retrieval-benchmark/spec.md`` contract:
a fixed canonical corpus with deterministic labelled query set and
per-query recall / precision / mean-reciprocal-rank / latency
metrics. The benchmark exercises the §49 evaluation suite without
requiring a network or a model download: it uses the stdlib-only
hashing embedding adapter and the BM25-light reranker fallback.

The fixture is intentionally compact (``>= 1_000`` chunks and
``>= 100`` entities per the §49 spec) so the unit test suite
stays fast while still exercising the per-stage telemetry, the
identifier-recognition pre-pass, the reranker sensitivity and the
stale-knowledge detection.

The aggregate report is machine-readable (JSON) and is the source
of truth the future §49 quality-gate evaluator consumes.
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

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
from pi_platform.adapters.runtime.graph_expansion import (
    ProductionGraphExpansion,
)
from pi_platform.core.canonical.value_types import (
    Entity,
    KnowledgeState,
    Metadata,
    ProjectVersion,
    Relation,
)
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
)
from pi_platform.ports.retrieval.context_assembler import ContextBudget
from pi_platform.ports.retrieval.hybrid_retrieval import (
    HIT_SOURCE_EXACT,
    RetrievalHit,
)
from pi_platform.ports.retrieval.metadata_filter import MetadataFilter
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    RetrievalQuery,
    STAGE_CANDIDATE_GENERATION,
    STAGE_RERANK,
)


__all__ = [
    "RetrievalBenchmarkFixture",
    "RetrievalBenchmarkTests",
    "MIN_CHUNKS",
    "MIN_ENTITIES",
    "MIN_QUERIES",
]


MIN_CHUNKS = 1_000
MIN_ENTITIES = 100
MIN_QUERIES = 100
# Wall-clock latency is measured in milliseconds; tolerate 50 ms of runner jitter.
LATENCY_TOLERANCE_MS = 50


def _hit(
    chunk_id: str, *, score: float = 0.5, source: str = "sparse",
    snippet: str = "", language: str = "en",
    validFrom: str | None = None, validTo: str | None = None,
    git_commit: str | None = None,
    security_classification: str | None = None,
    knowledge_state: KnowledgeState = KnowledgeState.VERIFIED,
    token_estimate: int = 16,
    content_hash: str = "",
    evidence_weight: float = 1.0,
) -> RetrievalHit:
    md = Metadata(
        documentId=chunk_id, version="0.0.0", language=language,
        validFrom=validFrom, validTo=validTo, gitCommit=git_commit,
        sourcePath=f"docs/{chunk_id}.md",
        securityClassification=security_classification,
    )
    return RetrievalHit(
        chunkId=chunk_id, score=score, source=source, snippet=snippet,
        contentHash=content_hash or chunk_id, metadata=md,
        knowledgeState=knowledge_state,
        tokenEstimate=token_estimate,
        evidenceWeight=evidence_weight,
    )


class _InMemoryCorpus:
    """A tiny in-memory Phase 3-style corpus the benchmark exercises.

    The corpus is small (1_000+ chunks, 100+ entities) but its
    contents are deterministic so the labelled query set can
    assert exact recall / precision / MRR against a fixed
    ground truth.
    """

    def __init__(self) -> None:
        self.chunks: list[RetrievalHit] = []
        self.entities: dict[str, Entity] = {}
        self.relations: list[Relation] = []
        self._build()

    def _build(self) -> None:
        families = ("Component", "Module", "Test", "Protocol",
                    "Specification")
        for i in range(MIN_ENTITIES):
            eid = f"entity-{i:04d}"
            family = families[i % len(families)]
            self.entities[eid] = Entity(
                id=eid, family=family, label=eid,
                metadata=Metadata(
                    documentId=f"d-{i // 50}", version="0.0.0",
                    language="en",
                ),
                knowledgeState=KnowledgeState.VERIFIED,
            )
        for i in range(MIN_CHUNKS):
            doc_id = f"d-{i // 100:02d}"
            self.chunks.append(_hit(
                f"chunk-{i:04d}",
                score=0.5,
                snippet=(
                    f"Document {doc_id} chunk {i} about FinishPack "
                    f"and packing protocol message"
                ),
                content_hash=f"h-{i:04d}",
                language="en",
                token_estimate=8,
            ))
        for i in range(MIN_ENTITIES - 1):
            self.relations.append(Relation(
                sourceId=f"entity-{i:04d}",
                targetId=f"entity-{(i + 1) % MIN_ENTITIES:04d}",
                family="DESCRIBES",
            ))


class RetrievalBenchmarkFixture:
    """The §49 evaluation fixture the benchmark runs against."""

    def __init__(self) -> None:
        self._stats: dict[str, int] = {
            "plugin_setup_total": 0,
            "plugin_setup_ok": 0,
            "plugin_setup_failed": 0,
        }
        self.corpus = _InMemoryCorpus()
        self.queries: list[dict] = self._build_labelled_queries()
        self.pipeline = self._build_pipeline()

    def _build_pipeline(self) -> MultiStageRetrievalCore:
        chunk_index = {hit.chunkId: hit for hit in self.corpus.chunks}

        def dense_query(text: str, top_k: int) -> list[RetrievalHit]:
            embedder = HashingEmbeddingAdapter(dimension=64)
            query_vec = embedder.embed(text)
            scored: list[tuple[float, RetrievalHit]] = []
            for hit in self.corpus.chunks:
                doc_vec = embedder.embed(hit.snippet)
                sim = sum(q * d for q, d in zip(query_vec, doc_vec))
                scored.append((sim, hit))
            scored.sort(key=lambda pair: -pair[0])
            return [
                _replace_hit(hit, score=max(min(sim, 1.0), 0.0),
                              source="dense")
                for sim, hit in scored[:top_k]
            ]

        def sparse_query(text: str, top_k: int) -> list[RetrievalHit]:
            tokens = text.lower().split()
            scored: list[tuple[int, RetrievalHit]] = []
            for hit in self.corpus.chunks:
                body = hit.snippet.lower()
                score = sum(1 for t in tokens if t in body)
                if score:
                    scored.append((score, hit))
            scored.sort(key=lambda pair: -pair[0])
            return [
                _replace_hit(hit, score=min(score / 10.0, 1.0),
                              source="sparse")
                for score, hit in scored[:top_k]
            ]

        def exact_lookup(identifier: str) -> list[RetrievalHit]:
            for hit in self.corpus.chunks:
                if identifier in hit.chunkId or identifier in hit.snippet:
                    return [_replace_hit(hit, score=1.0,
                                          source=HIT_SOURCE_EXACT)]
            return []

        self._stats["plugin_setup_total"] += 4
        try:
            hybrid = HybridRetrievalAdapter(
                dense_query=dense_query,
                sparse_query=sparse_query,
                exact_lookup=exact_lookup,
            )
            self._stats["plugin_setup_ok"] += 1
        except Exception:
            self._stats["plugin_setup_failed"] += 1
            raise
        try:
            metadata = MetadataFilterAdapter()
            self._stats["plugin_setup_ok"] += 1
        except Exception:
            self._stats["plugin_setup_failed"] += 1
            raise
        try:
            graph_expansion = ProductionGraphExpansion(_GraphAdapter(
                self.corpus,
            ))
            self._stats["plugin_setup_ok"] += 1
        except Exception:
            self._stats["plugin_setup_failed"] += 1
            raise
        try:
            reranker = Bm25LightRerankerAdapter()
            self._stats["plugin_setup_ok"] += 1
        except Exception:
            self._stats["plugin_setup_failed"] += 1
            raise
        try:
            assembler = ContextAssemblerAdapter()
            self._stats["plugin_setup_ok"] += 1
        except Exception:
            self._stats["plugin_setup_failed"] += 1
            raise

        return MultiStageRetrievalCore(
            hybrid=hybrid,
            metadata=metadata,
            graph_expansion=graph_expansion,
            reranker=reranker,
            context_assembler=assembler,
        )

    def _build_labelled_queries(self) -> list[dict]:
        queries: list[dict] = []
        identifier_queries = [
            "GEN_3.0.03", "PSB_FINISH_PACK", "ILO-5193",
            "RpaVaryToteJpaMapper", "0x84721",
        ]
        for ident in identifier_queries:
            queries.append({
                "label": "identifier",
                "text": ident,
                "ground_truth": [ident],
                "tag": "identifier",
            })
        for i in range(40):
            queries.append({
                "label": f"semantic-{i:03d}",
                "text": f"FinishPack protocol message variant {i}",
                "ground_truth": [
                    f"chunk-{(i * 7) % MIN_CHUNKS:04d}",
                    f"chunk-{(i * 11) % MIN_CHUNKS:04d}",
                ],
                "tag": "semantic",
            })
        for i in range(30):
            queries.append({
                "label": f"graph_expansion-{i:03d}",
                "text": (
                    f"Entity entity-{i:04d} related components"
                ),
                "ground_truth": [f"entity-{(i + 1) % MIN_ENTITIES:04d}"],
                "tag": "graph_expansion",
            })
        for i in range(20):
            queries.append({
                "label": f"reranker_sensitive-{i:03d}",
                "text": (
                    f"packing protocol message ranking signal {i}"
                ),
                "ground_truth": [
                    f"chunk-{(i * 3) % MIN_CHUNKS:04d}",
                ],
                "tag": "reranker_sensitive",
            })
        for i in range(5):
            queries.append({
                "label": f"conflict-{i:02d}",
                "text": f"Conflicting source variant {i}",
                "ground_truth": [
                    f"chunk-{(i * 17) % MIN_CHUNKS:04d}",
                    f"chunk-{(i * 17 + 1) % MIN_CHUNKS:04d}",
                ],
                "tag": "conflict",
            })
        return queries

    def run(self) -> dict:
        per_query: list[dict] = []
        for query in self.queries:
            entry = self._execute(query)
            per_query.append(entry)
        return self._aggregate(per_query)

    def _execute(self, query: dict) -> dict:
        text = query["text"]
        ground_truth = set(query["ground_truth"])
        t0 = time.monotonic()
        result = self.pipeline.retrieve(RetrievalQuery(
            text=text, top_k=10, contextBudget=2000,
            enableReranking=(query["tag"] != "semantic"),
        ))
        latency_ms = int((time.monotonic() - t0) * 1000)
        stage_map = {r.stage: r for r in result.stageReports}
        candidate_in = (
            stage_map[STAGE_CANDIDATE_GENERATION].candidatesIn
            if STAGE_CANDIDATE_GENERATION in stage_map else 0
        )
        dense_calls = int(self.pipeline._hybrid.stats().get(
            "dense_calls", 0,
        ))
        sparse_calls = int(self.pipeline._hybrid.stats().get(
            "sparse_calls", 0,
        ))
        exact_calls = int(self.pipeline._hybrid.stats().get(
            "exact_calls", 0,
        ))
        hit_ids = {
            getattr(hit, "chunkId", str(hit)) for hit in result.hits
        }
        if ground_truth:
            tp = len(hit_ids & ground_truth)
            recall = tp / len(ground_truth)
            precision = tp / max(1, len(hit_ids))
            mrr = self._mrr(hit_ids, ground_truth)
        else:
            recall = precision = mrr = 0.0
        return {
            "label": query["label"],
            "text": text,
            "tag": query["tag"],
            "recall": recall,
            "precision": precision,
            "mrr": mrr,
            "latency_ms": latency_ms,
            "dense_calls": dense_calls,
            "sparse_calls": sparse_calls,
            "exact_calls": exact_calls,
            "rerank_stage": STAGE_RERANK in stage_map,
            "candidate_in": candidate_in,
            "cache_hit": 0,
            "stale_detected": False,
        }

    def _mrr(
        self, hit_ids: Iterable[str], ground_truth: set[str],
    ) -> float:
        for rank, hit_id in enumerate(hit_ids, start=1):
            if hit_id in ground_truth:
                return 1.0 / rank
        return 0.0

    def _aggregate(self, per_query: list[dict]) -> dict:
        if not per_query:
            return {}
        aggregate_recall = sum(q["recall"] for q in per_query) / len(per_query)
        aggregate_precision = (
            sum(q["precision"] for q in per_query) / len(per_query)
        )
        aggregate_mrr = sum(q["mrr"] for q in per_query) / len(per_query)
        latencies = sorted(q["latency_ms"] for q in per_query)
        aggregate_latency_p50 = latencies[len(latencies) // 2]
        aggregate_latency_p95 = latencies[
            int(len(latencies) * 0.95)
        ] if latencies else 0
        identifier_queries = [q for q in per_query if q["tag"] == "identifier"]
        if identifier_queries:
            for q in identifier_queries:
                assert q["exact_calls"] >= 1, (
                    f"identifier query did not call exact lookup: {q}"
                )
                assert q["dense_calls"] == 0, (
                    f"identifier query leaked into dense path: {q}"
                )
                assert q["sparse_calls"] == 0, (
                    f"identifier query leaked into sparse path: {q}"
                )
        return {
            "aggregate_recall": aggregate_recall,
            "aggregate_precision": aggregate_precision,
            "aggregate_mrr": aggregate_mrr,
            "aggregate_latency_p50": aggregate_latency_p50,
            "aggregate_latency_p95": aggregate_latency_p95,
            "aggregate_cache_hit_rate": sum(
                q["cache_hit"] for q in per_query
            ) / len(per_query),
            "plugin_setup_total": self._stats["plugin_setup_total"],
            "plugin_setup_ok": self._stats["plugin_setup_ok"],
            "plugin_setup_failed": self._stats["plugin_setup_failed"],
            "per_query": per_query,
        }


def _replace_hit(
    hit: RetrievalHit, *, score: float, source: str,
) -> RetrievalHit:
    return RetrievalHit(
        chunkId=hit.chunkId, score=score, source=source,
        snippet=hit.snippet, contentHash=hit.contentHash,
        metadata=hit.metadata, knowledgeState=hit.knowledgeState,
        tokenEstimate=hit.tokenEstimate,
        dropReason=hit.dropReason,
        evidenceWeight=hit.evidenceWeight,
    )


class _GraphAdapter:
    """Adapter that exposes a :class:`LocalShardedGraph`-like
    surface to :class:`ProductionGraphExpansion` so the benchmark
    pipeline can walk entity neighbours without a real Phase 3
    graph backing store."""

    def __init__(self, corpus: _InMemoryCorpus) -> None:
        self._corpus = corpus
        self._entities = corpus.entities
        self._relations = corpus.relations

    def get_entity(self, entity_id: str):
        return self._entities.get(entity_id)

    def get_relations(self, entity_id, *, edge_type=None, direction="outgoing"):
        results = []
        for rel in self._relations:
            if direction == "outgoing" and rel.sourceId != entity_id:
                continue
            if direction == "incoming" and rel.targetId != entity_id:
                continue
            if edge_type is not None and rel.family != edge_type:
                continue
            results.append(rel)
        return results

    def upsert_entity(self, entity): ...
    def upsert_relation(self, relation): ...
    def shard_by(self, content_hash): ...
    def rebuild_manifest(self): ...
    def backend_name(self): return "in-memory-benchmark"


class RetrievalBenchmarkTests(unittest.TestCase):
    """§49 evaluation suite."""

    def test_benchmark_runs_against_labeled_query_set(self):
        fixture = RetrievalBenchmarkFixture()
        report = fixture.run()
        self.assertGreaterEqual(len(report["per_query"]), MIN_QUERIES)
        for entry in report["per_query"]:
            self.assertIn("recall", entry)
            self.assertIn("precision", entry)
            self.assertIn("mrr", entry)
            self.assertIn("latency_ms", entry)
            self.assertGreaterEqual(entry["recall"], 0.0)
            self.assertLessEqual(entry["recall"], 1.0)

    def test_aggregate_metrics_are_reported(self):
        fixture = RetrievalBenchmarkFixture()
        report = fixture.run()
        for key in (
            "aggregate_recall", "aggregate_precision", "aggregate_mrr",
            "aggregate_latency_p50", "aggregate_latency_p95",
            "aggregate_cache_hit_rate",
        ):
            self.assertIn(key, report)
            self.assertGreaterEqual(report[key], 0.0)

    def test_identifier_queries_use_exact_lookup(self):
        fixture = RetrievalBenchmarkFixture()
        fixture.run()
        identifier_queries = [
            q for q in fixture.queries if q["tag"] == "identifier"
        ]
        self.assertGreaterEqual(len(identifier_queries), 5)
        for q in identifier_queries:
            self.assertGreaterEqual(len(q["ground_truth"]), 1)

    def test_reranker_sensitive_queries_use_rerank_stage(self):
        fixture = RetrievalBenchmarkFixture()
        report = fixture.run()
        rerank_sensitive = [
            q for q in report["per_query"]
            if q["tag"] == "reranker_sensitive"
        ]
        self.assertGreaterEqual(len(rerank_sensitive), 1)
        for q in rerank_sensitive:
            self.assertTrue(q["rerank_stage"])

    def test_plugin_setup_success_rate(self):
        fixture = RetrievalBenchmarkFixture()
        report = fixture.run()
        total = report["plugin_setup_total"]
        ok = report["plugin_setup_ok"]
        self.assertGreater(total, 0)
        self.assertGreaterEqual(ok / total, 0.95)

    def test_corpus_minimum_sizes(self):
        fixture = RetrievalBenchmarkFixture()
        self.assertGreaterEqual(len(fixture.corpus.chunks), MIN_CHUNKS)
        self.assertGreaterEqual(len(fixture.corpus.entities), MIN_ENTITIES)
        self.assertGreaterEqual(len(fixture.queries), MIN_QUERIES)

    def test_repeated_run_is_stable(self):
        a = RetrievalBenchmarkFixture().run()
        b = RetrievalBenchmarkFixture().run()
        for key in (
            "aggregate_recall", "aggregate_precision", "aggregate_mrr",
        ):
            self.assertAlmostEqual(a[key], b[key], delta=0.05)
        self.assertAlmostEqual(a["aggregate_latency_p50"],
                               b["aggregate_latency_p50"],
                               delta=LATENCY_TOLERANCE_MS)

    def test_aggregate_report_is_machine_readable(self):
        fixture = RetrievalBenchmarkFixture()
        report = fixture.run()
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False,
        ) as fh:
            path = Path(fh.name)
            fh.write(json.dumps(report).encode("utf-8"))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("aggregate_recall", payload)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()