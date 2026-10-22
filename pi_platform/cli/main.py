"""CLI entry point for the Phase 1 platform foundation.

Provides the documented subcommands:

* ``init-project`` - scaffold ``project-knowledge/``,
  ``.project-intelligence-cache/``, ``distribution/`` and the
  stub inventory/SBOM artefacts.
* ``hydrate`` - run the hydrate service against a target repo.
* ``materialise`` - run the materialise service (approval-gated).
* ``license-gate`` - run the license gate over a stub inventory.
* ``okf-validate`` - validate a Wiki bundle against the OKF v0.2
  profile.
* ``version-identity`` - compute the runtime project version
  identity tuple.
* ``wal-recover`` - recover a crashed materialise from the WAL.
* ``health`` - lightweight liveness check used by the container
  ``HEALTHCHECK``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

from ..adapters.fs import LocalFilesystemAdapter
from ..core.canonical import validate_wiki_bundle
from ..core.eval import runner as eval_runner
from ..core.eval.thresholds import validate_metrics
from ..core.git import compute_version_identity
from ..core.licensing import (
    DEFAULT_DEPENDENCY_INVENTORY_PATH,
    DependencyInventory,
    LicenseGate,
    LicensePolicy,
    emit_notice_file,
    emit_spdx_sbom,
    stub_inventory,
)
from ..core.sync import (
    HydrateService,
    MaterialiseService,
    PolicyDecisionStub,
    ProjectLock,
    ReconcileService,
    WriteAheadLog,
)

__all__ = ["main", "build_parser"]


DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8765
DEFAULT_PROJECT_KNOWLEDGE = Path("project-knowledge")
DEFAULT_RUNTIME_CACHE = Path(".project-intelligence-cache")


def _parse_args(argv: Optional[Iterable[str]] = None
                ) -> argparse.Namespace:
    parser = build_parser()
    return parser.parse_args(list(argv) if argv is not None else None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="platform",
        description="v0.8 Project Intelligence Platform — Phase 1 foundation CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-project", help="scaffold a target repository")
    init.add_argument("--target", type=Path, default=Path("."),
                      help="target repository root (default: current directory)")

    hydrate = sub.add_parser("hydrate", help="restore the runtime cache from the canonical tree")
    hydrate.add_argument("--target", type=Path, default=Path("."))
    hydrate.add_argument("--cache-root", type=Path,
                         default=DEFAULT_RUNTIME_CACHE)

    materialise = sub.add_parser("materialise",
                                 help="write runtime changes back to the canonical tree")
    materialise.add_argument("--target", type=Path, default=Path("."))
    materialise.add_argument("--cache-root", type=Path,
                            default=DEFAULT_RUNTIME_CACHE)
    materialise.add_argument("--approval-token", type=str, default=None)

    gate = sub.add_parser("license-gate",
                          help="run the license gate against the dependency inventory")
    gate.add_argument("--target", type=Path, default=Path("."))
    gate.add_argument("--inventory", type=Path, default=None)
    gate.add_argument("--production-lock", type=Path, default=None,
                      help="require reviewed exact coordinates for every dependency in this production lock")
    gate.add_argument("--license-review", type=Path, default=None,
                      help="operator-approved exact production closure review")
    gate.add_argument("--license-evidence", type=Path, default=None,
                      help="retained license evidence bound to the review")
    gate.add_argument("--sbom-output", type=Path, default=None,
                      help="write SPDX SBOM and NOTICE under this root only after the gate passes")

    okf = sub.add_parser("okf-validate", help="validate a Wiki bundle against the OKF v0.2 profile")
    okf.add_argument("--wiki-root", type=Path,
                     default=DEFAULT_PROJECT_KNOWLEDGE / "wiki")

    version = sub.add_parser("version-identity",
                             help="compute the runtime project version identity")
    version.add_argument("--target", type=Path, default=Path("."))
    version.add_argument("--knowledge-schema-version", type=str, default="0.1.0")
    version.add_argument("--embedding-model-version", type=str, default="unknown")
    version.add_argument("--index-schema-version", type=str, default="0.1.0")

    wal = sub.add_parser("wal-recover",
                         help="recover a crashed materialise from the write-ahead log")
    wal.add_argument("--cache-root", type=Path,
                     default=DEFAULT_RUNTIME_CACHE)

    ingest = sub.add_parser("ingest-sources", help="ingest configured local sources into the runtime cache")
    ingest.add_argument("--target", type=Path, default=Path("."))
    ingest.add_argument("--inbox", type=Path, default=None)
    ingest.add_argument("--config", type=Path, default=None)
    ingest.add_argument("--cache-root", type=Path, default=Path("tmp/local/pi-platform-ingest"))

    runtime_status = sub.add_parser("runtime-status", help="print the Phase 3 runtime store status")
    runtime_status.add_argument("--target", type=Path, default=Path("."))
    runtime_status.add_argument("--cache-root", type=Path,
                                default=DEFAULT_RUNTIME_CACHE)
    runtime_status.add_argument("--policy", type=str, default="DURABLE",
                                choices=["DURABLE", "ALL", "STALE"])

    graph_rebuild = sub.add_parser("graph-rebuild", help="rebuild the canonical knowledge graph manifest")
    graph_rebuild.add_argument("--target", type=Path, default=Path("."))
    graph_rebuild.add_argument("--cache-root", type=Path,
                               default=Path(".project-intelligence-cache/graph"))

    emb_status = sub.add_parser("embedding-status",
                   help="print the active §25 EmbeddingModelPort status")
    emb_status.add_argument("--target", type=Path, default=Path("."))
    ret_status = sub.add_parser("retrieval-status",
                   help="print the Phase 4 retrieval pipeline status")
    ret_status.add_argument("--target", type=Path, default=Path("."))
    sub.add_parser("reranker-status",
                   help="print the active §30 RerankerPort status")

    sub.add_parser("orchestrator-status",
                   help="print the Phase 5 §34 query orchestrator status")
    sub.add_parser("llm-status",
                   help="print the active §35 LocalLLMPort status")
    cap_status = sub.add_parser("capabilities",
                   help="print the §47 capability discovery descriptor")
    cap_status.add_argument("--target", type=Path, default=Path("."))
    # Phase 10 §49 + §120 quality-gates subcommands + v0.8 Tier-3 eval subcommands.
    eval_parser = sub.add_parser(
        "eval",
        help="run the §49 integration-quality-gates suites or a Tier-3 retrieval subcommand",
    )
    eval_parser.add_argument(
        "eval_subcommand",
        nargs="?",
        choices=("retrieval", "chunk-size-sweep"),
        default=None,
        help="optional Tier-3 subcommand ('retrieval' or 'chunk-size-sweep')",
    )
    eval_parser.add_argument(
        "--golden", type=Path,
        default=Path("evals/corpus/golden_queries.yaml"),
        help="path to the golden query set (default: evals/corpus/golden_queries.yaml)",
    )
    eval_parser.add_argument(
        "--corpus-root", type=Path, default=Path("evals/corpus"),
        help="sub-corpus root (default: evals/corpus)",
    )
    eval_parser.add_argument(
        "--out", type=Path, default=None,
        help="output report path",
    )
    eval_parser.add_argument(
        "--baseline", type=Path,
        default=Path("evals/baselines/pre_change.json"),
        help="optional pre-change baseline for drift comparison",
    )
    eval_parser.add_argument(
        "--no-baseline", action="store_true",
        help="skip the baseline comparison",
    )
    eval_parser.add_argument(
        "--report", type=Path,
        default=Path("evals/reports/chunk_size_sweep.md"),
        help="Markdown report path for chunk-size-sweep",
    )
    eval_parser.add_argument(
        "--budgets", type=int, nargs="+",
        default=[512, 768, 900, 1200],
        help="context budgets to sweep (default: 512 768 900 1200)",
    )
    sub.add_parser("invariants",
                   help="run the §120 52-invariant §68 acceptance suite")
    accel = sub.add_parser(
        "accelerator", help="manage the host-side embedding accelerator",
    )
    accel.add_argument(
        "accelerator_command", choices=("start", "stop", "status"),
        help="accelerator lifecycle action",
    )
    accel.add_argument(
        "--bind-host", default=None,
        help="bind address (default: 127.0.0.1; private requires ACCELERATOR_ALLOW_WIDE_BIND=1)",
    )
    accel.add_argument(
        "--bind-port", type=int, default=None,
        help="bind port (default: 8791)",
    )
    accel.add_argument(
        "--max-concurrent-requests", type=int, default=None,
        help="concurrency limit (default: 4)",
    )

    sub.add_parser("metrics-gate",
                   help="verify the last eval/last.json metrics are within the documented thresholds")

    eval_retrieval = sub.add_parser(
        "eval-retrieval",
        help="run the v0.8 Tier-3 retrieval evaluation against the documented golden query set",
    )
    eval_retrieval.add_argument(
        "--target", type=Path, default=None,
        help="evaluate the actual repository runtime shared with UI/MCP instead of the fixture pipeline",
    )
    eval_retrieval.add_argument(
        "--golden", type=Path,
        default=Path("evals/corpus/golden_queries.yaml"),
        help="path to the golden query set (default: evals/corpus/golden_queries.yaml)",
    )
    eval_retrieval.add_argument(
        "--corpus-root", type=Path, default=Path("evals/corpus"),
        help="sub-corpus root (default: evals/corpus)",
    )
    eval_retrieval.add_argument(
        "--out", type=Path,
        default=Path("evals/reports/tier3_retrieval.json"),
        help="output report path (default: evals/reports/tier3_retrieval.json)",
    )
    eval_retrieval.add_argument(
        "--baseline", type=Path,
        default=Path("evals/baselines/pre_change.json"),
        help="optional pre-change baseline for drift comparison",
    )
    eval_retrieval.add_argument(
        "--no-baseline", action="store_true",
        help="skip the baseline comparison",
    )

    eval_sweep = sub.add_parser(
        "eval-chunk-size-sweep",
        help="sweep the v0.8 Tier-3 chunk-size budgets and pick the default",
    )
    eval_sweep.add_argument(
        "--golden", type=Path,
        default=Path("evals/corpus/golden_queries.yaml"),
    )
    eval_sweep.add_argument(
        "--corpus-root", type=Path, default=Path("evals/corpus"),
    )
    eval_sweep.add_argument(
        "--out", type=Path,
        default=Path("evals/reports/chunk_size_sweep.json"),
    )
    eval_sweep.add_argument(
        "--report", type=Path,
        default=Path("evals/reports/chunk_size_sweep.md"),
    )
    eval_sweep.add_argument(
        "--budgets", type=int, nargs="+",
        default=[512, 768, 900, 1200],
        help="context budgets to sweep (default: 512 768 900 1200)",
    )

    health = sub.add_parser(
        "health", help="liveness check; --ready reports readiness"
    )
    health.add_argument(
        "--ready", action="store_true",
        help="exit 0 only when knowledge hydration is consistent",
    )
    health.add_argument("--target", type=Path, default=Path.cwd())
    health.add_argument("--cache-root", type=Path, default=DEFAULT_RUNTIME_CACHE)
    serve = sub.add_parser(
        "serve", help="serve the human UI API and static frontend"
    )
    serve.add_argument("--target", type=Path, default=Path.cwd())
    serve.add_argument("--cache-root", type=Path, default=DEFAULT_RUNTIME_CACHE)
    serve.add_argument("--host", default=DEFAULT_UI_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_UI_PORT)

    mcp_serve = sub.add_parser(
        "mcp-serve", help="serve the §36 MCP tool and §38 skill resource surface"
    )
    mcp_serve.add_argument("--target", type=Path, default=Path.cwd())
    mcp_serve.add_argument("--cache-root", type=Path, default=DEFAULT_RUNTIME_CACHE)
    mcp_serve.add_argument(
        "--transport", choices=("stdio", "http"), default="stdio",
    )
    mcp_serve.add_argument("--host", default=DEFAULT_UI_HOST)
    mcp_serve.add_argument("--port", type=int, default=DEFAULT_UI_PORT)
    mcp_serve.add_argument("--debug", action="store_true")

    a2a_serve = sub.add_parser(
        "a2a-serve", help="serve the §50 A2A inbound HTTP surface and Agent Card"
    )
    a2a_serve.add_argument("--host", default=DEFAULT_UI_HOST)
    a2a_serve.add_argument("--port", type=int, default=8766)

    pkg_plugins = sub.add_parser(
        "package-plugins",
        help="generate the four §41-§44 vendor agent plugin bundles",
    )
    pkg_plugins.add_argument(
        "--skills-root", type=Path, default=None,
        help="path to canonical skills directory (default: distribution/skills)",
    )
    pkg_plugins.add_argument(
        "--output-root", type=Path, default=Path("distribution"),
        help="output root for codex/claude-code/opencode/generic-agent bundles",
    )

    sub.add_parser("--help", help="show this help message and exit")

    # One-command production UX (open spec change PR 11, plan §15–§18).
    start = sub.add_parser(
        "start",
        help="one-command production bootstrap (settings → wizard → discovery → index → retrieval runtime)",
    )
    start.add_argument("--target", type=Path, default=Path("."),
                       help="target repository root (default: current directory)")
    start.add_argument("--model", choices=("gemma", "qwen", "qwen-gguf", "gemma-gguf"), default=None,
                       help="embedding model alias (gemma → google/embeddinggemma-2)")
    start.add_argument("--device", choices=("auto", "cpu", "cuda", "vulkan"), default=None,
                       help="execution device (default: auto)")
    start.add_argument("--host", default=DEFAULT_UI_HOST,
                       help="control-plane bind host (default: 127.0.0.1)")
    start.add_argument("--port", type=int, default=DEFAULT_UI_PORT,
                       help="control-plane bind port (default: 8765)")
    start.add_argument("--serve", action="store_true",
                       help="serve the HTTP control plane (the default)")
    start.add_argument("--no-serve", action="store_true",
                       help="bootstrap once and exit without an HTTP listener")

    reindex_parser = sub.add_parser(
        "reindex",
        help="incrementally discover, reconcile, and reindex a target repository",
    )
    reindex_parser.add_argument("--target", type=Path, default=Path("."),
                                help="target repository root (default: current directory)")

    doctor_parser = sub.add_parser(
        "doctor",
        help="run full production capability and target readiness diagnostics",
    )
    doctor_parser.add_argument("--target", type=Path, default=Path("."),
                               help="target repository root (default: current directory)")

    models = sub.add_parser(
        "models",
        help="manage the production embedding models (list/status/pull/verify/use)",
    )
    models_sub = models.add_subparsers(dest="models_command", required=True)
    models_list = models_sub.add_parser(
        "list", help="list the production-enabled models from the licence record",
    )
    models_list.add_argument("--target", type=Path, default=Path("."),
                             help="target repository root used to locate distribution/")
    models_status = models_sub.add_parser(
        "status", help="print the active model profile",
    )
    models_status.add_argument("--target", type=Path, default=Path("."),
                               help="target repository root (default: current directory)")
    models_pull = models_sub.add_parser(
        "pull", help="download a model into the local Hugging Face cache",
    )
    models_pull.add_argument("alias", type=str,
                             help="model alias (gemma|qwen) or Hugging Face model id")
    models_verify = models_sub.add_parser(
        "verify", help="verify the model files exist in the local Hugging Face cache",
    )
    models_verify.add_argument("alias", type=str,
                               help="model alias (gemma|qwen) or Hugging Face model id")
    models_use = models_sub.add_parser(
        "use", help="record the selected model alias as the active selection",
    )
    models_use.add_argument("alias", type=str,
                            help="model alias (gemma|qwen) or Hugging Face model id")
    models_use.add_argument("--target", type=Path, default=Path("."),
                            help="target repository root (default: current directory)")

    return parser


def _resolve_cache_root(args: argparse.Namespace) -> Path:
    """Resolve ``--cache-root`` relative to ``--target`` when it is not absolute."""

    cache_root = Path(getattr(args, "cache_root", DEFAULT_RUNTIME_CACHE))
    if cache_root.is_absolute():
        return cache_root
    target_arg = getattr(args, "target", None)
    if target_arg is None:
        return (Path.cwd() / cache_root).resolve()
    return (Path(target_arg).resolve() / cache_root).resolve()


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def _cmd_init_project(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    fs = LocalFilesystemAdapter(target)
    fs.ensure_canonical_tree()
    fs.ensure_distribution_tree()
    fs.ensure_cache_root()
    added_gitignore = fs.ensure_gitignore()
    _ensure_default_project_context(fs.knowledge_root)
    inventory = DependencyInventory(DEFAULT_DEPENDENCY_INVENTORY_PATH)
    inventory.save(stub_inventory(), path=target / DEFAULT_DEPENDENCY_INVENTORY_PATH)
    emit_spdx_sbom(stub_inventory(), output_root=target)
    emit_notice_file(stub_inventory(), output_root=target)
    print(json.dumps({
        "target": str(target),
        "gitignore_added": added_gitignore,
        "canonical_root": str(fs.knowledge_root),
        "cache_root": str(fs.cache_root),
        "distribution_root": str(fs.distribution_root),
    }, indent=2))
    return 0


def _ensure_default_project_context(knowledge_root: Path) -> None:
    config_path = knowledge_root / "project-context.yaml"
    if config_path.exists():
        return
    text = (
        "---\n"
        "projectKnowledgeRoot: project-knowledge\n"
        "runtimeCacheRoot: .project-intelligence-cache\n"
        "localInbox: tmp/local/source\n"
        "okfVersion: \"0.2\"\n"
        "knowledgeSchemaVersion: \"0.1.0\"\n"
        "embeddingModelVersion: \"unknown\"\n"
        "indexSchemaVersion: \"0.1.0\"\n"
        "licensing:\n"
        "  mode: strict\n"
        "  allow:\n"
        "    - Apache-2.0\n"
        "    - MIT\n"
        "    - BSD-2-Clause\n"
        "    - BSD-3-Clause\n"
        "    - ISC\n"
        "  review:\n"
        "    - MPL-2.0\n"
        "    - EPL-2.0\n"
        "    - LGPL-2.1-only\n"
        "    - LGPL-3.0-only\n"
        "  denyPatterns:\n"
        "    - \"*-NC-*\"\n"
        "    - \"research-only\"\n"
        "    - \"non-commercial\"\n"
        "    - \"source-available-restricted\"\n"
        "sources:\n"
        "  localInbox:\n"
        "    path: tmp/local/source\n"
        "    recursive: true\n"
        "    defaultPolicy: LOCAL_ONLY\n"
        "  externalDocumentation:\n"
        "    path: external-documentation\n"
        "    recursive: true\n"
        "    defaultPolicy: SNAPSHOT\n"
        "  confluence:\n"
        "    enabled: false\n"
        "  intranet:\n"
        "    enabled: false\n"
    )
    config_path.write_text(text, encoding="utf-8")


def _cmd_hydrate(args: argparse.Namespace) -> int:
    from ..adapters.ui import persist_readiness
    from ..core.sync.readiness import DefaultKnowledgeReadiness

    target = args.target.resolve()
    cache_root = _resolve_cache_root(args)
    fs = LocalFilesystemAdapter(target, cache_root=cache_root)
    with ProjectLock(_project_id(target)).acquire():
        service = HydrateService(filesystem=fs)
        report = service.restore_runtime(target, cache_root=cache_root)
        previous_head = report.project_version.gitHead
        readiness_file = cache_root / "readiness.json"
        if readiness_file.is_file():
            try:
                prev_payload = json.loads(readiness_file.read_text(encoding="utf-8"))
                if isinstance(prev_payload, dict) and prev_payload.get("current_head"):
                    previous_head = str(prev_payload["current_head"])
            except (OSError, ValueError):
                pass
        reconcile = ReconcileService(filesystem=fs).reconcile_branch_switch(
            target,
            previous_head=previous_head,
            current_head=report.project_version.gitHead,
            cache_root=cache_root,
        )
        readiness = DefaultKnowledgeReadiness()
        readiness.record_hydrate(report)
        readiness.record_reconcile(
            reconcile,
            current_head=report.project_version.gitHead,
            working_tree_fingerprint=report.project_version.workingTreeFingerprint,
        )
        persist_readiness(cache_root, readiness)
    print(json.dumps({
        "git_head": report.project_version.gitHead,
        "embedding_model_version": report.project_version.embeddingModelVersion,
        "families": dict(report.families),
        "cache_hit_rates": dict(report.cache_hit_rates),
        "stale_fact_ids": list(report.stale_fact_ids),
    }, indent=2))
    return 0


def _cmd_materialise(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    cache_root = _resolve_cache_root(args)
    with ProjectLock(_project_id(target)).acquire():
        service = MaterialiseService(
            filesystem=LocalFilesystemAdapter(target, cache_root=cache_root),
            wal=WriteAheadLog(cache_root),
            policy=PolicyDecisionStub(),
            license_gate=LicenseGate(LicensePolicy()),
        )
        try:
            report = service.materialise_durable_changes(
                target, cache_root=cache_root,
                approval_token=args.approval_token,
            )
        except Exception as exc:
            print(json.dumps({"error": str(exc)}, indent=2))
            return 2
    print(json.dumps({
        "policy_decision": report.policy_decision.value,
        "diff_files": [{"path": d.path, "status": d.status} for d in report.diff_files],
        "excluded_local_only": list(report.excluded_local_only),
        "okf_validation_errors": [str(e) for e in report.okf_validation_errors],
    }, indent=2))
    return 0


def _cmd_license_gate(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    if args.inventory:
        inventory_path = args.inventory
    else:
        candidates = [target / DEFAULT_DEPENDENCY_INVENTORY_PATH]
        platform_home = os.environ.get("PI_PLATFORM_HOME")
        if platform_home:
            candidates.append(Path(platform_home) / DEFAULT_DEPENDENCY_INVENTORY_PATH)
        candidates.extend([
            Path(sys.prefix) / DEFAULT_DEPENDENCY_INVENTORY_PATH,
            Path(__file__).resolve().parents[2] / DEFAULT_DEPENDENCY_INVENTORY_PATH,
            Path("/opt/project-intelligence") / DEFAULT_DEPENDENCY_INVENTORY_PATH,
        ])
        inventory_path = next((path for path in candidates if path.is_file()), candidates[0])
    try:
        if not inventory_path.is_file():
            raise ValueError(f"Dependency inventory not found: {inventory_path}")
        deps = DependencyInventory(inventory_path).load()
        if not deps:
            raise ValueError(f"Dependency inventory is empty: {inventory_path}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"inventory": str(inventory_path), "passed": False,
                          "findings": [], "error": str(exc)}, indent=2))
        return 1
    discovered = target / "tmp/local/pi-platform-ingest/discovered-dependencies.json"
    if discovered.exists():
        deps.extend(DependencyInventory(discovered).load())
    policy = LicensePolicy()
    review = getattr(args, "license_review", None)
    if review is not None:
        from ..core.licensing.scoped_review import load_scoped_review, ScopedReviewPolicy
        try:
            if args.production_lock is None or args.license_evidence is None:
                raise ValueError("Scoped review requires --production-lock and --license-evidence")
            policy = ScopedReviewPolicy(load_scoped_review(
                review, inventory=inventory_path, lock=args.production_lock,
                evidence=args.license_evidence,
            ))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(json.dumps({"passed": False, "error": str(exc)}))
            return 1
    passed, findings = LicenseGate(policy).run(deps)
    coverage_errors: list[str] = []
    production_lock = getattr(args, "production_lock", None)
    if production_lock is not None:
        from ..core.licensing.lock_coverage import check_lock_coverage
        try:
            coverage_errors = check_lock_coverage(production_lock, deps)
        except (OSError, ValueError) as exc:
            coverage_errors = [str(exc)]
        passed = passed and not coverage_errors

    sbom_output = getattr(args, "sbom_output", None)
    if passed and sbom_output is not None:
        emit_spdx_sbom(deps, output_root=sbom_output)
        emit_notice_file(deps, output_root=sbom_output, policy=policy)
    payload = {
        "inventory": str(inventory_path),
        "passed": passed,
        "coverage_errors": coverage_errors,
        "findings": [
            {"name": f.dependency.name,
             "version": f.dependency.version,
             "spdx": f.dependency.spdx,
             "decision": f.decision,
             "reason": f.reason}
            for f in findings
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


def _cmd_okf_validate(args: argparse.Namespace) -> int:
    errors = validate_wiki_bundle(args.wiki_root)
    payload = {
        "wiki_root": str(args.wiki_root),
        "errors": [str(e) for e in errors],
    }
    print(json.dumps(payload, indent=2))
    return 0 if not errors else 1


def _cmd_version_identity(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    identity = compute_version_identity(
        target,
        knowledge_schema_version=args.knowledge_schema_version,
        embedding_model_version=args.embedding_model_version,
        index_schema_version=args.index_schema_version,
    )
    print(json.dumps({
        "git_head": identity.gitHead,
        "working_tree_fingerprint": identity.workingTreeFingerprint,
        "knowledge_schema_version": identity.knowledgeSchemaVersion,
        "embedding_model_version": identity.embeddingModelVersion,
        "index_schema_version": identity.indexSchemaVersion,
    }, indent=2))
    return 0


def _cmd_wal_recover(args: argparse.Namespace) -> int:
    cache_root = _resolve_cache_root(args)
    removed = WriteAheadLog(cache_root).recover()
    print(json.dumps({"cache_root": str(cache_root), "rolled_back": removed}, indent=2))
    return 0


def _cmd_ingest_sources(args: argparse.Namespace) -> int:
    from ..adapters.ingest.local_pipeline_driver import (
        LocalPipelineDriver,
        _default_parser_registry,
    )
    from ..adapters.java.java_structured_adapter import JavaStructuredAdapter
    from ..core.ingest.config import load_ingest_config
    from ..core.ingest.local_source_inbox_scanner import LocalSourceInboxScanner
    from ..core.ingest.runtime_cache import InMemoryRuntimeCache
    from ..core.canonical.value_types import dataclass_to_dict
    from ..ports.ingest.local_source_inbox_scanner import (
        LocalSourceInboxContext,
        SourcePromotionPolicy,
    )
    from ..ports.ingest.chunker import ChunkerContext
    from ..ports.ingest.context_enricher import EnricherContext, DomainRule
    from ..ports.ingest.source_adapter import SourceContentFamily
    from ..adapters.java.parser_subprocess import TreeSitterJavaSubprocess

    target = args.target.resolve()
    config = load_ingest_config(
        args.config or target / "project-knowledge/project-context.yaml"
    )
    inbox_config = config.get("sources", {}).get("localInbox", {})
    inbox = args.inbox or Path(inbox_config.get("path", "tmp/local/source"))
    if not inbox.is_absolute():
        inbox = target / inbox
    cache = InMemoryRuntimeCache()
    cache_root = _resolve_cache_root(args)
    state_path = cache_root / "ingestion.json"
    with ProjectLock(_project_id(target)).acquire():
        if state_path.exists():
            saved = json.loads(state_path.read_text())
            cache._store = {k: v.encode() for k, v in saved.get("records", {}).items()}
            cache._sources = saved.get("sources", {})
            cache._owners = {k: set(v) for k, v in saved.get("owners", {}).items()}
        scanner = LocalSourceInboxScanner(cache)
        from ..core.canonical.value_types import Source, dataclass_from_dict

        if state_path.exists():
            scanner._previous[str(inbox.resolve())] = {
                p: dataclass_from_dict(Source, s)
                for p, s in saved.get("scanner", {}).items()
            }
        registry = _default_parser_registry()
        java_config = config.get("javaParser", {})
        registry.register(
            JavaStructuredAdapter(
                TreeSitterJavaSubprocess(
                    required=bool(java_config.get("required", False))
                )
            )
        )
        ingest = config.get("ingest", {})
        chunking = ingest.get("chunking", {})
        rules = tuple(
            DomainRule(r["path"], r.get("metadata", {}))
            for r in ingest.get("domainRules", [])
        )
        policies = {
            g: SourcePromotionPolicy(str(p).upper())
            for g, p in inbox_config.get("policies", {}).items()
        }
        scan = scanner.scan(
            LocalSourceInboxContext(
                inbox,
                SourcePromotionPolicy(
                    str(inbox_config.get("defaultPolicy", "LOCAL_ONLY")).upper()
                ),
                policies,
                recursive=inbox_config.get("recursive", True),
                extra={
                    "repository_root": target,
                    "max_source_bytes": inbox_config.get(
                        "maxSourceBytes", 256 * 1024 * 1024
                    ),
                    "processing_fingerprint": hashlib.sha256(
                        json.dumps(config, sort_keys=True).encode()
                    ).hexdigest()
                    + str(
                        registry.resolve(
                            SourceContentFamily.JAVA_SOURCE
                        ).parser.is_available()
                    ),
                },
            )
        )
        version = (
            compute_version_identity(target) if (target / ".git").exists() else None
        )
        driver = LocalPipelineDriver(
            parser_registry=registry,
            cache=cache,
            project_version=version,
            chunker_context=ChunkerContext(
                max_chunk_bytes=chunking.get("maxChunkBytes", 4096),
                extra={"min_chunk_bytes": chunking.get("minChunkBytes", 256)},
            ),
            enricher_context=EnricherContext(
                domain_rules=rules,
                enable_optional_llm=ingest.get("enableOptionalLlm", False),
            ),
        )
        reports = driver.run_many(scan.registered_sources, target)
        cache_root.mkdir(parents=True, exist_ok=True)
        body = {
            "records": {k: v.decode() for k, v in cache._store.items()},
            "sources": cache._sources,
            "owners": {k: sorted(v) for k, v in cache._owners.items()},
            "scanner": {
                p: dataclass_to_dict(s)
                for p, s in scanner._previous.get(str(inbox.resolve()), {}).items()
            },
        }
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
        temporary.replace(state_path)
        # Unknown dependency coordinates are local evidence, never authoritative inventory edits.
        discovered = []
        for value in cache._store.values():
            try:
                record = json.loads(value)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("family") == "Dependency":
                attrs = record.get("metadata", {}).get("extensions", {})
                discovered.append(
                    {
                        "name": record["label"],
                        "version": attrs.get("version", "unknown"),
                        "spdx": attrs.get("spdx"),
                        "scope": "runtime",
                    }
                )
        (cache_root / "discovered-dependencies.json").write_text(
            json.dumps({"dependencies": discovered}, sort_keys=True)
        )
    print(
        json.dumps(
            {
                "reports": [dataclass_to_dict(r) for r in reports],
                "skipped": len(scan.skipped_paths),
                "deleted_source_ids": list(scan.deleted_source_ids),
                "cache_root": str(cache_root),
            },
            indent=2,
        )
    )
    return 0 if all(r.ok for r in reports) else 1


def _resolve_skills_root(target: Optional[Path] = None) -> Optional[Path]:
    """Locate the canonical ``distribution/skills`` directory."""
    candidates: list[Path] = []
    if target is not None:
        candidates.append(Path(target).resolve() / "distribution" / "skills")
    candidates.append(Path.cwd() / "distribution" / "skills")
    platform_home = os.environ.get("PI_PLATFORM_HOME")
    if platform_home:
        candidates.append(Path(platform_home) / "distribution" / "skills")
    candidates.append(
        Path(__file__).resolve().parents[2] / "distribution" / "skills"
    )
    candidates.append(Path(sys.prefix) / "distribution" / "skills")
    for cand in candidates:
        if (cand / "project-intelligence" / "SKILL.md").is_file():
            return cand
    return None


def _build_embedded_mcp_and_a2a(
    *,
    target: Path,
    cache_root: Path,
    service: object,
    readiness: object,
    debug_mode: Optional[bool] = None,
) -> tuple[object, object, object, object]:
    """Construct the embedded MCP server, SkillDistributionPlane, A2A adapter, and Agent Card."""
    from ..core.a2a import A2aAdapterCore, A2aFlags, AgentCardBuilder
    from ..mcp.context import build_default_tool_context
    from ..mcp.server import McpServer
    from ..mcp.skill_plane import SkillDistributionPlane

    mcp_ctx = build_default_tool_context(
        debug_mode=debug_mode,
        repo_root=target,
        cache_root=cache_root,
        readiness=readiness,
        multi_stage_retrieval=getattr(service, "_retrieval", None),
        hybrid_retrieval=getattr(
            getattr(service, "_retrieval", None), "_hybrid", None
        ),
        orchestrator=getattr(service, "_orchestrator", None),
        boundary=getattr(service, "_approval", None),
    )
    mcp_server = McpServer(context=mcp_ctx)

    skill_plane = None
    skills_root = _resolve_skills_root(target)
    if skills_root is not None:
        try:
            skill_plane = SkillDistributionPlane(skills_root=skills_root)
        except Exception:
            skill_plane = None

    a2a_inbound = str(
        os.environ.get("PI_A2A_INBOUND", "") or ""
    ).strip().lower() in ("1", "true", "yes", "on")

    def _flags_provider(flag_name: str) -> bool:
        if flag_name == A2aFlags.A2A_INBOUND.value:
            return a2a_inbound
        return False

    a2a_adapter = A2aAdapterCore(
        flags_provider=_flags_provider,
        policy_gate=lambda **_: "ALLOW" if a2a_inbound else "DENY",
    )
    agent_card = AgentCardBuilder(
        descriptor={
            "name": "project-intelligence",
            "description": "Project Intelligence Platform",
            "version": "0.8.0",
            "protocols": {
                "a2a": {
                    "supported_protocols": ("jsonrpc-2.0",),
                    "version": "1.0",
                }
            },
            "skills": [
                {
                    "id": "project-intelligence",
                    "description": "Retrieval-first project intelligence",
                    "tags": ["retrieval", "mcp", "okf"],
                }
            ],
        },
        flags_provider=_flags_provider,
        published=a2a_inbound,
    )
    return mcp_server, skill_plane, a2a_adapter, agent_card


def _cmd_health(args: argparse.Namespace) -> int:
    """Liveness by default; ``--ready`` reports hydration readiness (§62)."""
    if not getattr(args, "ready", False):
        print(json.dumps({"status": "ok"}))
        return 0
    from ..adapters.ui.composition import load_persisted_readiness
    from ..core.sync.readiness import DefaultKnowledgeReadiness

    target = Path(getattr(args, "target", Path.cwd())).resolve()
    cache_root = _resolve_cache_root(args)
    readiness = DefaultKnowledgeReadiness()
    load_persisted_readiness(cache_root, readiness)
    snapshot = readiness.snapshot()
    ready = bool(snapshot.consistent) and not bool(snapshot.in_progress)
    print(json.dumps({
        "status": "ok",
        "ready": ready,
        "current_head": snapshot.current_head,
        "last_hydrate_at": snapshot.last_hydrate_at,
        "reason": snapshot.reason,
    }))
    return 0 if ready else 1


def _cmd_serve(args: argparse.Namespace) -> int:
    """Serve the human UI API, static frontend, MCP endpoint, and optional A2A surface."""
    from ..adapters.ui import (
        OPEN_WEBUI_FLAG,
        OpenAiCompatShim,
        UiHttpServer,
        build_flag_registry,
        build_ui_service,
        is_open_webui_enabled,
    )
    from ..core.control.flags import FeatureFlagScope, FeatureFlagState
    from ..ports.ui.rest_api import QueryRequest, UiActor

    target = Path(getattr(args, "target", Path.cwd())).resolve()
    cache_root = _resolve_cache_root(args)
    service, readiness = build_ui_service(
        repo_root=target,
        cache_root=cache_root,
        hydrate_on_start=False,
        defer_runtime=True,
    )
    readiness.begin_refresh()
    mcp_server, skill_plane, a2a_adapter, agent_card = (
        _build_embedded_mcp_and_a2a(
            target=target,
            cache_root=cache_root,
            service=service,
            readiness=readiness,
        )
    )
    registry = build_flag_registry()
    # Operator override path: ``PI_OPEN_WEBUI_ADAPTER=0`` flips the flag off;
    # ``PI_OPEN_WEBUI_ADAPTER=1`` keeps it on. The default is ON so the
    # local model bundled in ``desktop-lite`` is wired up out of the box.
    flag_override = os.environ.get("PI_OPEN_WEBUI_ADAPTER")
    if flag_override == "0":
        registry.override(
            OPEN_WEBUI_FLAG,
            state=FeatureFlagState.DISABLED,
            scope=FeatureFlagScope.DEPLOYMENT_PROFILE,
            scope_key=os.environ.get("PI_PROFILE", ""),
        )
    # Build a stable actor used by the OpenAI-compatible shim. The
    # ``RestService`` accepts a ``UiActor`` per operation; we reuse the same
    # default the HTTP server initialises with so chat-completion requests
    # are indistinguishable from the ``/api/v1/query`` path.
    shim_actor = UiActor(
        actor_type="agent",
        actor_id="open-webui-adapter",
        role="viewer",
    )
    shim = OpenAiCompatShim(
        lambda prompt: service.query(shim_actor, QueryRequest(text=prompt)),
        flag=lambda: is_open_webui_enabled(
            registry,
            deployment_profile=os.environ.get("PI_PROFILE", ""),
        ),
        model=os.environ.get("PI_OPENAI_MODEL") or None,
        base_url=os.environ.get("PI_OPENAI_BASE_URL") or None,
    )
    server = UiHttpServer(
        service,
        host=args.host,
        port=args.port,
        readiness=lambda: readiness.is_ready(),
        openai_compat=shim,
        mcp_server=mcp_server,
        skill_plane=skill_plane,
        a2a_adapter=a2a_adapter,
        agent_card=agent_card,
    )
    from ..core.sync.version_monitor import PollingProjectVersionMonitor
    import threading

    first_refresh = True

    def refresh(_event):
        nonlocal first_refresh
        summary = _bootstrap_and_index_target(
            target,
            model_alias=getattr(args, "model", None) if first_refresh else None,
            device=getattr(args, "device", None) if first_refresh else None,
            service=service,
            readiness=readiness,
            cache_root=cache_root,
        )
        first_refresh = False
        print(json.dumps({"status": "ready", **summary}), flush=True)

    def failed(exc):
        readiness.record_failure(str(exc))
        readiness.end_refresh()
        print(json.dumps({"status": "refresh-failed", "error": str(exc)}), flush=True)

    def execute_admin_job(kind, details):
        if kind == "reindex":
            _bootstrap_and_index_target(
                target, service=service, readiness=readiness, cache_root=cache_root,
            )
        elif kind == "models.pull":
            result = _cmd_models_pull(argparse.Namespace(target=target, alias=details["alias"]))
            if result:
                raise RuntimeError("Model download failed; inspect the model cache and connection")
        else:
            raise ValueError(f"Unsupported administrative job: {kind}")

    server.admin_routes.job_executor = execute_admin_job
    monitor = PollingProjectVersionMonitor(target, on_change=refresh, on_error=failed)
    server.refresh_requested = monitor.request_refresh
    server.start_background()
    print(json.dumps({
        "status": "listening", "url": server.address, "target": str(target),
        "ready": False, "mcp_endpoint": f"{server.address}/mcp",
    }), flush=True)
    monitor.start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:  # pragma: no cover - operator interrupt
        pass
    finally:
        monitor.stop()
        server.stop()
    return 0


def _cmd_mcp_serve(args: argparse.Namespace) -> int:
    """Serve the §36 MCP tool and §38 skill distribution surface over stdio or HTTP."""
    from ..adapters.ui import build_ui_service

    target = Path(getattr(args, "target", Path.cwd())).resolve()
    cache_root = _resolve_cache_root(args)
    auto_hydrate = os.environ.get("PI_AUTO_HYDRATE", "1") != "0"
    service, readiness = build_ui_service(
        repo_root=target,
        cache_root=cache_root,
        hydrate_on_start=False,
        defer_runtime=True,
    )
    from ..core.sync.version_monitor import PollingProjectVersionMonitor
    def refresh(_event):
        _bootstrap_and_index_target(target, service=service, readiness=readiness, cache_root=cache_root)
    def failed(exc):
        readiness.record_failure(str(exc))
        readiness.end_refresh()
    monitor = PollingProjectVersionMonitor(target, on_change=refresh, on_error=failed)
    if auto_hydrate:
        try:
            monitor.poll_once()
        except Exception as exc:
            failed(exc)
    else:
        readiness.record_failure("Automatic hydrate disabled; no active runtime published")
    if auto_hydrate:
        monitor.start()
    debug_flag = True if getattr(args, "debug", False) else None
    mcp_server, skill_plane, a2a_adapter, agent_card = (
        _build_embedded_mcp_and_a2a(
            target=target,
            cache_root=cache_root,
            service=service,
            readiness=readiness,
            debug_mode=debug_flag,
        )
    )
    transport = getattr(args, "transport", "stdio")
    if transport == "http":
        from ..adapters.ui import UiHttpServer

        server = UiHttpServer(
            service,
            host=args.host,
            port=args.port,
            readiness=lambda: readiness.is_ready(),
            mcp_server=mcp_server,
            skill_plane=skill_plane,
            a2a_adapter=a2a_adapter,
            agent_card=agent_card,
        )
        server.refresh_requested = monitor.request_refresh
        try:
            server.serve_forever()
        except KeyboardInterrupt:  # pragma: no cover
            pass
        finally:
            monitor.stop()
            server.stop()
        return 0
    try:
        return mcp_server.serve_stdio_fallback(skill_plane=skill_plane)
    finally:
        monitor.stop()


def _cmd_a2a_serve(args: argparse.Namespace) -> int:
    """Serve the §50 A2A HTTP transport and Agent Card."""
    from ..adapters.a2a.http_transport import (
        A2aHttpServer,
        A2aHttpServerConfig,
    )
    from ..core.a2a import A2aAdapterCore, AgentCardBuilder

    adapter = A2aAdapterCore(
        flags_provider=lambda _: True,
        policy_gate=lambda **_: "ALLOW",
    )
    card = AgentCardBuilder(
        descriptor={
            "name": "project-intelligence",
            "description": "Project Intelligence Platform",
            "version": "0.8.0",
            "protocols": {
                "a2a": {
                    "supported_protocols": ("jsonrpc-2.0",),
                    "version": "1.0",
                }
            },
            "skills": [
                {
                    "id": "project-intelligence",
                    "description": "Retrieval-first project intelligence",
                    "tags": ["retrieval", "mcp", "okf"],
                }
            ],
        },
        flags_provider=lambda _: True,
        published=True,
    )
    server = A2aHttpServer(
        adapter=adapter,
        agent_card=card,
        config=A2aHttpServerConfig(host=args.host, port=args.port),
        token_provider=lambda: os.environ.get("PI_UI_TOKEN") or None,
    )
    host, port = server.start()
    print(json.dumps({
        "status": "listening",
        "url": f"http://{host}:{port}",
        "agent_card": f"http://{host}:{port}/.well-known/agent-card.json",
        "tasks_send": f"http://{host}:{port}/a2a/v1/tasks:send",
    }), flush=True)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.stop()
    return 0


def _cmd_package_plugins(args: argparse.Namespace) -> int:
    """Generate the four deterministic vendor plugin bundles (§41–§45)."""
    from ..adapters.agent_integration.packagers.codex import ReleaseInputSet
    from ..adapters.agent_integration.packagers.runner import (
        DeterministicBuildRunner,
    )
    from ..core.agent_integration.supply_chain_gate import (
        PluginSupplyChainSecurityGate,
    )

    skills_root = args.skills_root or _resolve_skills_root()
    if skills_root is None or not (skills_root / "project-intelligence" / "SKILL.md").is_file():
        print(json.dumps({
            "ok": False,
            "error": f"canonical skill not found under {skills_root!r}",
        }), file=sys.stderr)
        return 2
    skill_md = skills_root / "project-intelligence" / "SKILL.md"
    skill_sha = hashlib.sha256(skill_md.read_bytes()).hexdigest()
    release = ReleaseInputSet(
        skill_version="1.0.0",
        skill_sha256=skill_sha,
        mcp_api_range=">=1.3.0 <2.0.0",
        license="Apache-2.0",
        server_version="0.8.0",
        mcp_endpoint="http://127.0.0.1:8765/mcp",
        okf_profile_versions=("0.2",),
        source_repository="https://github.com/Shkirmantsev/ProjectExpert",
    )
    output_root = Path(args.output_root).resolve()
    runner = DeterministicBuildRunner(
        skills_root=skills_root,
        gate=PluginSupplyChainSecurityGate(),
    )
    result = runner.build(release, output_root=output_root)
    inventory = runner.combined_inventory(result)
    print(json.dumps({
        "ok": True,
        "output_root": str(output_root),
        "vendors": sorted(result.verdicts.keys()),
        "files_generated": len(inventory),
        "shared_release_identity": dict(result.shared_release_identity),
    }, indent=2))
    return 0


def _cmd_runtime_status(args: argparse.Namespace) -> int:
    from ..adapters.runtime.sqlite_runtime_store import SqliteRuntimeStore
    from ..core.canonical.value_types import ProjectVersion

    target = args.target.resolve()
    cache_root = _resolve_cache_root(args)
    version = compute_version_identity(target)
    store = SqliteRuntimeStore(cache_root=cache_root, version=ProjectVersion(
        gitHead=version.gitHead,
        workingTreeFingerprint=version.workingTreeFingerprint,
        knowledgeSchemaVersion=version.knowledgeSchemaVersion,
        embeddingModelVersion=version.embeddingModelVersion,
        indexSchemaVersion=version.indexSchemaVersion,
    ))
    report = store.runtime_status(policy=args.policy)
    payload = {
        "bound_version": {
            "gitHead": report.bound_version.gitHead,
            "workingTreeFingerprint": report.bound_version.workingTreeFingerprint,
            "knowledgeSchemaVersion": report.bound_version.knowledgeSchemaVersion,
            "embeddingModelVersion": report.bound_version.embeddingModelVersion,
            "indexSchemaVersion": report.bound_version.indexSchemaVersion,
        },
        "backend": report.backend,
        "cache_entries": report.cache_entries,
        "wal_tail_length": report.wal_tail_length,
        "families": list(report.families),
        "family_counts": dict(report.family_counts),
        "policy": args.policy,
        "cache_root": str(cache_root),
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_graph_rebuild(args: argparse.Namespace) -> int:
    from ..adapters.runtime.sharded_graph import LocalShardedGraph

    graph_root = args.cache_root
    if not graph_root.is_absolute():
        graph_root = args.target.resolve() / graph_root
    graph = LocalShardedGraph(graph_root)
    manifest = graph.rebuild_manifest()
    payload = {
        "graph_root": str(graph_root),
        "family": manifest.family,
        "schemaVersion": manifest.schemaVersion,
        "entity_count": manifest.entity_count,
        "relation_count": manifest.relation_count,
        "shards": [
            {"id": s.id, "path": s.path, "count": s.count}
            for s in manifest.shards
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


def _project_id(target: Path) -> str:
    """Return a stable, cross-platform project lock identifier.

    Uses the SHA-256 hex digest of the resolved canonical path so the
    lock filename is safe on every platform (no ``:`` on Windows, no
    ``/`` anywhere) and two distinct projects can never share a lock
    even when their paths differ only in case or symlink resolution.
    The digest is also stable across runs, which lets an operator
    inspect / correlate ``tmp/local/project-locks/<id>.lock`` files
    without leaking the absolute path.
    """

    canonical = str(target.resolve()).lower()
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"proj-{digest}"


# ---------------------------------------------------------------------------
# Phase 10 §49 + §120 quality-gates subcommands
# ---------------------------------------------------------------------------


def _run_unittest_module(module_name: str) -> int:
    """Run a single ``unittest`` module programmatically and return its exit code.

    Phase 10 keeps the runner zero-dependency: ``unittest`` is in the
    standard library and the test modules are direct children of
    ``tests/``. The harness never shells out to ``python -m unittest``
    so the caller's environment stays inside the same process tree.
    """
    return 0 if eval_runner.run_unittest_module(module_name).ok else 1


def _cmd_eval(args: argparse.Namespace) -> int:
    """Run the §49 integration-quality-gates suites and record their metrics.

    When an optional ``eval_subcommand`` (``retrieval`` or
    ``chunk-size-sweep``) is supplied, dispatch to the Tier-3
    retrieval evaluation or chunk-size sweep handler so
    ``project-intelligence eval retrieval`` works alongside the
    Phase 10 ``project-intelligence eval`` command.
    """
    subcommand = getattr(args, "eval_subcommand", None)
    if subcommand == "retrieval":
        return _cmd_eval_retrieval(args)
    if subcommand == "chunk-size-sweep":
        return _cmd_eval_chunk_size_sweep(args)
    outcome = eval_runner.run_unittest_module(eval_runner.QUALITY_GATES_SUITE)
    report = eval_runner.eval_report(outcome)
    path = eval_runner.write_report(report)
    print(json.dumps({
        **outcome.as_dict(),
        "scope": report.scope,
        "metrics_file": str(path),
    }, indent=2))
    return outcome.exit_code


def _cmd_invariants(args: argparse.Namespace) -> int:
    """Run the §120 52-invariant §68 acceptance suite.

    Every probe is executed and reported as ``invariants_run`` /
    ``invariants_passed``; additionally each probe body is classified
    so the report states the honest ``invariants_enforced`` /
    ``invariants_declared`` split instead of implying that all 52
    probes contain real checks.
    """
    outcome = eval_runner.run_unittest_module(eval_runner.INVARIANTS_SUITE)
    summary = eval_runner.probe_summary()
    report = eval_runner.invariants_report(outcome, summary)
    path = eval_runner.write_report(report)
    print(json.dumps({
        **outcome.as_dict(),
        "scope": report.scope,
        "metrics_file": str(path),
        "invariants_run": summary.total,
        "invariants_passed": summary.passed,
        "invariants_failed": summary.failed,
        "invariants_enforced": summary.enforced,
        "invariants_declared": summary.declared,
    }, indent=2))
    if summary.failed:
        return 1
    return outcome.exit_code


def _cmd_eval_retrieval(args: argparse.Namespace) -> int:
    """Run the v0.8 Tier-3 retrieval evaluation.

    Uses :mod:`pi_platform.core.eval.tier3_commands` directly so the
    command runs inside the standalone container without requiring the
    host ``scripts/`` directory.
    """
    from ..core.eval import tier3_commands as _tier3

    baseline_path = None if args.no_baseline else args.baseline
    out_path = args.out or Path("evals/reports/tier3_retrieval.json")
    try:
        runtime_kwargs = {}
        if getattr(args, "target", None) is not None:
            from pi_platform.adapters.ui.composition import build_ui_service
            target = Path(args.target).resolve()
            service, readiness = build_ui_service(repo_root=target, defer_runtime=True)
            _bootstrap_and_index_target(target, service=service, readiness=readiness)
            runtime_kwargs["pipeline"] = service._retrieval
        payload = _tier3.run_eval(
            golden_path=args.golden,
            corpus_root=args.corpus_root,
            out_path=out_path,
            baseline_path=baseline_path,
            **runtime_kwargs,
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "ok": False, "error": str(exc),
            "scope": "tier-3-retrieval",
        }), file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "scope": payload["scope"],
        "aggregate": payload["aggregate"],
        "out_path": str(out_path),
        "queries_run": len(payload["rows"]),
    }, indent=2))
    return 0


def _cmd_eval_chunk_size_sweep(args: argparse.Namespace) -> int:
    """Run the v0.8 Tier-3 chunk-size sweep.

    Uses :mod:`pi_platform.core.eval.tier3_commands` directly so the
    command runs inside the standalone container without requiring the
    host ``scripts/`` directory.
    """
    from ..core.eval import tier3_commands as _tier3

    out_path = args.out or Path("evals/reports/chunk_size_sweep.json")
    try:
        payload = _tier3.run_chunk_size_sweep(
            golden_path=args.golden,
            corpus_root=args.corpus_root,
            out_path=out_path,
            report_path=args.report,
            budgets=tuple(args.budgets),
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "ok": False, "error": str(exc),
            "scope": "tier-3-chunk-size-sweep",
        }), file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "scope": payload["scope"],
        "selected_default_budget": payload["selected_default_budget"],
        "out_path": str(out_path),
        "report_path": str(args.report),
    }, indent=2))
    return 0


def _cmd_metrics_gate(args: argparse.Namespace) -> int:
    """Verify the last ``eval/last.json`` metrics are within the documented thresholds.

    Exit codes: ``0`` all present metrics within bounds, ``1``
    schema/shape/bound violation (a JSON list of the offending metric
    names is printed on stdout), ``2`` metrics file missing.
    """
    target = eval_runner.resolve_metrics_path()
    if not target.exists():
        print(json.dumps({
            "error": "eval metrics file not found",
            "path": str(target),
        }), file=sys.stderr)
        return 2
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(json.dumps({
            "error": "eval metrics file is not valid JSON",
            "path": str(target),
            "detail": str(exc),
        }), file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print(json.dumps({
            "error": "eval metrics file must be a JSON object",
            "path": str(target),
        }), file=sys.stderr)
        return 1
    schema = payload.get("schema") or {}
    if schema.get("name") != "phase-10-eval" or schema.get("version") != "1":
        print(json.dumps({
            "error": "eval metrics schema mismatch",
            "schema": schema,
        }), file=sys.stderr)
        return 1
    violations = validate_metrics(payload.get("metrics"))
    if violations:
        print(json.dumps({
            "ok": False,
            "violations": [v.metric for v in violations],
            "details": [v.as_dict() for v in violations],
            "metrics_file": str(target),
        }, indent=2))
        return 1
    print(json.dumps({
        "ok": True,
        "scope": payload.get("scope"),
        "metrics_file": str(target),
    }))
    return 0


def _cmd_accelerator(args: argparse.Namespace) -> int:
    """Manage the host-side embedding accelerator (G)."""
    from ..host_accelerator.config import (
        AcceleratorConfig,
    )
    from ..host_accelerator.bootstrap import bootstrap_all
    from ..host_accelerator.security import (
        ModelAllowList,
        TokenStore,
    )
    from ..host_accelerator.server import (
        AcceleratorService,
        build_default_embedding_models,
    )
    from ..ports.retrieval.embedding_profile import (
        EMBEDDINGGEMMA2_512,
        HASHING_DEFAULT,
        QWEN3_EMBEDDING_0_6B_1024,
    )

    def _build_config() -> AcceleratorConfig:
        kwargs: dict = {}
        if args.bind_host is not None:
            kwargs["bind_address"] = args.bind_host
        if args.bind_port is not None:
            kwargs["port"] = args.bind_port
        if args.max_concurrent_requests is not None:
            kwargs["max_concurrent_requests"] = (
                args.max_concurrent_requests
            )
        return AcceleratorConfig(**kwargs)

    config = _build_config()
    if args.accelerator_command == "status":
        # Connect to /health on the configured port.
        import urllib.error
        import urllib.request
        url = f"http://{config.bind_address}:{config.port}/health"
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                body = resp.read().decode("utf-8")
                print(json.dumps({
                    "status": "running",
                    "url": url,
                    "health": json.loads(body),
                }, indent=2))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(json.dumps({
                "status": "stopped",
                "url": url,
                "reason": str(exc),
            }, indent=2))
        return 0
    if args.accelerator_command == "stop":
        # Send a SIGTERM to the pidfile.
        import signal as _sig
        pidfile = os.path.join(
            os.path.dirname(config.audit_log_path), "pid",
        )
        if not os.path.isfile(pidfile):
            print(json.dumps({
                "status": "stopped", "reason": "no pidfile",
            }, indent=2))
            return 0
        with open(pidfile, "r", encoding="utf-8") as f:
            try:
                pid = int(f.read().strip())
            except ValueError:
                print(json.dumps({
                    "status": "error", "reason": "bad pidfile",
                }, indent=2))
                return 1
        try:
            os.kill(pid, _sig.SIGTERM)
        except ProcessLookupError:
            print(json.dumps({
                "status": "stopped", "reason": "process not found",
            }, indent=2))
            os.unlink(pidfile)
            return 0
        print(json.dumps({"status": "stopping", "pid": pid}, indent=2))
        return 0
    # start
    profiles = {
        HASHING_DEFAULT.identity(): HASHING_DEFAULT,
        EMBEDDINGGEMMA2_512.identity(): EMBEDDINGGEMMA2_512,
        QWEN3_EMBEDDING_0_6B_1024.identity(): QWEN3_EMBEDDING_0_6B_1024,
    }
    token, log, al = bootstrap_all(config)
    embedding_models = build_default_embedding_models(profiles)
    service = AcceleratorService(
        config=config,
        token_store=TokenStore(config.token_path),
        allow_list=al,
        audit_log=log,
        embedding_models=embedding_models,
        profiles_by_id=profiles,
    )
    service.serve_forever()
    pidfile = os.path.join(
        os.path.dirname(config.audit_log_path), "pid",
    )
    os.makedirs(os.path.dirname(pidfile), exist_ok=True)
    with open(pidfile, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    print(json.dumps({
        "status": "started",
        "url": f"http://{config.bind_address}:{config.port}",
        "token_path": config.token_path,
        "audit_log_path": config.audit_log_path,
    }, indent=2))
    print(f"press Ctrl-C to stop (pidfile: {pidfile})")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        service.shutdown()
        try:
            os.unlink(pidfile)
        except FileNotFoundError:
            pass
    return 0


_DISPATCH = {
    "init-project": _cmd_init_project,
    "hydrate": _cmd_hydrate,
    "materialise": _cmd_materialise,
    "license-gate": _cmd_license_gate,
    "okf-validate": _cmd_okf_validate,
    "version-identity": _cmd_version_identity,
    "wal-recover": _cmd_wal_recover,
    "health": _cmd_health,
    "serve": _cmd_serve,
    "mcp-serve": _cmd_mcp_serve,
    "a2a-serve": _cmd_a2a_serve,
    "package-plugins": _cmd_package_plugins,
    "ingest-sources": _cmd_ingest_sources,
    "runtime-status": _cmd_runtime_status,
    "graph-rebuild": _cmd_graph_rebuild,
    "eval": _cmd_eval,
    "invariants": _cmd_invariants,
    "metrics-gate": _cmd_metrics_gate,
    "eval-retrieval": _cmd_eval_retrieval,
    "eval-chunk-size-sweep": _cmd_eval_chunk_size_sweep,
    "accelerator": _cmd_accelerator,
}


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _parse_args(argv)
    handler = _DISPATCH.get(args.command)
    if handler is None:
        print(json.dumps({"error": f"unknown command {args.command!r}"}), file=sys.stderr)
        return 2
    try:
        return handler(args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Phase 4 retrieval subcommands
# ---------------------------------------------------------------------------


def _cmd_embedding_status(args: argparse.Namespace) -> int:
    """Report the active §25 EmbeddingModelPort status via resolved runtime configuration."""

    from ..adapters.config.runtime_configuration_resolver import (
        LOCAL_SETTINGS_RELATIVE_PATH,
        RuntimeConfigurationResolver,
    )
    from ..adapters.retrieval.embedding_model_factory import (
        EmbeddingModelFactory,
    )
    from ..adapters.retrieval.multilingual_st_embedding_model import (
        ADAPTER_NAME as _MULTILINGUAL_NAME,
        DEFAULT_LICENSE_ID,
        EXPECTED_DIMENSION,
        MultilingualSentenceTransformerEmbeddingModel,
    )

    target = Path(getattr(args, "target", Path("."))).resolve()
    cfg = RuntimeConfigurationResolver(
        local_settings_path=target / LOCAL_SETTINGS_RELATIVE_PATH,
    ).resolve()
    factory = EmbeddingModelFactory(startup_profile=cfg.startup_profile)
    adapter = factory.build(cfg.embedding_model, device=cfg.embedding_device, cache_folder=str(Path(cfg.model_cache_dir) / "hub"))
    profile = adapter.profile()
    backend_name = cfg.embedding_model
    model_version = adapter.model_version()
    license_id = adapter.license_id()
    dimension = adapter.dimension()
    try:
        MultilingualSentenceTransformerEmbeddingModel()
        multilingual_available = True
    except Exception:
        multilingual_available = False
    payload = {
        "active_backend": backend_name,
        "active_model_id": getattr(profile, "model_id", backend_name),
        "active_model_revision": getattr(profile, "model_revision", ""),
        "active_profile_identity": profile.identity() if profile else "",
        "active_device": getattr(adapter, "_device", cfg.embedding_device),
        "startup_profile": cfg.startup_profile,
        "active_model_version": model_version,
        "active_license_id": license_id,
        "active_dimension": dimension,
        "multilingual_available": multilingual_available,
        "multilingual_adapter_name": _MULTILINGUAL_NAME,
        "multilingual_default_model_id": "paraphrase-multilingual-MiniLM-L12-v2",
        "multilingual_default_license_id": DEFAULT_LICENSE_ID,
        "multilingual_expected_dimension": EXPECTED_DIMENSION,
        "stats": dict(adapter.stats()),
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_reranker_status(args: argparse.Namespace) -> int:
    """Report the active §30 RerankerPort status."""

    from ..adapters.retrieval.bm25_light_reranker import (
        Bm25LightRerankerAdapter,
    )
    from ..adapters.retrieval.cross_encoder_reranker import (
        ADAPTER_NAME as _CROSS_ENCODER_NAME,
        CrossEncoderRerankerAdapter,
    )
    from ..adapters.retrieval.colbert_style_reranker import (
        ADAPTER_NAME as _COLBERT_NAME,
        ColBertStyleRerankerAdapter,
    )

    bm25 = Bm25LightRerankerAdapter()
    payload = {
        "active_family": bm25.family(),
        "active_model_version": bm25.model_version(),
        "active_license_id": bm25.license_id(),
        "budget": bm25.budget,
        "stats": dict(bm25.stats()),
    }
    for label, adapter_cls, name in (
        ("cross-encoder", CrossEncoderRerankerAdapter, _CROSS_ENCODER_NAME),
        ("colbert-style", ColBertStyleRerankerAdapter, _COLBERT_NAME),
    ):
        try:
            adapter_cls()
            available = True
        except Exception:
            available = False
        payload[f"{label}_available"] = available
        payload[f"{label}_adapter_name"] = name
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_retrieval_status(args: argparse.Namespace) -> int:
    """Report the Phase 4 & production retrieval pipeline status."""

    from ..adapters.config.runtime_configuration_resolver import (
        LOCAL_SETTINGS_RELATIVE_PATH,
        RuntimeConfigurationResolver,
    )
    from ..adapters.retrieval.bm25_light_reranker import Bm25LightRerankerAdapter
    from ..adapters.retrieval.context_assembler_adapter import (
        ContextAssemblerAdapter,
    )
    from ..adapters.retrieval.embedding_model_factory import (
        EmbeddingModelFactory,
    )
    from ..adapters.retrieval.hybrid_retrieval import HybridRetrievalAdapter
    from ..adapters.retrieval.identifier_query_detector import (
        IdentifierQueryDetector,
    )
    from ..adapters.retrieval.metadata_filter_adapter import (
        MetadataFilterAdapter,
    )
    from ..adapters.runtime.graph_expansion import (
        DEFAULT_BUDGET as _PRODUCTION_GRAPH_BUDGET,
        DEFAULT_EDGE_TYPES as _PRODUCTION_GRAPH_EDGE_TYPES,
        ProductionGraphExpansion,
    )
    from ..adapters.ui import load_persisted_readiness
    from ..core.retrieval.multi_stage_retrieval import (
        DEFAULT_BUDGETS as _DEFAULT_STAGE_BUDGETS,
    )
    from ..core.sync.readiness import DefaultKnowledgeReadiness
    from ..core.sync.version_snapshot import RuntimeSnapshotService

    target = Path(getattr(args, "target", Path("."))).resolve()
    cache_root = target / DEFAULT_RUNTIME_CACHE
    cfg = RuntimeConfigurationResolver(
        local_settings_path=target / LOCAL_SETTINGS_RELATIVE_PATH,
    ).resolve()
    factory = EmbeddingModelFactory(startup_profile=cfg.startup_profile)
    profile = factory.resolve_profile(cfg.embedding_model)
    readiness = DefaultKnowledgeReadiness()
    load_persisted_readiness(cache_root, readiness)
    snap_service = RuntimeSnapshotService(cache_root=cache_root)
    persisted_snap = snap_service.read_snapshot()
    current_generation = (
        persisted_snap.active.active_index_generation
        if persisted_snap is not None
        else "unindexed"
    )
    vector_count = 0
    index_count = 0
    index_meta_path = cache_root / "indexes" / "index_meta.json"
    if index_meta_path.is_file():
        try:
            meta = json.loads(index_meta_path.read_text(encoding="utf-8"))
            vector_count = int(meta.get("vector_count", 0))
            index_count = 1
        except Exception:
            pass

    hybrid = HybridRetrievalAdapter(
        dense_query=lambda text, k: (),
        sparse_query=lambda text, k: (),
    )
    try:
        from ..core.retrieval.selection import SelectionCore as _SelectionCore
        from ..ports.retrieval.selection import (
            DEFAULT_PRIMARY_TOP_K as _SELECTION_PRIMARY_TOP_K,
        )

        _selection_class_name = _SelectionCore.__name__
        _selection_primary_top_k = _SELECTION_PRIMARY_TOP_K
    except Exception:
        _selection_class_name = ""
        _selection_primary_top_k = 0
    payload = {
        "active_model": cfg.embedding_model,
        "active_model_id": profile.model_id,
        "active_embedding_profile_identity": profile.identity(),
        "dense_backend": cfg.dense_index,
        "current_generation": current_generation,
        "vector_count": vector_count,
        "index_count": index_count,
        "sparse_index": "bm25-sqlite",
        "ready": readiness.is_ready(),
        "active_fusion_strategy": hybrid.fusion_strategy,
        "hybrid_level": hybrid.stats().get("level", 0),
        "identifier_detector": IdentifierQueryDetector.name,
        "metadata_filter_adapter": "metadata-filter-default",
        "context_assembler_adapter": "context-assembler-default",
        "reranker_family": Bm25LightRerankerAdapter().family(),
        "production_graph_expansion": {
            "default_budget": _PRODUCTION_GRAPH_BUDGET,
            "default_edge_types": list(_PRODUCTION_GRAPH_EDGE_TYPES),
        },
        "stage_budgets": dict(_DEFAULT_STAGE_BUDGETS),
        "selection_core_class": _selection_class_name,
        "selection_default_primary_top_k": _selection_primary_top_k,
        "stats": {
            "hybrid": dict(hybrid.stats()),
            "metadata": dict(MetadataFilterAdapter().stats()),
            "context_assembler": dict(ContextAssemblerAdapter().stats()),
            "reranker": dict(Bm25LightRerankerAdapter().stats()),
        },
    }
    payload["graph_expansion_class"] = ProductionGraphExpansion.__name__
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_orchestrator_status(args: argparse.Namespace) -> int:
    """Report the Phase 5 §34 query orchestrator status."""

    from ..adapters.orchestration.query_orchestrator import (
        DefaultQueryOrchestratorAdapter,
    )
    from ..adapters.orchestration.stub_local_llm import (
        StubLocalLLMAdapter,
    )
    from ..adapters.orchestration.task_context import (
        DefaultTaskContextBuilderAdapter,
    )
    from ..adapters.runtime.graph_expansion import (
        ProductionGraphExpansion,
    )
    from ..adapters.retrieval.bm25_light_reranker import (
        Bm25LightRerankerAdapter,
    )
    from ..adapters.retrieval.context_assembler_adapter import (
        ContextAssemblerAdapter,
    )
    from ..adapters.retrieval.hybrid_retrieval import (
        HybridRetrievalAdapter,
    )
    from ..adapters.retrieval.metadata_filter_adapter import (
        MetadataFilterAdapter,
    )
    from ..core.retrieval.multi_stage_retrieval import (
        MultiStageRetrievalCore,
    )

    hybrid = HybridRetrievalAdapter(
        dense_query=lambda text, k: (),
        sparse_query=lambda text, k: (),
    )
    try:
        from ..core.retrieval.selection import SelectionCore as _SelectionCore

        _selection = _SelectionCore()
    except Exception:
        _selection = None
    pipeline = MultiStageRetrievalCore(
        hybrid=hybrid,
        metadata=MetadataFilterAdapter(),
        graph_expansion=ProductionGraphExpansion(_GraphAdapter()),
        reranker=Bm25LightRerankerAdapter(),
        context_assembler=ContextAssemblerAdapter(),
        selection=_selection,
    )
    local_llm = StubLocalLLMAdapter()
    builder = DefaultTaskContextBuilderAdapter()
    orchestrator = DefaultQueryOrchestratorAdapter(
        retrieval=pipeline,
        local_llm=local_llm,
        task_context_builder=builder,
    )
    payload = {
        "active_backend": "query-orchestrator-default",
        "levels": {
            "L0": "direct retrieval",
            "L1": "retrieval + small local LLM",
            "L2": "strong external agent (task context bundle)",
        },
        "default_level": int(orchestrator.stats() and 0),
        "local_llm_available": local_llm.is_available(),
        "local_llm_family": local_llm.family(),
        "local_llm_license": local_llm.license_id(),
        "task_context_knowledge_schema_version": builder._knowledge_schema_version,
        "task_context_okf_versions": list(builder._okf_versions),
        "stats": dict(orchestrator.stats()),
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_llm_status(args: argparse.Namespace) -> int:
    """Report the active §35 LocalLLMPort status."""

    from ..adapters.orchestration.stub_local_llm import (
        StubLocalLLMAdapter,
    )

    stub = StubLocalLLMAdapter()
    payload = {
        "active_backend": "local-llm-stub",
        "is_available": stub.is_available(),
        "family": stub.family(),
        "model_version": stub.model_version(),
        "license_id": stub.license_id(),
        "stats": dict(stub.stats()),
        "opt_in_families": ["llama-cpp", "transformers", "external-llm"],
        "note": "default container ships with the stub only; opt-in "
                "LLM backends register as adapters when the "
                "corresponding Python package is installed AND "
                "project-context.yaml:orchestrator.local_llm.family "
                "is set to the family's name.",
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_capabilities(args: argparse.Namespace) -> int:
    """Print the §47 capability discovery descriptor and production capability report."""

    from ..adapters.config.runtime_configuration_resolver import (
        LOCAL_SETTINGS_RELATIVE_PATH,
        RuntimeConfigurationResolver,
    )
    from ..adapters.orchestration.capability_discovery import (
        DefaultCapabilityDiscoveryAdapter,
    )
    from ..adapters.orchestration.stub_local_llm import (
        StubLocalLLMAdapter,
    )
    from ..adapters.retrieval.embedding_model_factory import (
        EmbeddingModelFactory,
    )
    from ..core.orchestration.production_capability_discovery import (
        build_production_capability_report,
    )

    target = Path(getattr(args, "target", Path("."))).resolve()
    cfg = RuntimeConfigurationResolver(
        local_settings_path=target / LOCAL_SETTINGS_RELATIVE_PATH,
    ).resolve()
    factory = EmbeddingModelFactory(startup_profile=cfg.startup_profile)
    adapter = factory.build(cfg.embedding_model, device=cfg.embedding_device, cache_folder=str(Path(cfg.model_cache_dir) / "hub"))
    prod_report = build_production_capability_report(
        embedding_adapter=adapter,
        embedding_provider=cfg.embedding_model,
        dense_backend_name=cfg.dense_index,
        docling_enabled=cfg.docling_enabled,
    )
    discovery = DefaultCapabilityDiscoveryAdapter(
        retrieval=object(),
        graph_expansion=object(),
        materialisation=object(),
        local_llm=StubLocalLLMAdapter(),
    )
    payload = discovery.describe().as_dict()
    payload["productionCapabilities"] = prod_report.as_dict()
    print(json.dumps(payload, indent=2))
    return 0


class _GraphAdapter:
    """In-memory graph stub used by the orchestrator-status CLI."""

    def expand(self, seeds, *, hops, edge_types, budget):
        from pi_platform.ports.runtime.graph_expansion import GraphExpansion
        return GraphExpansion(
            seeds=tuple(seeds), expandedEntities=(),
            expandedRelations=(), hops=hops, budget_exhausted=False,
        )

    def stats(self) -> dict:
        return {}


_DISPATCH.update(
    {
        "embedding-status": _cmd_embedding_status,
        "retrieval-status": _cmd_retrieval_status,
        "reranker-status": _cmd_reranker_status,
        "orchestrator-status": _cmd_orchestrator_status,
        "llm-status": _cmd_llm_status,
        "capabilities": _cmd_capabilities,
    }
)


# ---------------------------------------------------------------------------
# One-command production UX (open spec change PR 11, plan §15–§18)
# ---------------------------------------------------------------------------


_MODEL_VERIFY_FILES = (
    "sentence_bert_config.json",
    "tokenizer.json",
    "config.json",
)


def _resolve_model_licenses_path(target: Optional[Path] = None) -> Optional[Path]:
    """Locate ``distribution/licenses/model-licenses.json``."""

    candidates: list[Path] = []
    if target is not None:
        candidates.append(Path(target).resolve() / "distribution" / "licenses"
                          / "model-licenses.json")
    candidates.append(Path.cwd() / "distribution" / "licenses"
                      / "model-licenses.json")
    platform_home = os.environ.get("PI_PLATFORM_HOME")
    if platform_home:
        candidates.append(Path(platform_home) / "distribution" / "licenses"
                          / "model-licenses.json")
    candidates.append(
        Path(__file__).resolve().parents[2] / "distribution" / "licenses"
        / "model-licenses.json"
    )
    candidates.append(Path(sys.prefix) / "distribution" / "licenses" / "model-licenses.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _resolve_model_alias_and_id(value: str) -> tuple[str, str]:
    """Return ``(alias, huggingface_model_id)`` for a CLI model argument."""

    from ..core.control.retrieval_settings import (
        PRODUCTION_ALIAS_TO_MODEL_ID,
        normalise_model_alias,
    )

    alias = normalise_model_alias(value)
    return alias, PRODUCTION_ALIAS_TO_MODEL_ID[alias]


def _local_hf_snapshot(model_id: str) -> Optional[Path]:
    """Find only the selected immutable revision, without any network access."""
    from ..adapters.retrieval.embedding_model_factory import EmbeddingModelFactory
    from ..adapters.config.runtime_configuration_resolver import RuntimeConfigurationResolver
    alias, _ = _resolve_model_alias_and_id(model_id)
    profile = EmbeddingModelFactory().resolve_profile(alias)
    cache = Path(RuntimeConfigurationResolver().resolve().model_cache_dir) / "hub"
    try:
        from huggingface_hub import snapshot_download
        return Path(snapshot_download(model_id, revision=profile.model_revision, cache_dir=str(cache), local_files_only=True))
    except Exception:
        snapshot = cache / f"models--{model_id.replace('/', '--')}" / "snapshots" / profile.model_revision
        return snapshot if snapshot.is_dir() else None


def _bootstrap_and_index_target(
    target: Path,
    *,
    model_alias: Optional[str] = None,
    device: Optional[str] = None,
    service=None,
    readiness=None,
    cache_root: Optional[Path] = None,
) -> dict:
    """Serialize a complete candidate build and fail closed until publication."""
    import hashlib
    from dataclasses import replace
    from ..core.sync import ProjectLock
    from ..core.sync.readiness import DefaultKnowledgeReadiness
    from ..adapters.ui.composition import persist_readiness
    from ..core.control.retrieval_settings import load_retrieval_settings, save_retrieval_settings

    target = Path(target).resolve()
    cache_root = Path(cache_root) if cache_root else target / DEFAULT_RUNTIME_CACHE
    runtime_overrides = getattr(service, "_runtime_overrides", {}) if service is not None else {}
    model_alias = runtime_overrides.get("embedding_model", model_alias)
    device = runtime_overrides.get("embedding_device", device)
    readiness = readiness or DefaultKnowledgeReadiness()
    with readiness.refresh_lock:
        with readiness.configuration_lock:
            configuration_epoch = readiness.configuration_epoch
            readiness.begin_refresh()
        persist_readiness(cache_root, readiness)
        project_id = "proj-" + hashlib.sha256(str(target).lower().encode()).hexdigest()[:32]
        try:
            with ProjectLock(project_id, root=cache_root / "locks").acquire():
                return _bootstrap_and_index_target_locked(
                    target, model_alias=model_alias, device=device,
                    service=service, readiness=readiness, cache_root=cache_root,
                )
        except Exception as exc:
            readiness.record_failure(str(exc))
            try:
                settings = load_retrieval_settings(target)
                save_retrieval_settings(replace(settings, bootstrap_state="error"), target)
            except Exception:
                pass
            raise
        finally:
            with readiness.configuration_lock:
                configuration_changed = readiness.configuration_epoch != configuration_epoch
                if configuration_changed:
                    readiness.record_failure("Operator configuration changed during indexing; refresh queued")
                readiness.end_refresh()
                persist_readiness(cache_root, readiness)
                if configuration_changed and sys.exc_info()[0] is None:
                    raise RuntimeError("Operator configuration changed during indexing; refresh queued")


def _bootstrap_and_index_target_locked(
    target: Path,
    *,
    model_alias: Optional[str] = None,
    device: Optional[str] = None,
    service=None,
    readiness=None,
    cache_root: Optional[Path] = None,
) -> dict:
    """Execute the full target bootstrap: settings → hydrate/reconcile →
    incremental source discovery → retrieval runtime composition →
    persisted runtime snapshot commit → readiness=True.
    """
    from dataclasses import replace as _dc_replace

    from ..adapters.ui.composition import hydrate_and_reconcile_target
    from ..core.control.retrieval_settings import (
        CACHE_DIR_NAME,
        load_retrieval_settings,
        retrieval_settings_path,
        save_retrieval_settings,
    )
    from ..core.ingest.repository_source_discovery import (
        RepositorySourceDiscovery,
    )
    from ..core.orchestration.repository_indexing import index_repository
    from ..core.sync.version_monitor import read_project_version
    from ..core.retrieval.first_start_wizard import FirstStartWizard
    from ..core.sync.readiness import DefaultKnowledgeReadiness
    from ..core.sync.version_snapshot import (
        ManifestSnapshot,
        PersistedActiveVersion,
        RuntimeSnapshotService,
        SourceSnapshot,
        compute_snapshot_hash,
    )

    target = Path(target).resolve()
    cache_root = Path(cache_root) if cache_root else target / CACHE_DIR_NAME
    settings = load_retrieval_settings(target)
    wizard = FirstStartWizard()
    wizard_schema = wizard.render(target)
    from ..adapters.config.runtime_configuration_resolver import RuntimeConfigurationResolver
    from ..core.control.retrieval_settings import PRODUCTION_ALIASES
    initial_config = RuntimeConfigurationResolver(
        local_settings_path=target / ".project-intelligence-cache" / "settings.json",
        cli_overrides={
            **(getattr(service, "_runtime_overrides", {}) if service is not None else {}),
            **({"embedding_model": model_alias} if model_alias else {}),
            **({"embedding_device": device} if device else {}),
        },
    ).resolve()
    if wizard_schema.get("visible") and not retrieval_settings_path(target).exists():
        settings = wizard.submit({
            "model": initial_config.embedding_model if initial_config.embedding_model in {"gemma", "qwen", "qwen-gguf", "gemma-gguf"} else "gemma",
            "device": initial_config.embedding_device,
            "document_processing_enabled": initial_config.docling_enabled,
            "target_repo": str(target),
        })
    else:
        # Commit effective selection before computing the source-version fingerprint.
        # Otherwise an environment-driven model switch leaves the new snapshot stale.
        settings = _dc_replace(
            settings,
            embedding_model_alias=(initial_config.embedding_model if initial_config.embedding_model in PRODUCTION_ALIASES
                                   else settings.embedding_model_alias),
            device=initial_config.embedding_device,
            document_processing_enabled=initial_config.docling_enabled,
        )

    settings = _dc_replace(settings, bootstrap_state="hydrating")
    save_retrieval_settings(settings, target)

    before = read_project_version(target)
    transient_readiness = DefaultKnowledgeReadiness()
    hydrate_report = hydrate_and_reconcile_target(
        target, cache_root, transient_readiness, lock_held=True, persist_state=False,
    )
    if hydrate_report is None or not transient_readiness.is_ready():
        raise RuntimeError(transient_readiness.snapshot().reason or "Hydration failed")

    settings = _dc_replace(load_retrieval_settings(target), bootstrap_state="indexing")
    save_retrieval_settings(settings, target)

    discovery = RepositorySourceDiscovery()
    inv_path = cache_root / "source-inventory.json"
    prev_inv = discovery.load(inv_path)
    fresh_inv = discovery.discover(target)
    merged_inv, unchanged_entries, modified_entries = discovery.incremental_reuse(
        previous_inventory=prev_inv,
        new_inventory=fresh_inv,
    )
    runtime = index_repository(
        target=target, cache_root=cache_root, inventory=merged_inv,
        previous_inventory=prev_inv, settings=settings,
        cli_overrides={
            **(getattr(service, "_runtime_overrides", {}) if service is not None else {}),
            **({"embedding_model": model_alias} if model_alias else {}),
            **({"embedding_device": device} if device else {}),
        },
    )
    merged_inv = runtime.extra.get("source_inventory", merged_inv)
    after = read_project_version(target)
    if after != before:
        raise RuntimeError("Project version changed during indexing; refresh will retry")

    head = (
        hydrate_report.project_version.gitHead
        if hydrate_report is not None
        else "unversioned"
    )
    fp = before.working_tree_fingerprint
    source_hashes = {e.path: e.content_hash for e in merged_inv.entries}
    source_ids = tuple(e.path for e in merged_inv.entries)
    chunk_ids = tuple(runtime.extra.get("chunk_ids", ()))
    canonical_hashes = []
    graph_node_ids = tuple(runtime.extra.get("graph_node_ids", ()))
    knowledge_root = target / "project-knowledge"
    if knowledge_root.is_dir():
        import hashlib
        for path in sorted(path for path in knowledge_root.rglob("*") if path.is_file() and path.suffix in {".json", ".jsonl"}):
            canonical_hashes.append(f"{path.relative_to(target).as_posix()}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    manifest_snap = ManifestSnapshot(
        snapshot_hash=compute_snapshot_hash(list(chunk_ids) + canonical_hashes),
        chunk_ids=chunk_ids,
        graph_node_ids=graph_node_ids,
    )
    source_snap = SourceSnapshot(
        snapshot_hash=compute_snapshot_hash(
            tuple(f"{k}:{v}" for k, v in sorted(source_hashes.items()))
        ),
        source_ids=source_ids,
        content_hashes=source_hashes,
    )
    gen_id = runtime.extra.get("source_generation") or f"gen-{runtime.embedding_profile_hash[:12]}-{source_snap.snapshot_hash[:12]}"
    active_ver = PersistedActiveVersion(
        project_version=head,
        branch=before.branch,
        head=head,
        working_tree_fingerprint=fp,
        manifest_snapshot_hash=manifest_snap.snapshot_hash,
        source_snapshot_hash=source_snap.snapshot_hash,
        embedding_profile_identity=runtime.embedding_profile_hash,
        active_index_generation=gen_id,
        last_refresh_id=f"refresh-{int(time.time())}",
    )
    RuntimeSnapshotService(cache_root=cache_root).commit(
        active=active_ver,
        manifest=manifest_snap,
        source=source_snap,
    )

    discovery.persist(merged_inv, inv_path)
    if service is not None:
        from ..adapters.ui.composition import publish_runtime
        publish_runtime(service, runtime)
    readiness.record_hydrate(hydrate_report)
    readiness.record_reconcile(
        transient_readiness._reconcile_report,
        current_head=head, working_tree_fingerprint=fp,
    )
    effective = runtime.extra.get("resolved_configuration", {})
    from ..core.control.retrieval_settings import PRODUCTION_ALIASES
    active_alias = effective.get("embedding_model")
    settings = _dc_replace(
        load_retrieval_settings(target), bootstrap_state="ready",
        **({"embedding_model_alias": active_alias} if active_alias in PRODUCTION_ALIASES else {}),
        **({"device": effective["embedding_device"]} if "embedding_device" in effective else {}),
        **({"document_processing_enabled": effective["docling_enabled"]} if "docling_enabled" in effective else {}),
    )
    save_retrieval_settings(settings, target)
    return {
        "target": str(target),
        "active_model": effective.get("embedding_model", settings.embedding_model_alias),
        "model_id": runtime.embedding_model.profile().model_id,
        "device": effective.get("embedding_device", settings.device),
        "embedding_profile_hash": runtime.embedding_profile_hash,
        "dense_backend": runtime.backend_name,
        "active_index_generation": gen_id,
        "discovered_sources": len(merged_inv.entries),
        "unchanged_sources": len(unchanged_entries),
        "modified_or_added_sources": len(modified_entries),
        "removed_sources": len(set(e.path for e in prev_inv.entries) - set(source_ids)) if prev_inv else 0,
        "reused_vectors": getattr(runtime.extra.get("indexing_report"), "reused_count", 0),
        "new_vectors": getattr(runtime.extra.get("indexing_report"), "embedded_count", 0),
        "source_failures": runtime.extra.get("source_failures", []),
        "dense_generation_loaded": runtime.extra.get("dense_generation_loaded", False),
        "ready": True,
        "bootstrap_state": settings.bootstrap_state,
    }


def _cmd_start(args: argparse.Namespace) -> int:
    """Start the control plane immediately and bootstrap in its worker."""
    if getattr(args, "no_serve", False):
        summary = _bootstrap_and_index_target(
            Path(args.target).resolve(),
            model_alias=getattr(args, "model", None),
            device=getattr(args, "device", None),
        )
        print(json.dumps(summary, indent=2))
        return 0
    return _cmd_serve(args)


def _cmd_reindex(args: argparse.Namespace) -> int:
    """Incrementally discover, reconcile, and reindex a target repository."""

    target = Path(getattr(args, "target", Path("."))).resolve()
    summary = _bootstrap_and_index_target(target)
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Run full production capability and target readiness diagnostics."""

    from ..adapters.ui.composition import load_persisted_readiness
    from ..core.control.retrieval_settings import (
        CACHE_DIR_NAME,
        load_retrieval_settings,
        retrieval_settings_path,
    )
    from ..core.orchestration.production_capability_gate import (
        run_production_capability_gate,
    )
    from ..core.sync.readiness import DefaultKnowledgeReadiness
    from ..core.sync.version_snapshot import RuntimeSnapshotService

    target = Path(getattr(args, "target", Path("."))).resolve()
    cache_root = target / CACHE_DIR_NAME
    gate = run_production_capability_gate()
    settings = load_retrieval_settings(target)
    readiness = DefaultKnowledgeReadiness()
    load_persisted_readiness(cache_root, readiness)
    snap = RuntimeSnapshotService(cache_root=cache_root).read_snapshot()
    payload = {
        "ok": gate.passed,
        "target": str(target),
        "settings_configured": retrieval_settings_path(target).is_file(),
        "active_model": settings.embedding_model_alias,
        "model_id": settings.model_id,
        "device": settings.device,
        "document_processing_enabled": settings.document_processing_enabled,
        "bootstrap_state": settings.bootstrap_state,
        "ready": readiness.is_ready(),
        "active_index_generation": (
            snap.active.active_index_generation if snap is not None else None
        ),
        "production_capability_gate": gate.as_dict(),
    }
    print(json.dumps(payload, indent=2))
    return 0 if gate.passed else 1


