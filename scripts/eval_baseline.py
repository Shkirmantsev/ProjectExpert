#!/usr/bin/env python3
"""Eval baseline reload / regeneration tool.

The v0.8 refinement (``improve-ingestion-retrieval-local-models``,
P0 / Change Package I task 1) records the Tier-1 deterministic
benchmark numbers in ``evals/baselines/pre_change.json`` so the
post-change Tier-3 sweep has a stable comparator.

Usage:

* ``python3 scripts/eval_baseline.py show`` — print the recorded
  numbers as JSON; the canonical command behind
  ``make eval-baseline``.
* ``python3 scripts/eval_baseline.py rerun`` — re-execute the
  benchmark fixture and overwrite ``pre_change.json`` with fresh
  numbers. Intended for the operator who wants to refresh the
  baseline after a model / corpus change; never run automatically
  by CI.

The script is intentionally thin: it imports the benchmark
fixture from ``tests.test_retrieval_benchmark`` and writes the
result through an atomic rename so concurrent readers always see
a fully-formed JSON file.
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
BASELINE_PATH = ROOT / "evals" / "baselines" / "pre_change.json"


# -- internal helpers -----------------------------------------------------


def _load_baseline() -> dict:
    with BASELINE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_baseline(payload: dict) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(BASELINE_PATH.parent), suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
        os.replace(tmp_path, BASELINE_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _run_fixture() -> dict:
    """Import the fixture, run it three times, return medians."""
    sys.path.insert(0, str(ROOT))
    from tests.test_retrieval_benchmark import RetrievalBenchmarkFixture

    trials: list[dict] = []
    for _ in range(3):
        report = RetrievalBenchmarkFixture().run()
        agg = {k: v for k, v in report.items() if k != "per_query"}
        trials.append(agg)
    keys = (
        "aggregate_recall", "aggregate_precision", "aggregate_mrr",
        "aggregate_recall_at_5", "aggregate_ndcg_at_10",
        "average_context_tokens", "context_coverage",
        "protected_hit_retention",
        "aggregate_latency_p50", "aggregate_latency_p95",
        "aggregate_cache_hit_rate",
    )
    return {key: statistics.median(t[key] for t in trials) for key in keys}


def _per_tag_breakdown() -> dict[str, dict]:
    """Return mean recall / MRR per tag (single trial)."""
    sys.path.insert(0, str(ROOT))
    from tests.test_retrieval_benchmark import RetrievalBenchmarkFixture

    report = RetrievalBenchmarkFixture().run()
    bucket: dict[str, dict] = {}
    for entry in report["per_query"]:
        tag = entry["tag"]
        bucket.setdefault(tag, {"recall": [], "mrr": []})
        bucket[tag]["recall"].append(entry["recall"])
        bucket[tag]["mrr"].append(entry["mrr"])
    out: dict[str, dict] = {}
    for tag, values in bucket.items():
        out[tag] = {
            "count": len(values["recall"]),
            "mean_recall_at_10": statistics.mean(values["recall"]),
            "mean_mrr": statistics.mean(values["mrr"]),
        }
    return out


# -- CLI -----------------------------------------------------------------


def cmd_show(_: argparse.Namespace) -> int:
    baseline = _load_baseline()
    print(json.dumps(baseline, indent=2, sort_keys=False))
    return 0


def cmd_rerun(args: argparse.Namespace) -> int:
    payload = _load_baseline()
    aggregate = _run_fixture()
    payload["aggregate_metrics"] = {
        "recall_at_10": aggregate["aggregate_recall"],
        "precision_at_10": aggregate["aggregate_precision"],
        "recall_at_5": aggregate["aggregate_recall_at_5"],
        "ndcg_at_10": aggregate["aggregate_ndcg_at_10"],
        "mrr": aggregate["aggregate_mrr"],
        "context_coverage": aggregate["context_coverage"],
        "protected_hit_retention": aggregate["protected_hit_retention"],
        "average_context_tokens": int(aggregate["average_context_tokens"]),
        "latency_p50_ms": int(aggregate["aggregate_latency_p50"]),
        "latency_p95_ms": int(aggregate["aggregate_latency_p95"]),
        "cache_hit_rate": aggregate["aggregate_cache_hit_rate"],
    }
    payload["per_tag_metrics"] = _per_tag_breakdown()
    payload["recorded_at"] = args.recorded_at or payload.get(
        "recorded_at", "",
    )
    _write_baseline(payload)
    print(json.dumps(payload, indent=2, sort_keys=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reload / regenerate evals/baselines/pre_change.json from "
            "the Tier-1 deterministic benchmark fixture."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "show",
        help="print the recorded pre-change baseline",
    )
    rerun = sub.add_parser(
        "rerun",
        help=(
            "re-run the Tier-1 benchmark fixture three times and "
            "overwrite pre_change.json with the medians"
        ),
    )
    rerun.add_argument(
        "--recorded-at", default=None,
        help="override the recorded_at timestamp (default: keep existing)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "show":
        return cmd_show(args)
    if args.command == "rerun":
        return cmd_rerun(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())