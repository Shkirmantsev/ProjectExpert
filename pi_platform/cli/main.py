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
import sys
from pathlib import Path
from typing import Iterable, Optional

from ..adapters.fs import LocalFilesystemAdapter
from ..core.canonical import validate_wiki_bundle
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

    sub.add_parser("health", help="lightweight liveness check")
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
    target = args.target.resolve()
    cache_root = _resolve_cache_root(args)
    with ProjectLock(_project_id(target)).acquire():
        service = HydrateService(filesystem=LocalFilesystemAdapter(target, cache_root=cache_root))
        report = service.restore_runtime(target, cache_root=cache_root)
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
    inventory_path = (args.inventory
                      if args.inventory else
                      target / DEFAULT_DEPENDENCY_INVENTORY_PATH)
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


def _cmd_health(_: argparse.Namespace) -> int:
    print(json.dumps({"status": "ok"}))
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
    return target.resolve().as_posix().replace("/", "-").lstrip("-") or "default"


_DISPATCH = {
    "init-project": _cmd_init_project,
    "hydrate": _cmd_hydrate,
    "materialise": _cmd_materialise,
    "license-gate": _cmd_license_gate,
    "okf-validate": _cmd_okf_validate,
    "version-identity": _cmd_version_identity,
    "wal-recover": _cmd_wal_recover,
    "health": _cmd_health,
    "ingest-sources": _cmd_ingest_sources,
    "runtime-status": _cmd_runtime_status,
    "graph-rebuild": _cmd_graph_rebuild,
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


if __name__ == "__main__":
    raise SystemExit(main())