def _cmd_models_list(args: argparse.Namespace) -> int:
    """Print the production-enabled models from the licence record."""

    path = _resolve_model_licenses_path(getattr(args, "target", None))
    if path is None:
        print(json.dumps({
            "error": "distribution/licenses/model-licenses.json not found",
            "code": "model-licenses-not-found",
            "details": {},
        }), file=sys.stderr)
        return 2
    payload = json.loads(path.read_text(encoding="utf-8"))
    production = [
        m for m in payload.get("models", []) if m.get("production_enabled") or m.get("optional_runtime_enabled")
    ]
    print(json.dumps({
        "source": str(path),
        "count": len(production),
        "models": [
            {
                "model_id": m.get("model_id"),
                "provider": m.get("provider"),
                "revision": m.get("revision"),
                "spdx": m.get("spdx"),
                "profile": m.get("profile"),
                "status": m.get("status"),
            }
            for m in production
        ],
    }, indent=2))
    return 0


def _cmd_models_status(args: argparse.Namespace) -> int:
    """Print the active model profile recorded in the retrieval settings."""

    from ..adapters.retrieval.embedding_model_factory import (
        EmbeddingModelFactory,
        StartupProfile,
    )
    from ..core.control.retrieval_settings import (
        load_retrieval_settings,
        retrieval_settings_path,
    )

    target = Path(getattr(args, "target", Path("."))).resolve()
    settings = load_retrieval_settings(target)
    settings_path = retrieval_settings_path(target)
    payload = {
        "active_alias": settings.embedding_model_alias,
        "model_id": settings.model_id,
        "device": settings.device,
        "document_processing_enabled": settings.document_processing_enabled,
        "bootstrap_state": settings.bootstrap_state,
        "profile": StartupProfile.PRODUCTION,
        "settings_path": str(settings_path),
        "settings_exist": settings_path.exists(),
    }
    try:
        profile = EmbeddingModelFactory(
            startup_profile=StartupProfile.PRODUCTION,
        ).resolve_profile(settings.embedding_model_alias)
        payload["embedding_profile_hash"] = profile.identity()
    except Exception as exc:  # noqa: BLE001 - status must not crash
        payload["embedding_profile_hash"] = None
        payload["profile_error"] = str(exc)
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_models_pull(args: argparse.Namespace) -> int:
    """Download the selected model into the local Hugging Face cache."""

    try:
        alias, model_id = _resolve_model_alias_and_id(args.alias)
    except ValueError as exc:
        print(json.dumps({
            "error": str(exc),
            "code": "unknown-model-alias",
            "details": {"alias": str(args.alias)},
        }), file=sys.stderr)
        return 2
    if alias in {'qwen-gguf', 'gemma-gguf'}:
        from .gguf_setup import prepare
        try:
            path = prepare(Path(os.environ.get('PI_GGUF_CACHE', '/models')), alias)
        except (OSError, ValueError) as exc:
            print(json.dumps({'ok': False, 'error': str(exc)}))
            return 1
        print(json.dumps({'ok': True, 'alias': alias, 'path': str(path)}))
        return 0
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        print(json.dumps({
            "error": "huggingface_hub is not installed; cannot pull models",
            "code": "model-pull-unavailable",
            "details": {"model_id": model_id, "reason": str(exc)},
        }), file=sys.stderr)
        return 1
    try:
        from ..adapters.retrieval.embedding_model_factory import EmbeddingModelFactory
        from ..adapters.config.runtime_configuration_resolver import RuntimeConfigurationResolver
        profile = EmbeddingModelFactory().resolve_profile(alias)
        path = snapshot_download(model_id, revision=profile.model_revision,
                                 cache_dir=str(Path(RuntimeConfigurationResolver().resolve().model_cache_dir) / "hub"))
    except Exception as exc:  # noqa: BLE001 - surface the hub error
        print(json.dumps({
            "error": f"failed to pull {model_id}: {exc}",
            "code": "model-pull-failed",
            "details": {"alias": alias, "model_id": model_id},
        }), file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "alias": alias,
        "model_id": model_id,
        "path": str(path),
        "status": "pulled",
    }, indent=2))
    return 0


