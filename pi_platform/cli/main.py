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

    sub.add_parser("embedding-status",
                   help="print the active §25 EmbeddingModelPort status")
    sub.add_parser("retrieval-status",
                   help="print the Phase 4 retrieval pipeline status")
    sub.add_parser("reranker-status",
                   help="print the active §30 RerankerPort status")

    sub.add_parser("orchestrator-status",
                   help="print the Phase 5 §34 query orchestrator status")
    sub.add_parser("llm-status",
                   help="print the active §35 LocalLLMPort status")
    sub.add_parser("capabilities",
                   help="print the §47 capability discovery descriptor")
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
        reconcile = ReconcileService(filesystem=fs).reconcile_branch_switch(
            target,
            previous_head=report.project_version.gitHead,
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
        candidate = target / DEFAULT_DEPENDENCY_INVENTORY_PATH
        if candidate.is_file():
            inventory_path = candidate
        else:
            platform_home = Path(
                os.environ.get("PI_PLATFORM_HOME", "/opt/project-intelligence")
            )
            fallback = platform_home / DEFAULT_DEPENDENCY_INVENTORY_PATH
            inventory_path = fallback if fallback.is_file() else candidate
    deps = DependencyInventory(inventory_path).load()
    discovered = target / "tmp/local/pi-platform-ingest/discovered-dependencies.json"
    if discovered.exists():
        deps.extend(DependencyInventory(discovered).load())
    passed, findings = LicenseGate(LicensePolicy()).run(deps)
    payload = {
        "inventory": str(inventory_path),
        "passed": passed,
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
    from ..adapters.ui import build_ui_service, hydrate_and_reconcile_target

    target = Path(getattr(args, "target", Path.cwd())).resolve()
    cache_root = _resolve_cache_root(args)
    _service, readiness = build_ui_service(
        repo_root=target, cache_root=cache_root,
    )
    snapshot = readiness.snapshot()
    ready = bool(snapshot.consistent) and not bool(snapshot.in_progress)
    if (
        not ready
        and os.environ.get("PI_AUTO_HYDRATE") == "1"
        and ((target / ".git").exists() or (target / "project-knowledge").is_dir())
    ):
        hydrate_and_reconcile_target(target, cache_root, readiness)
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
    auto_hydrate = os.environ.get("PI_AUTO_HYDRATE", "1") != "0"
    service, readiness = build_ui_service(
        repo_root=target,
        cache_root=cache_root,
        hydrate_on_start=auto_hydrate,
    )
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
    print(json.dumps({
        "status": "listening",
        "url": f"http://{args.host}:{args.port}",
        "target": str(target),
        "ready": readiness.is_ready(),
        "mcp_endpoint": f"http://{args.host}:{args.port}/mcp",
    }), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - operator interrupt
        pass
    finally:
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
        hydrate_on_start=auto_hydrate,
    )
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
        try:
            server.serve_forever()
        except KeyboardInterrupt:  # pragma: no cover
            pass
        finally:
            server.stop()
        return 0
    return mcp_server.serve_stdio_fallback(skill_plane=skill_plane)


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
        payload = _tier3.run_eval(
            golden_path=args.golden,
            corpus_root=args.corpus_root,
            out_path=out_path,
            baseline_path=baseline_path,
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
    """Report the active §25 EmbeddingModelPort status."""

    from ..adapters.retrieval.hashing_embedding_model import (
        HashingEmbeddingAdapter,
    )
    from ..adapters.retrieval.multilingual_st_embedding_model import (
        ADAPTER_NAME as _MULTILINGUAL_NAME,
        DEFAULT_LICENSE_ID,
        EXPECTED_DIMENSION,
        MultilingualSentenceTransformerEmbeddingModel,
    )

    hashing = HashingEmbeddingAdapter()
    backend_name = "hashing"
    model_version = hashing.model_version()
    license_id = hashing.license_id()
    dimension = hashing.dimension()
    try:
        MultilingualSentenceTransformerEmbeddingModel()
        multilingual_available = True
    except Exception:
        multilingual_available = False
    payload = {
        "active_backend": backend_name,
        "active_model_version": model_version,
        "active_license_id": license_id,
        "active_dimension": dimension,
        "multilingual_available": multilingual_available,
        "multilingual_adapter_name": _MULTILINGUAL_NAME,
        "multilingual_default_model_id": "paraphrase-multilingual-MiniLM-L12-v2",
        "multilingual_default_license_id": DEFAULT_LICENSE_ID,
        "multilingual_expected_dimension": EXPECTED_DIMENSION,
        "stats": dict(hashing.stats()),
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
    """Report the Phase 4 retrieval pipeline status."""

    from ..adapters.retrieval.context_assembler_adapter import (
        ContextAssemblerAdapter,
    )
    from ..adapters.retrieval.hybrid_retrieval import HybridRetrievalAdapter
    from ..adapters.retrieval.identifier_query_detector import (
        IdentifierQueryDetector,
    )
    from ..adapters.retrieval.metadata_filter_adapter import (
        MetadataFilterAdapter,
    )
    from ..adapters.retrieval.bm25_light_reranker import Bm25LightRerankerAdapter
    from ..adapters.runtime.graph_expansion import (
        DEFAULT_BUDGET as _PRODUCTION_GRAPH_BUDGET,
        DEFAULT_EDGE_TYPES as _PRODUCTION_GRAPH_EDGE_TYPES,
        ProductionGraphExpansion,
    )
    from ..core.retrieval.multi_stage_retrieval import (
        DEFAULT_BUDGETS as _DEFAULT_STAGE_BUDGETS,
    )

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
    """Print the §47 capability discovery descriptor."""

    from ..adapters.orchestration.capability_discovery import (
        DefaultCapabilityDiscoveryAdapter,
    )
    from ..adapters.orchestration.stub_local_llm import (
        StubLocalLLMAdapter,
    )

    discovery = DefaultCapabilityDiscoveryAdapter(
        local_llm=StubLocalLLMAdapter(),
    )
    payload = discovery.describe().as_dict()
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


if __name__ == "__main__":
    raise SystemExit(main())