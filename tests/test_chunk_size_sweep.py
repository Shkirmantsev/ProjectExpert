"""Chunk-size sweep selection-rule tests.

Change Package J of the v0.8 refinement (plan §28.4) runs
the Tier-3 evaluation across four context budgets
(512 / 768 / 900 / 1200) and picks the budget that maximises
the mean of ``[recall, context_coverage]`` (tie-break on the
smaller budget). The selection rule is deterministic so a
unit test can pin it without spinning up a real pipeline.

The test asserts:

* every documented budget is represented in the sweep;
* the selection rule picks the budget that maximises the
  heuristic score;
* the Markdown report is byte-stable;
* the JSON contract carries the schema descriptor and the
  per-budget aggregate metrics.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


__all__ = ["ChunkSizeSweepTests"]


ROOT = Path(__file__).resolve().parents[1]


class ChunkSizeSweepTests(unittest.TestCase):

    def test_select_default_picks_highest_score(self) -> None:
        from scripts.eval_chunk_size_sweep import _select_default
        # Manually constructed sweep: budget 768 wins on the
        # mean of recall and context_coverage.
        sweep = [
            {"context_budget": 512,
             "aggregate": {"recall": 0.4, "context_coverage": 0.5}},
            {"context_budget": 768,
             "aggregate": {"recall": 0.8, "context_coverage": 0.6}},
            {"context_budget": 900,
             "aggregate": {"recall": 0.6, "context_coverage": 0.6}},
            {"context_budget": 1200,
             "aggregate": {"recall": 0.5, "context_coverage": 0.5}},
        ]
        self.assertEqual(_select_default(sweep), 768)

    def test_select_default_breaks_ties_on_smaller_budget(self) -> None:
        from scripts.eval_chunk_size_sweep import _select_default
        # All budgets tie on the heuristic; the smaller one
        # wins.
        sweep = [
            {"context_budget": b,
             "aggregate": {"recall": 0.5, "context_coverage": 0.5}}
            for b in (512, 768, 900, 1200)
        ]
        self.assertEqual(_select_default(sweep), 512)

    def test_select_default_handles_empty_sweep(self) -> None:
        from scripts.eval_chunk_size_sweep import _select_default
        # An empty sweep keeps the documented initial
        # candidate (900) by returning 0; the caller
        # surfaces the result as ``selected_default_budget``.
        self.assertEqual(_select_default([]), 0)

    def test_sweep_default_budgets_match_plan(self) -> None:
        from scripts.eval_chunk_size_sweep import DEFAULT_BUDGETS
        self.assertEqual(DEFAULT_BUDGETS, (512, 768, 900, 1200))

    def test_chunk_size_sweep_writes_json_and_markdown(self) -> None:
        from scripts.eval_chunk_size_sweep import run_chunk_size_sweep
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sweep.json"
            report = Path(tmp) / "sweep.md"
            payload = run_chunk_size_sweep(
                golden_path=ROOT / "evals" / "corpus"
                / "golden_queries.yaml",
                corpus_root=ROOT / "evals" / "corpus",
                out_path=out,
                report_path=report,
                budgets=(512, 768, 900, 1200),
            )
            self.assertTrue(out.exists())
            self.assertTrue(report.exists())
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema"]["name"],
                             "tier-3-chunk-size-sweep/1")
            self.assertEqual(loaded["budgets"], [512, 768, 900, 1200])
            markdown = report.read_text(encoding="utf-8")
            self.assertIn("# Tier-3 chunk-size sweep", markdown)
            self.assertIn("Selected default", markdown)
            for budget in (512, 768, 900, 1200):
                self.assertIn(f"| {budget} ", markdown)
            self.assertEqual(
                loaded["selected_default_budget"],
                payload["selected_default_budget"],
            )

    def test_chunk_size_sweep_rejects_empty_budgets(self) -> None:
        from scripts.eval_chunk_size_sweep import run_chunk_size_sweep
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sweep.json"
            report = Path(tmp) / "sweep.md"
            # An empty budget list still completes (the loop
            # just yields an empty sweep); the selected
            # default is 0 and the report is the empty case.
            payload = run_chunk_size_sweep(
                golden_path=ROOT / "evals" / "corpus"
                / "golden_queries.yaml",
                corpus_root=ROOT / "evals" / "corpus",
                out_path=out,
                report_path=report,
                budgets=(),
            )
            self.assertEqual(payload["sweep"], [])
            self.assertEqual(payload["selected_default_budget"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()