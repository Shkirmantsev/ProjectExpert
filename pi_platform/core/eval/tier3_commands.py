"""Self-contained Tier-3 retrieval evaluation and chunk-size sweep commands.

Lives inside ``pi_platform.core.eval`` so the CLI and container runtime
can execute ``eval-retrieval`` and ``eval-chunk-size-sweep`` without
importing ``scripts/`` from a host repository checkout.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from pi_platform.adapters.ingest.tokenizers import HashingTokenizer
from pi_platform.core.eval.corpus_loader import (
    CorpusChunk,
    build_pipeline_hits,
    load_corpus_json,
)
from pi_platform.core.eval.golden import (
    DEFAULT_GOLDEN_QUERIES_PATH,
    load_golden_queries,
)
from pi_platform.core.eval.retrieval_evaluator import (
    Tier3Baseline,
    Tier3RetrievalEvaluator,
    build_default_pipeline,
)


__all__ = [
    "DEFAULT_BASELINE_PATH",
    "DEFAULT_BUDGETS",
    "DEFAULT_CORPUS_ROOT",
    "DEFAULT_OUTPUT_PATH",
    "SUB_CORPORA",
    "SWEEP_SCHEMA_VERSION",
    "SWEEP_SCOPE",
    "TIER3_SCHEMA_VERSION",
    "TIER3_SCOPE",
    "resolve_eval_asset_path",
    "run_chunk_size_sweep",
    "run_eval",
    "_select_default",
]


DEFAULT_CORPUS_ROOT = Path("evals/corpus")
DEFAULT_OUTPUT_PATH = Path("evals/reports/tier3_retrieval.json")
DEFAULT_BASELINE_PATH = Path("evals/baselines/pre_change.json")
TIER3_SCOPE = "tier-3-retrieval"
TIER3_SCHEMA_VERSION = "tier-3-retrieval/1"

SUB_CORPORA: tuple[str, ...] = (
    "synthetic",
    "generated-pdf",
    "multilingual",
    "java",
    "requirements",
)

DEFAULT_BUDGETS: tuple[int, ...] = (512, 768, 900, 1200)
SWEEP_SCHEMA_VERSION = "tier-3-chunk-size-sweep/1"
SWEEP_SCOPE = "tier-3-chunk-size-sweep"


def resolve_eval_asset_path(path: Path) -> Path:
    """Resolve an eval asset path against CWD first, then ``PI_PLATFORM_HOME``."""
    candidate = Path(path)
    if candidate.exists() or candidate.is_absolute():
        return candidate
    platform_home = Path(
        os.environ.get("PI_PLATFORM_HOME", "/opt/project-intelligence")
    )
    fallback = platform_home / candidate
    if fallback.exists():
        return fallback
    return candidate


def _load_baseline(path: Optional[Path]) -> Optional[Tier3Baseline]:
    if path is None:
        return None
    resolved = resolve_eval_asset_path(path)
    if not resolved.exists():
        return None
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
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
                "ground_truth_chunk_ids": list(row.ground_truth_chunk_ids),
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
            tag: dict(metrics)
            for tag, metrics in report.per_tag_breakdown.items()
        },
        "baseline": (
            {
                "metrics_file": report.baseline.metrics_file,
                "drift": dict(report.baseline.drift),
                "within_tolerance": report.baseline.within_tolerance,
            }
            if report.baseline is not None
            else None
        ),
        "timings": dict(report.timings),
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def run_eval(
    *,
    golden_path: Path = DEFAULT_GOLDEN_QUERIES_PATH,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    out_path: Path = DEFAULT_OUTPUT_PATH,
    baseline_path: Optional[Path] = DEFAULT_BASELINE_PATH,
) -> dict:
    """Run the Tier-3 retrieval evaluation end-to-end."""
    resolved_golden = resolve_eval_asset_path(golden_path)
    resolved_corpus = resolve_eval_asset_path(corpus_root)
    queries = load_golden_queries(resolved_golden)
    hits: list = []
    for name in SUB_CORPORA:
        chunks = load_corpus_json(resolved_corpus / name)
        hits.extend(build_pipeline_hits(chunks))
    if not hits:
        raise RuntimeError(
            f"Tier-3 eval found no corpus chunks under {resolved_corpus}"
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
    _write_json(out_path, payload)
    return payload


def _select_default(sweep: list[dict]) -> int:
    """Pick the budget with the best recall + context coverage."""
    best_budget = 0
    best_score = float("-inf")
    for entry in sweep:
        aggregate = entry.get("aggregate") or {}
        recall = float(aggregate.get("recall") or 0.0)
        coverage = float(aggregate.get("context_coverage") or 0.0)
        score = 0.5 * recall + 0.5 * coverage
        if score > best_score or (
            score == best_score
            and int(entry["context_budget"]) < best_budget
        ):
            best_score = score
            best_budget = int(entry["context_budget"])
    return best_budget


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
    lines.append(
        f"- **Budgets**: {', '.join(str(b) for b in payload['budgets'])}"
    )
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
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
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
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def run_chunk_size_sweep(
    *,
    golden_path: Path = DEFAULT_GOLDEN_QUERIES_PATH,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    out_path: Path = Path("evals/reports/chunk_size_sweep.json"),
    report_path: Path = Path("evals/reports/chunk_size_sweep.md"),
    budgets: tuple[int, ...] = DEFAULT_BUDGETS,
) -> dict:
    """Run the chunk-size sweep and return the per-budget metric set."""
    resolved_golden = resolve_eval_asset_path(golden_path)
    resolved_corpus = resolve_eval_asset_path(corpus_root)
    queries = load_golden_queries(resolved_golden)
    raw_chunks: list[CorpusChunk] = []
    for name in SUB_CORPORA:
        raw_chunks.extend(load_corpus_json(resolved_corpus / name))
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