def _cmd_models_verify(args: argparse.Namespace) -> int:
    """Verify the model files exist in the local Hugging Face cache."""

    try:
        alias, model_id = _resolve_model_alias_and_id(args.alias)
    except ValueError as exc:
        print(json.dumps({
            "error": str(exc),
            "code": "unknown-model-alias",
            "details": {"alias": str(args.alias)},
        }), file=sys.stderr)
        return 2
    if alias in {'qwen-gguf', 'gemma-gguf'}:
        from .gguf_setup import file_hash
        from ..adapters.retrieval.gguf_artifacts import (FILENAME, SHA256, GEMMA_FILENAME,
            GEMMA_SHA256, GEMMA_PROJECTOR_FILENAME, GEMMA_PROJECTOR_SHA256)
        cache = Path(os.environ.get('PI_GGUF_CACHE', '/models'))
        files = ((FILENAME, SHA256),) if alias == 'qwen-gguf' else (
            (GEMMA_FILENAME, GEMMA_SHA256), (GEMMA_PROJECTOR_FILENAME, GEMMA_PROJECTOR_SHA256))
        path = cache / files[0][0]
        valid = all((cache / name).is_file() and file_hash(cache / name) == digest for name, digest in files)
        print(json.dumps({'ok': valid, 'alias': alias, 'path': str(path)}))
        return 0 if valid else 1
    snapshot = _local_hf_snapshot(model_id)
    if snapshot is None:
        print(json.dumps({
            "ok": False,
            "alias": alias,
            "model_id": model_id,
            "cached": False,
            "files": {name: False for name in _MODEL_VERIFY_FILES},
            "missing": list(_MODEL_VERIFY_FILES),
            "error": "model is not in the local Hugging Face cache; "
                     "run `models pull` first",
            "code": "model-not-cached",
            "details": {"model_id": model_id},
        }, indent=2))
        return 1
    presence = {
        name: (snapshot / name).is_file() for name in _MODEL_VERIFY_FILES
    }
    missing = [name for name, ok in presence.items() if not ok]
    print(json.dumps({
        "ok": not missing,
        "alias": alias,
        "model_id": model_id,
        "cached": True,
        "path": str(snapshot),
        "files": presence,
        "missing": missing,
    }, indent=2))
    return 0 if not missing else 1


