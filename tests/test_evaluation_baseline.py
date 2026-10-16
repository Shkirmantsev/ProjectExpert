"""Pre-change evaluation baseline tests (Change Package I, P0 task 1).

The v0.8 refinement records the Tier-1 deterministic benchmark
numbers in ``evals/baselines/pre_change.json`` so the Tier-3
chunk-size sweep has a stable comparator. These tests assert:

* the baseline file exists, is valid JSON and carries the
  documented schema;
* every required metric key is present and non-empty;
* the recorded numbers reproduce the Tier-1 deterministic
  benchmark within an explicit tolerance (the fixture is the
  deterministic source of truth);
* the ``scripts/eval_baseline.py show`` reload command returns
  the same JSON the file carries.

The focused subset referenced by ``make eval-baseline`` is the
``tests.test_retrieval_benchmark`` module which is the same
fixture the baseline script re-runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


__all__ = ["EvaluationBaselineTests"]


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "evals" / "baselines" / "pre_change.json"


class EvaluationBaselineTests(unittest.TestCase):

    def test_baseline_file_exists(self) -> None:
        self.assertTrue(
            BASELINE_PATH.exists(),
            f"missing baseline file: {BASELINE_PATH}",
        )

    def test_baseline_is_valid_json(self) -> None:
        text = BASELINE_PATH.read_text(encoding="utf-8")
        # ``json.loads`` raises ValueError on malformed JSON; the
        # assertion is the successful return.
        json.loads(text)

    def test_baseline_schema_is_documented(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        schema = baseline.get("schema") or {}
        self.assertEqual(schema.get("name"), "v0.8-evaluation-baseline")
        self.assertEqual(schema.get("version"), "1")
        self.assertEqual(
            schema.get("tier"), "tier-1-deterministic-ci-benchmark",
        )

    def test_baseline_records_required_metrics(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        metrics = baseline.get("aggregate_metrics") or {}
        # The aggregate metrics must cover every name in plan §28.3
        # that the Tier-1 deterministic benchmark can produce
        # without external models / network. The throughputs and
        # peak-RAM fields belong to Tier-3 and are recorded there.
        for key in (
            "recall_at_5", "recall_at_10", "precision_at_10", "mrr",
            "ndcg_at_10", "context_coverage", "protected_hit_retention",
            "average_context_tokens",
            "latency_p50_ms", "latency_p95_ms", "cache_hit_rate",
        ):
            self.assertIn(key, metrics, f"missing aggregate metric: {key}")
            self.assertIsNotNone(metrics[key], f"empty aggregate metric: {key}")
        self.assertGreater(metrics["latency_p50_ms"], 0)
        self.assertGreaterEqual(metrics["recall_at_5"], 0.0)
        self.assertLessEqual(metrics["recall_at_5"], 1.0)
        self.assertGreaterEqual(metrics["recall_at_10"], 0.0)
        self.assertLessEqual(metrics["recall_at_10"], 1.0)
        self.assertGreaterEqual(metrics["ndcg_at_10"], 0.0)
        self.assertLessEqual(metrics["ndcg_at_10"], 1.0)
        self.assertGreaterEqual(metrics["mrr"], 0.0)
        self.assertLessEqual(metrics["mrr"], 1.0)
        self.assertGreaterEqual(metrics["context_coverage"], 0.0)
        self.assertLessEqual(metrics["context_coverage"], 1.0)
        self.assertGreaterEqual(metrics["protected_hit_retention"], 0.0)
        self.assertLessEqual(metrics["protected_hit_retention"], 1.0)
        self.assertGreaterEqual(metrics["average_context_tokens"], 1)
        # Tier-1 deliberately omits embedding / reranker throughput
        # and peak RAM; the baseline must mark that scope so a
        # Tier-3 follow-up can fill them in.
        self.assertIn("metric_definitions", baseline)
        self.assertIn("scope_notes", baseline)

    def test_baseline_records_per_tag_breakdown(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        per_tag = baseline.get("per_tag_metrics") or {}
        self.assertEqual(set(per_tag.keys()),
                         {"identifier", "semantic", "graph_expansion",
                          "reranker_sensitive", "conflict"})
        # The pre-change baseline is the deterministic legacy
        # fixture result; the per-tag counts must sum to the
        # total queries.
        total = sum(entry["count"] for entry in per_tag.values())
        self.assertEqual(total, baseline["fixture"]["queries_total"])

    def test_baseline_reload_script_returns_same_payload(self) -> None:
        # The CLI helper must be byte-stable: ``show`` prints the
        # same JSON the file holds. This pins the public surface
        # for the ``make eval-baseline`` target.
        result = subprocess.run(
            [sys.executable, "scripts/eval_baseline.py", "show"],
            cwd=str(ROOT), capture_output=True, text=True, check=True,
        )
        from_file = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        from_script = json.loads(result.stdout)
        self.assertEqual(from_file, from_script)

    def test_baseline_reproduces_against_fixture_within_tolerance(
        self,
    ) -> None:
        # The Tier-1 benchmark is the source of the baseline, so
        # a fresh run must reproduce the recorded numbers within
        # a small tolerance (the fixture is deterministic but
        # wall-clock latency and MRR ties may vary slightly
        # between runs).
        import statistics
        from tests.test_retrieval_benchmark import RetrievalBenchmarkFixture
        # Three trials mimic ``scripts/eval_baseline.py rerun``
        # so the comparison matches the median the baseline
        # stores.
        trials = []
        for _ in range(3):
            report = RetrievalBenchmarkFixture().run()
            trials.append(
                {k: v for k, v in report.items() if k != "per_query"}
            )
        agg = {
            key: statistics.median(t[key] for t in trials)
            for key in (
                "aggregate_recall", "aggregate_precision",
                "aggregate_recall_at_5", "aggregate_ndcg_at_10",
                "average_context_tokens", "context_coverage",
                "protected_hit_retention",
                "aggregate_mrr", "aggregate_latency_p50",
                "aggregate_latency_p95",
            )
        }
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        recorded = baseline["aggregate_metrics"]
        # Recall / precision are deterministic; require exact
        # equality so a regression in the fixture surfaces here.
        self.assertEqual(agg["aggregate_recall"],
                         recorded["recall_at_10"])
        self.assertEqual(agg["aggregate_precision"],
                         recorded["precision_at_10"])
        self.assertEqual(agg["aggregate_recall_at_5"],
                         recorded["recall_at_5"])
        self.assertEqual(agg["average_context_tokens"],
                         int(recorded["average_context_tokens"]))
        self.assertEqual(agg["protected_hit_retention"],
                         recorded["protected_hit_retention"])
        # MRR / NDCG / context_coverage vary with reranker
        # tie-breaking across trials; allow ±0.05 so a noisy
        # machine does not invalidate the baseline while a
        # deliberate regression is still observable.
        self.assertLessEqual(
            abs(agg["aggregate_mrr"] - recorded["mrr"]), 0.05,
            f"MRR drift exceeded 0.05: {agg['aggregate_mrr']}",
        )
        self.assertLessEqual(
            abs(agg["aggregate_ndcg_at_10"] - recorded["ndcg_at_10"]),
            0.05,
            f"NDCG@10 drift exceeded 0.05: {agg['aggregate_ndcg_at_10']}",
        )
        self.assertLessEqual(
            abs(agg["context_coverage"] - recorded["context_coverage"]),
            0.05,
            f"context coverage drift exceeded 0.05: "
            f"{agg['context_coverage']}",
        )
        # Latency is wall-clock; accept ±50 ms on p50 / p95 so a
        # noisy CI runner does not invalidate the baseline.
        self.assertLessEqual(
            abs(int(agg["aggregate_latency_p50"])
                - recorded["latency_p50_ms"]),
            50,
            "p50 latency drift exceeded 50 ms",
        )
        self.assertLessEqual(
            abs(int(agg["aggregate_latency_p95"])
                - recorded["latency_p95_ms"]),
            50,
            "p95 latency drift exceeded 50 ms",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()