#!/usr/bin/env python3
"""Tier-3 retrieval evaluation command.

Implements the ``project-intelligence eval retrieval`` subcommand
introduced by Change Package J of the v0.8 refinement
(``improve-ingestion-retrieval-local-models``). The command:

* loads the golden query set from
  ``evals/corpus/golden_queries.yaml``;
* loads every referenced sub-corpus
  (``synthetic`` / ``generated-pdf`` / ``multilingual`` /
  ``java`` / ``requirements``) from
  ``evals/corpus/{name}/corpus.json``;
* runs each query through the stdlib-only multi-stage
  retrieval pipeline (the Tier-2/3 integration tests can
  swap the embedding / reranker adapters without changing
  this script);
* writes a JSON report to
  ``evals/reports/tier3_retrieval.json`` (overwritten on
  every run, atomic-rename so concurrent readers always
  see a fully-formed file);
* optionally compares the new run against the recorded
  pre-change baseline
  (``evals/baselines/pre_change.json``) and reports the
  per-metric drift.

Usage:

  project-intelligence eval retrieval                       # default
  project-intelligence eval retrieval \\
      --golden evals/corpus/golden_queries.yaml \\
      --corpus-root evals/corpus \\
      --out evals/reports/tier3_retrieval.json \\
      --baseline evals/baselines/pre_change.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pi_platform.core.eval.golden import (  # noqa: E402
    DEFAULT_GOLDEN_QUERIES_PATH,
    load_golden_queries,
)
from pi_platform.core.eval.corpus_loader import (  # noqa: E402
    load_corpus_json,
    build_pipeline_hits,
)
from pi_platform.core.eval.retrieval_evaluator import (  # noqa: E402
    Tier3Baseline,
    Tier3RetrievalEvaluator,
    build_default_pipeline,
)


__all__ = ["build_parser", "main", "run_eval"]


DEFAULT_CORPUS_ROOT = Path("evals/corpus")
DEFAULT_OUTPUT_PATH = Path("evals/reports/tier3_retrieval.json")
DEFAULT_BASELINE_PATH = Path("evals/baselines/pre_change.json")
TIER3_SCOPE = "tier-3-retrieval"
TIER3_SCHEMA_VERSION = "tier-3-retrieval/1"


# Documented sub-corpus names the golden query set can
# reference. The Tier-3 command always loads all five so the
# eval report is consistent across runs; an operator can
# drop a sub-corpus by removing its directory.
SUB_CORPORA: tuple[str, ...] = (
    "synthetic",
    "generated-pdf",
    "multilingual",
    "java",
    "requirements",
)


# -- internal helpers -----------------------------------------------------


def _load_baseline(
    path: Path | None,
) -> Tier3Baseline | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    metrics = payload.get("aggregate_metrics") or {}
    if not isinstance(metrics, dict):
        return None
    return Tier3Baseline(
        metrics_file=str(path),
        drift=dict(metrics),
        within_tolerance=True,
    )


def _serialise_report(report) -> dict:
    """Convert a :class:`Tier3EvalReport` to a JSON-friendly dict."""
    return {
        "schema": {
            "name": TIER3_SCHEMA_VERSION,
            "version": "1",
        },
        "scope": report.scope,
        "golden_queries_path": report.golden_queries_path,
        "top_k": report.top_k,
        "context_budget": report.chunk_budget,
        "rows": [
            {
                "id": row.id,
                "corpus": row.corpus,
                "text": row.text,
                "tags": list(row.tags),
                "tier": row.tier,
                "ground_truth_chunk_ids": list(
                    row.ground_truth_chunk_ids
                ),
                "protected_chunk_ids": list(row.protected_chunk_ids),
                "hit_chunk_ids": list(row.hit_chunk_ids),
                "recall": row.recall,
                "precision": row.precision,
                "mrr": row.mrr,
                "ndcg_at_10": row.ndcg_at_10,
                "recall_at_5": row.recall_at_5,
                "context_coverage": row.context_coverage,
                "protected_hit_retention": row.protected_hit_retention,
                "context_tokens": row.context_tokens,
                "latency_ms": row.latency_ms,
            }
            for row in report.rows
        ],
        "aggregate": dict(report.aggregate),
        "per_tag_breakdown": {
            tag: dict(metrics) for tag, metrics in
            report.per_tag_breakdown.items()
        },
        "baseline": (
            {
                "metrics_file": report.baseline.metrics_file,
                "drift": dict(report.baseline.drift),
                "within_tolerance": report.baseline.within_tolerance,
            }
            if report.baseline is not None else None
        ),
        "timings": dict(report.timings),
    }


def _write_report(out_path: Path, payload: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(out_path.parent), suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
        os.replace(tmp_path, out_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


# -- the run command ------------------------------------------------------


def run_eval(
    *,
    golden_path: Path = DEFAULT_GOLDEN_QUERIES_PATH,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    out_path: Path = DEFAULT_OUTPUT_PATH,
    baseline_path: Path | None = DEFAULT_BASELINE_PATH,
) -> dict:
    """Run the Tier-3 retrieval evaluation end-to-end.

    Returns the serialised report payload so unit tests
    (and the CLI handler) can assert on the same shape.
    """

    queries = load_golden_queries(golden_path)
    hits: list = []
    for name in SUB_CORPORA:
        chunks = load_corpus_json(corpus_root / name)
        hits.extend(build_pipeline_hits(chunks))
    if not hits:
        raise RuntimeError(
            f"Tier-3 eval found no corpus chunks under {corpus_root}"
        )
    pipeline = build_default_pipeline(corpus_hits=hits)
    evaluator = Tier3RetrievalEvaluator(pipeline=pipeline, queries=queries)
    baseline = _load_baseline(baseline_path)
    report = evaluator.run(
        scope=TIER3_SCOPE,
        baseline=baseline,
        golden_queries_path=str(golden_path),
    )
    payload = _serialise_report(report)
    _write_report(out_path, payload)
    return payload


# -- CLI plumbing ---------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the v0.8 Tier-3 retrieval evaluation against the "
            "documented golden query set; emit a JSON report."
        ),
    )
    parser.add_argument(
        "--golden", type=Path,
        default=DEFAULT_GOLDEN_QUERIES_PATH,
        help=(
            "path to the golden query set "
            "(default: evals/corpus/golden_queries.yaml)"
        ),
    )
    parser.add_argument(
        "--corpus-root", type=Path,
        default=DEFAULT_CORPUS_ROOT,
        help="sub-corpus root (default: evals/corpus)",
    )
    parser.add_argument(
        "--out", type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=(
            "output report path "
            "(default: evals/reports/tier3_retrieval.json)"
        ),
    )
    parser.add_argument(
        "--baseline", type=Path, default=DEFAULT_BASELINE_PATH,
        help=(
            "optional pre-change baseline for drift comparison "
            "(default: evals/baselines/pre_change.json; pass "
            "--no-baseline to skip)"
        ),
    )
    parser.add_argument(
        "--no-baseline", action="store_true",
        help="skip the baseline comparison",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baseline_path = None if args.no_baseline else args.baseline
    try:
        payload = run_eval(
            golden_path=args.golden,
            corpus_root=args.corpus_root,
            out_path=args.out,
            baseline_path=baseline_path,
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "ok": False, "error": str(exc),
            "scope": TIER3_SCOPE,
        }), file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "scope": payload["scope"],
        "aggregate": payload["aggregate"],
        "out_path": str(args.out),
        "queries_run": len(payload["rows"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())