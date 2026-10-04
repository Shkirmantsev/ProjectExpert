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

    sub.add_parser("health", help="lightweight liveness check")
    sub.add_parser("--help", help="show this help message and exit")
    return parser


def _resolve_cache_root(args: argparse.Namespace) -> Path:
    """Resolve ``--cache-root`` relative to ``--target`` when it is not absolute."""

    cache_root = Path(getattr(args, "cache_root", DEFAULT_RUNTIME_CACHE))
    if not cache_root.is_absolute():
        cache_root = (Path(args.target).resolve() / cache_root).resolve()
    return cache_root


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


def _cmd_health(_: argparse.Namespace) -> int:
    print(json.dumps({"status": "ok"}))
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