def _cmd_models_use(args: argparse.Namespace) -> int:
    """Record the selected model alias in the retrieval settings."""

    from dataclasses import replace as _dc_replace

    from ..core.control.retrieval_settings import (
        load_retrieval_settings,
        retrieval_settings_path,
        save_retrieval_settings,
    )

    try:
        alias, model_id = _resolve_model_alias_and_id(args.alias)
    except ValueError as exc:
        print(json.dumps({
            "error": str(exc),
            "code": "unknown-model-alias",
            "details": {"alias": str(args.alias)},
        }), file=sys.stderr)
        return 2
    target = Path(getattr(args, "target", Path("."))).resolve()
    settings = load_retrieval_settings(target)
    updated = _dc_replace(settings, embedding_model_alias=alias)
    save_retrieval_settings(updated, target)
    print(json.dumps({
        "ok": True,
        "active_alias": updated.embedding_model_alias,
        "model_id": model_id,
        "device": updated.device,
        "settings_path": str(retrieval_settings_path(target)),
        "note": "the new selection activates on the next start/reindex; "
                "canonical Git knowledge is never rewritten",
    }, indent=2))
    return 0


def _cmd_models(args: argparse.Namespace) -> int:
    """Dispatch the ``models`` command group (list/status/pull/verify/use)."""

    subcommand = getattr(args, "models_command", None)
    handlers = {
        "list": _cmd_models_list,
        "status": _cmd_models_status,
        "pull": _cmd_models_pull,
        "verify": _cmd_models_verify,
        "use": _cmd_models_use,
    }
    handler = handlers.get(subcommand)
    if handler is None:
        print(json.dumps({
            "error": f"unknown models subcommand {subcommand!r}",
            "code": "unknown-models-subcommand",
            "details": {"allowed": sorted(handlers)},
        }), file=sys.stderr)
        return 2
    return handler(args)


_DISPATCH.update(
    {
        "start": _cmd_start,
        "models": _cmd_models,
        "reindex": _cmd_reindex,
        "doctor": _cmd_doctor,
    }
)


if __name__ == "__main__":
    raise SystemExit(main())
