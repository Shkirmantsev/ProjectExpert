#!/usr/bin/env python3
"""Chunk-size sweep over 512 / 768 / 900 / 1200 token budgets.

Change Package J of the v0.8 refinement (plan §28.4) runs the
golden query set against the multi-stage retrieval pipeline
with four token budgets and reports the metric drift across
the sweep. The sweep command is the production evaluation
that picks the default chunk profile.

The default budgets come from plan §28.4; ``900`` is the
initial candidate and the sweep is what confirms or
rejects it. The selected default is recorded in
``evals/reports/chunk_size_sweep.md`` so the eval corpus
links to the rationale.

Usage:

  project-intelligence eval chunk-size-sweep
  project-intelligence eval chunk-size-sweep \\
      --budgets 512 768 900 1200 \\
      --out evals/reports/chunk_size_sweep.json \\
      --report evals/reports/chunk_size_sweep.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pi_platform.adapters.ingest.tokenizers import (  # noqa: E402
    HashingTokenizer,
)
from pi_platform.core.eval.golden import (  # noqa: E402
    DEFAULT_GOLDEN_QUERIES_PATH,
    load_golden_queries,
)
from pi_platform.core.eval.corpus_loader import (  # noqa: E402
    CorpusChunk,
    load_corpus_json,
    build_pipeline_hits,
)
from pi_platform.core.eval.retrieval_evaluator import (  # noqa: E402
    Tier3RetrievalEvaluator,
    build_default_pipeline,
)


__all__ = ["build_parser", "main", "run_chunk_size_sweep"]


# Default chunk-size budgets from plan §28.4. The 900 token
# budget is the documented "initial candidate" — the sweep
# is what picks the actual default.
DEFAULT_BUDGETS: tuple[int, ...] = (512, 768, 900, 1200)
SWEEP_SCHEMA_VERSION = "tier-3-chunk-size-sweep/1"
SWEEP_SCOPE = "tier-3-chunk-size-sweep"


def run_chunk_size_sweep(
    *,
    golden_path: Path = DEFAULT_GOLDEN_QUERIES_PATH,
    corpus_root: Path = Path("evals/corpus"),
    out_path: Path = Path("evals/reports/chunk_size_sweep.json"),
    report_path: Path = Path("evals/reports/chunk_size_sweep.md"),
    budgets: tuple[int, ...] = DEFAULT_BUDGETS,
) -> dict:
    """Run the sweep and return the per-budget metric set."""

    queries = load_golden_queries(golden_path)
    raw_chunks: list[CorpusChunk] = []
    for name in ("synthetic", "generated-pdf", "multilingual",
                 "java", "requirements"):
        raw_chunks.extend(load_corpus_json(corpus_root / name))
    tokenizer = HashingTokenizer()
    sweep: list[dict] = []
    for budget in budgets:
        budget_int = max(1, int(budget))
        budgeted_chunks = [
            CorpusChunk(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                text=tokenizer.truncate(c.text, budget_int),
                language=c.language,
                valid_from=c.valid_from,
                from_pdf_prescan=c.from_pdf_prescan,
            )
            for c in raw_chunks
        ]
        hits = build_pipeline_hits(budgeted_chunks)
        pipeline = build_default_pipeline(corpus_hits=hits)
        evaluator = Tier3RetrievalEvaluator(
            pipeline=pipeline, queries=queries, context_budget=budget_int,
        )
        report = evaluator.run(
            scope=f"{SWEEP_SCOPE}@{budget_int}",
            golden_queries_path=str(golden_path),
        )
        sweep.append({
            "context_budget": budget_int,
            "chunk_max_tokens": budget_int,
            "tokenizer_id": tokenizer.identity(),
            "aggregate": dict(report.aggregate),
            "queries_run": len(report.rows),
        })
    payload = {
        "schema": {"name": SWEEP_SCHEMA_VERSION, "version": "1"},
        "scope": SWEEP_SCOPE,
        "golden_queries_path": str(golden_path),
        "budgets": list(budgets),
        "sweep": sweep,
    }
    selected = _select_default(sweep)
    payload["selected_default_budget"] = selected
    _write_json(out_path, payload)
    _write_markdown(report_path, payload)
    return payload


def _select_default(sweep: list[dict]) -> int:
    """Pick the budget with the best recall + context coverage.

    The selection rule is the plan §28.4 documented heuristic:
    the budget that maximises mean recall without regressing
    the average context tokens. The 900 budget is the
    documented initial candidate so the heuristic is
    deterministic and a regression is observable.
    """

    best_budget = 0
    best_score = float("-inf")
    for entry in sweep:
        aggregate = entry.get("aggregate") or {}
        recall = float(aggregate.get("recall") or 0.0)
        coverage = float(aggregate.get("context_coverage") or 0.0)
        # Two metrics, equal weight; tie-break on smaller
        # context budget so the default stays in the lower
        # half of the sweep when the metrics are equivalent.
        score = 0.5 * recall + 0.5 * coverage
        if score > best_score or (
            score == best_score
            and int(entry["context_budget"]) < best_budget
        ):
            best_score = score
            best_budget = int(entry["context_budget"])
    return best_budget


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _write_markdown(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Tier-3 chunk-size sweep")
    lines.append("")
    lines.append(
        f"- **Schema**: `{payload['schema']['name']}` "
        f"v{payload['schema']['version']}"
    )
    lines.append(f"- **Scope**: `{payload['scope']}`")
    lines.append(
        f"- **Golden queries**: `{payload['golden_queries_path']}`"
    )
    lines.append(f"- **Budgets**: {', '.join(str(b) for b in payload['budgets'])}")
    lines.append(
        f"- **Selected default**: "
        f"**{payload['selected_default_budget']}** tokens"
    )
    lines.append("")
    lines.append("## Per-budget metrics")
    lines.append("")
    lines.append(
        "| Context budget | Recall | Recall@5 | MRR | NDCG@10 | "
        "Context coverage | Avg context tokens |"
    )
    lines.append(
        "|---:|---:|---:|---:|---:|---:|---:|"
    )
    for entry in payload["sweep"]:
        agg = entry["aggregate"]
        lines.append(
            f"| {entry['context_budget']} "
            f"| {agg.get('recall', 0.0):.4f} "
            f"| {agg.get('recall_at_5', 0.0):.4f} "
            f"| {agg.get('mrr', 0.0):.4f} "
            f"| {agg.get('ndcg_at_10', 0.0):.4f} "
            f"| {agg.get('context_coverage', 0.0):.4f} "
            f"| {agg.get('average_context_tokens', 0)} |"
        )
    lines.append("")
    lines.append("## Selection rule")
    lines.append("")
    lines.append(
        "Plan §28.4: evaluate the `512 / 768 / 900 / 1200` token budgets "
        "(including the `900`-token initial candidate) and pick the "
        "budget that maximises the mean of `[recall, context_coverage]`, "
        "breaking ties on the smaller budget so context token cost is "
        "minimised when recall and coverage are equal."
    )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- Tier-1 default (`minimal` profile) keeps the existing "
        "context_budget = 2000 setting for backwards compatibility."
    )
    lines.append(
        "- The selected default is cross-referenced from the embedding ADR "
        "(`.ai/wiki/adr/0026-embedding-profile-identity-and-vector-"
        "namespace.md`) and from `evals/baselines/pre_change.json`."
    )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep the multi-stage retrieval pipeline over the "
            "documented chunk-size budgets and pick the default."
        ),
    )
    parser.add_argument(
        "--golden", type=Path,
        default=DEFAULT_GOLDEN_QUERIES_PATH,
    )
    parser.add_argument(
        "--corpus-root", type=Path, default=Path("evals/corpus"),
    )
    parser.add_argument(
        "--out", type=Path,
        default=Path("evals/reports/chunk_size_sweep.json"),
    )
    parser.add_argument(
        "--report", type=Path,
        default=Path("evals/reports/chunk_size_sweep.md"),
    )
    parser.add_argument(
        "--budgets", type=int, nargs="+", default=list(DEFAULT_BUDGETS),
        help=(
            "context budgets to sweep "
            "(default: 512 768 900 1200 per plan §28.4)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = run_chunk_size_sweep(
            golden_path=args.golden,
            corpus_root=args.corpus_root,
            out_path=args.out,
            report_path=args.report,
            budgets=tuple(args.budgets),
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "ok": False, "error": str(exc),
            "scope": SWEEP_SCOPE,
        }), file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "scope": payload["scope"],
        "selected_default_budget": payload["selected_default_budget"],
        "out_path": str(args.out),
        "report_path": str(args.report),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())