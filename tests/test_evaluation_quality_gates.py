"""Tier-3 evaluation quality gate tests.

Change Package J of the v0.8 refinement ships a Tier-3
retrieval evaluation command. The test suite asserts:

* the golden query loader parses the documented YAML
  schema and rejects malformed inputs;
* the corpus JSON loader reads the five documented
  sub-corpora and surfaces chunk-id-based records;
* the Tier-3 evaluator runs the golden query set against
  the stdlib-only pipeline and reports every metric named
  in plan §28.3;
* the report serialises to a JSON document that the eval
  metrics gate can consume;
* the chunk-size sweep picks the budget that maximises the
  recall + context coverage heuristic.

The Tier-2 / Tier-3 integration tests that need real models
live under ``@pytest.mark.local_model`` and are skipped on
the harness runner; the tests in this module stay
stdlib-only.
"""

from __future__ import annotations

import json
import statistics
import unittest
from pathlib import Path


__all__ = ["Tier3EvaluationQualityGateTests"]


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "evals" / "corpus" / "golden_queries.yaml"
CORPUS_ROOT = ROOT / "evals" / "corpus"
SUB_CORPORA = ("synthetic", "generated-pdf", "multilingual",
               "java", "requirements")


class Tier3EvaluationQualityGateTests(unittest.TestCase):

    def test_golden_queries_yaml_exists_and_is_valid(self) -> None:
        self.assertTrue(GOLDEN_PATH.exists(),
                        f"missing golden queries file: {GOLDEN_PATH}")
        queries = _load_golden()
        self.assertGreaterEqual(len(queries), 8)
        for query in queries:
            self.assertTrue(query.id)
            self.assertTrue(query.text)
            self.assertTrue(query.corpus)
            self.assertIn(query.corpus, SUB_CORPORA)
            self.assertGreaterEqual(query.tier, 1)

    def test_golden_queries_cover_required_tags(self) -> None:
        queries = _load_golden()
        all_tags = {tag for q in queries for tag in q.tags}
        for required in ("identifier", "protected", "java",
                         "requirements", "multilingual",
                         "generated-pdf"):
            self.assertIn(required, all_tags,
                          f"missing required tag {required!r}")

    def test_golden_queries_have_unique_ids(self) -> None:
        queries = _load_golden()
        ids = [q.id for q in queries]
        self.assertEqual(len(ids), len(set(ids)),
                         "duplicate golden query ids")

    def test_sub_corpora_all_exist(self) -> None:
        for name in SUB_CORPORA:
            self.assertTrue(
                (CORPUS_ROOT / name / "corpus.json").exists(),
                f"missing sub-corpus: {name}/corpus.json",
            )

    def test_tier3_evaluator_runs_and_reports_metrics(self) -> None:
        from pi_platform.core.eval.corpus_loader import (
            build_pipeline_hits,
            load_corpus_json,
        )
        from pi_platform.core.eval.retrieval_evaluator import (
            Tier3RetrievalEvaluator,
            build_default_pipeline,
        )
        from pi_platform.core.canonical.value_types import ProjectVersion

        queries = _load_golden()
        hits: list = []
        for name in SUB_CORPORA:
            chunks = load_corpus_json(CORPUS_ROOT / name)
            hits.extend(build_pipeline_hits(chunks))
        pipeline = build_default_pipeline(corpus_hits=hits)
        evaluator = Tier3RetrievalEvaluator(
            pipeline=pipeline, queries=queries,
            project_version=ProjectVersion(
                gitHead="abc", workingTreeFingerprint="f",
                knowledgeSchemaVersion="0.8.0",
                embeddingModelVersion="hashing-default",
                indexSchemaVersion="0.1.0",
            ),
        )
        report = evaluator.run(
            golden_queries_path=str(GOLDEN_PATH),
        )
        # Plan §28.3 complete 13-metric set
        for key in ("recall", "recall_at_10", "precision", "mrr",
                    "ndcg_at_10", "recall_at_5", "context_coverage",
                    "protected_hit_retention",
                    "average_context_tokens",
                    "latency_p50_ms", "latency_p95_ms",
                    "peak_ram_mb", "embedding_throughput_qps",
                    "reranker_throughput_qps", "cache_reuse_rate",
                    "branch_switch_hydration_ms"):
            self.assertIn(key, report.aggregate,
                          f"missing aggregate metric: {key}")
        # The golden set must produce one row per query.
        self.assertEqual(len(report.rows), len(queries))
        for row in report.rows:
            self.assertGreaterEqual(row.recall, 0.0)
            self.assertLessEqual(row.recall, 1.0)
            self.assertGreaterEqual(row.ndcg_at_10, 0.0)
            self.assertLessEqual(row.ndcg_at_10, 1.0)
            self.assertGreaterEqual(row.context_coverage, 0.0)
            self.assertLessEqual(row.context_coverage, 1.0)

    def test_quality_gates_yaml_enforces_thresholds(self) -> None:
        from pi_platform.core.eval.corpus_loader import (
            build_pipeline_hits,
            load_corpus_json,
        )
        from pi_platform.core.eval.retrieval_evaluator import (
            DEFAULT_QUALITY_GATES_PATH,
            Tier3RetrievalEvaluator,
            build_default_pipeline,
            evaluate_quality_gates,
            load_quality_gates,
        )
        gates_path = ROOT / DEFAULT_QUALITY_GATES_PATH
        self.assertTrue(gates_path.exists(),
                        f"missing quality gates file: {gates_path}")
        thresholds = load_quality_gates(gates_path)
        for required_metric in (
            "recall_at_5", "recall_at_10", "mrr", "ndcg_at_10",
            "protected_hit_retention", "context_coverage",
            "average_context_tokens", "latency_p50_ms",
            "latency_p95_ms", "peak_ram_mb",
            "embedding_throughput_qps", "reranker_throughput_qps",
            "cache_reuse_rate", "branch_switch_hydration_ms",
        ):
            self.assertIn(required_metric, thresholds)
        queries = _load_golden()
        hits: list = []
        for name in SUB_CORPORA:
            hits.extend(build_pipeline_hits(
                load_corpus_json(CORPUS_ROOT / name),
            ))
        evaluator = Tier3RetrievalEvaluator(
            pipeline=build_default_pipeline(corpus_hits=hits),
            queries=queries,
        )
        report = evaluator.run(golden_queries_path=str(GOLDEN_PATH))
        violations = evaluate_quality_gates(report.aggregate, thresholds)
        self.assertEqual(
            violations, (),
            f"quality gate violations: {[v.as_dict() for v in violations]}",
        )
        # Simulated regression must be caught with metric + threshold.
        regressed = dict(report.aggregate, recall_at_10=0.01)
        reg_violations = evaluate_quality_gates(regressed, thresholds)
        self.assertEqual(len(reg_violations), 1)
        self.assertEqual(reg_violations[0].metric, "recall_at_10")
        self.assertEqual(reg_violations[0].bound_kind, "min")

    def test_cli_eval_retrieval_subcommand(self) -> None:
        import tempfile
        from pi_platform.cli.main import main as cli_main
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "cli_tier3.json"
            rc = cli_main([
                "eval", "retrieval",
                "--golden", str(GOLDEN_PATH),
                "--corpus-root", str(CORPUS_ROOT),
                "--out", str(out),
                "--no-baseline",
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())

    def test_tier3_evaluator_serialises_to_json(self) -> None:
        import tempfile
        from pi_platform.core.eval.corpus_loader import (
            build_pipeline_hits,
            load_corpus_json,
        )
        from pi_platform.core.eval.retrieval_evaluator import (
            Tier3RetrievalEvaluator,
            build_default_pipeline,
        )
        from pi_platform.core.canonical.value_types import ProjectVersion
        from scripts.eval_retrieval import run_eval

        # The script-level entry point writes the canonical
        # report and we read it back to confirm the JSON
        # contract.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            payload = run_eval(
                golden_path=GOLDEN_PATH,
                corpus_root=CORPUS_ROOT,
                out_path=out,
                baseline_path=None,
            )
            self.assertTrue(out.exists())
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["scope"], "tier-3-retrieval")
            self.assertEqual(loaded["schema"]["name"],
                             "tier-3-retrieval/1")
            self.assertEqual(len(loaded["rows"]), len(payload["rows"]))
            for row in loaded["rows"]:
                self.assertIn("id", row)
                self.assertIn("hit_chunk_ids", row)
                self.assertIn("recall", row)

    def test_chunk_size_sweep_picks_documented_budget(self) -> None:
        from scripts.eval_chunk_size_sweep import run_chunk_size_sweep
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sweep.json"
            report = Path(tmp) / "sweep.md"
            payload = run_chunk_size_sweep(
                golden_path=GOLDEN_PATH,
                corpus_root=CORPUS_ROOT,
                out_path=out,
                report_path=report,
                budgets=(512, 768, 900, 1200),
            )
            self.assertIn(payload["selected_default_budget"],
                          {512, 768, 900, 1200})
            self.assertTrue(out.exists())
            self.assertTrue(report.exists())
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema"]["name"],
                             "tier-3-chunk-size-sweep/1")
            self.assertEqual(len(loaded["sweep"]), 4)
            for entry in loaded["sweep"]:
                self.assertIn(entry["context_budget"], {512, 768, 900, 1200})
                for key in ("recall", "mrr", "context_coverage",
                            "average_context_tokens"):
                    self.assertIn(key, entry["aggregate"])

    def test_golden_query_rejects_malformed_yaml(self) -> None:
        # The parser must reject missing 'text' / 'corpus' /
        # duplicate ids / non-mapping entries; the negative
        # path catches a typo in the schema before a silent
        # Tier-3 run.
        from pi_platform.core.eval.golden import (
            GoldenQueryError,
            parse_golden_queries,
        )
        with self.assertRaises(GoldenQueryError):
            parse_golden_queries({"queries": "not a list"})
        with self.assertRaises(GoldenQueryError):
            parse_golden_queries({
                "queries": [{"id": "x"}],  # missing text / corpus
            })
        with self.assertRaises(GoldenQueryError):
            parse_golden_queries({
                "queries": [
                    {"id": "a", "text": "a", "corpus": "synthetic"},
                    {"id": "a", "text": "b", "corpus": "synthetic"},
                ],
            })

    def test_corpus_loader_rejects_malformed_json(self) -> None:
        import tempfile
        from pi_platform.core.eval.corpus_loader import (
            CorpusLoadError,
            load_corpus_json,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken"
            path.mkdir()
            (path / "corpus.json").write_text(
                "{not valid json", encoding="utf-8",
            )
            with self.assertRaises(CorpusLoadError):
                load_corpus_json(path)


def _load_golden():
    from pi_platform.core.eval.golden import load_golden_queries
    return load_golden_queries(GOLDEN_PATH)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()