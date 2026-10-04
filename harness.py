#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MCP_ROOT = ROOT / "tools/mcp/project-context-mcp"
sys.path.insert(0, str(MCP_ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    resolved = shutil.which(cmd[0])
    if resolved:
        cmd = [resolved, *cmd[1:]]
    return subprocess.run(cmd, cwd=ROOT, check=check)


def ensure_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        shutil.copy2(ROOT / ".env.example", env)
        print("Created .env from .env.example")
    run([sys.executable, "scripts/bootstrap_env.py"])


def cmd_mcp_install() -> None:
    target = ROOT / "tmp/local/project-context/venv"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        print(f"Creating local MCP virtual environment: {target.relative_to(ROOT)}")
        venv.EnvBuilder(with_pip=True).create(target)
    py = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "--retries", "1", "--timeout", "15", "-e", str(MCP_ROOT)])


def cmd_index() -> None:
    from project_context_mcp.core import build_index
    print(json.dumps(build_index(ROOT), indent=2))


def cmd_wiki_validate() -> None:
    from project_context_mcp.core import validate
    result = validate(ROOT)
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


def cmd_openspec_check() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from openspec_layout import validate_layout
    layout_errors = validate_layout(ROOT / "openspec")
    if layout_errors:
        print({"openspecLayoutErrors": layout_errors})
        raise SystemExit(1)
    import re
    path = ROOT / "openspec/schemas/production-sdd/schema.yaml"
    text = path.read_text(encoding="utf-8")
    required = ["proposal", "specs", "design", "context-impact", "tasks"]
    missing = [x for x in required if not re.search(rf"(?m)^\s*- id: {re.escape(x)}\s*$", text)]
    template_dir = path.parent / "templates"
    missing_templates = [f for f in ["proposal.md","spec.md","design.md","context-impact.md","tasks.md"] if not (template_dir/f).exists()]
    if missing or missing_templates:
        print({"missingArtifacts": missing, "missingTemplates": missing_templates})
        raise SystemExit(1)
    print("OpenSpec project schema structure: PASS")
    if shutil.which("openspec"):
        run(["openspec", "schema", "validate", "production-sdd"])
        run(["openspec", "validate", "--all", "--strict"])
    else:
        raise SystemExit(
            "OpenSpec CLI validation: FAIL (install OpenSpec 1.12.0 or newer)"
        )


def configure_openspec() -> None:
    if not shutil.which("openspec"):
        print("OpenSpec telemetry: NOT RUN (openspec executable not installed)")
        return
    run(["openspec", "config", "set", "telemetry.enabled", "false"])


def cmd_client_config() -> None:
    run([sys.executable, "scripts/configure_clients.py"])


def cmd_test() -> None:
    # Run repository test modules in isolated processes. Several tests intentionally
    # mutate generated local state, so module isolation avoids order-dependent state.
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        module = f"tests.{path.stem}"
        run([sys.executable, "-m", "unittest", module, "-v"])
    env = os.environ.copy(); env["PYTHONPATH"] = str(MCP_ROOT)
    print("+ project-context core tests")
    installed_python = ROOT / "tmp/local/project-context/venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = str(installed_python) if installed_python.exists() else sys.executable
    subprocess.run([python, "-m", "unittest", "discover", "-s", str(MCP_ROOT / "tests"), "-p", "test_*.py", "-v"], cwd=ROOT, check=True, env=env)


def cmd_check(*, delegated: bool = False) -> None:
    if not delegated:
        run([sys.executable, "scripts/check_config.py"])
    else:
        print("Config/secret validation: SKIPPED (delegated secret-free profile)")
    run([sys.executable, "scripts/session_state.py", "verify"])
    cmd_wiki_validate()
    cmd_openspec_check()
    cmd_test()
    run([sys.executable, "scripts/artifact_manifest.py", "verify"])
    print("Harness core checks: PASS")


def cmd_init(args) -> None:
    ensure_env()
    configure_openspec()
    cmd_index()
    run([sys.executable, "scripts/sync_skills.py", "local"])
    if args.install_mcp:
        cmd_mcp_install()
    cmd_client_config()
    print("Initialization complete. Edit .env only if you want optional integrations, then run: python harness.py check")


def cmd_help() -> None:
    import re
    print("Harness commands (GNU Make optional; Python works on Linux and Windows):")
    for line in (ROOT / "Makefile").read_text(encoding="utf-8").splitlines():
        match = re.match(r"([a-zA-Z0-9_-]+):.*?## (.+)", line)
        if match:
            print(f"  make {match[1]:28} {match[2]}")
    print("Core equivalent: python harness.py <command>; see --help for aliases.")


def cmd_wiki_init() -> None:
    cmd_wiki_validate()
    cmd_index()
    print("Wiki ready; existing Markdown preserved.")


def cmd_mcp_stdio() -> None:
    from project_mcp import installed_python
    from common import parse_env, project_root, validate_project_root
    python = installed_python()
    if not python.is_file():
        raise SystemExit("MCP is not installed; run python harness.py mcp-install")
    root = project_root(parse_env())
    validate_project_root(root)
    # Stdout belongs exclusively to MCP; never use the logging run() wrapper here.
    raise SystemExit(subprocess.run([str(python), "-m", "project_context_mcp.server",
                                    "--root", str(root)], cwd=ROOT).returncode)



def cmd_clean() -> None:
    from project_mcp import Lifecycle

    def remove_runtime() -> None:
        for p in [ROOT / ".generated", ROOT / ".mcp.json", ROOT / "opencode.json", ROOT / ".codex/config.toml", ROOT / ".claude/settings.local.json"]:
            if p.is_dir(): shutil.rmtree(p, ignore_errors=True)
            elif p.exists(): p.unlink()
        for pattern in [ROOT / ".claude/agents", ROOT / ".opencode/agents"]:
            if pattern.exists():
                for p in pattern.glob("generated-*.md"): p.unlink()
        tool_dir = ROOT / '.opencode/tools'
        if tool_dir.exists():
            for p in list(tool_dir.glob('generated-hermes.*')) + [tool_dir / 'hermes.js']:
                if p.exists(): p.unlink()
        shutil.rmtree(ROOT / "tmp/local/project-context", ignore_errors=True)

    # The same lock spans readiness checks and runtime deletion: start cannot race clean.
    if Lifecycle().clean(runtime_cleanup=remove_runtime):
        raise SystemExit("Stop the background MCP with stop-mcp before cleaning its runtime")
    print("Generated client/runtime/index state removed; source and .env preserved.")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cross-platform management CLI for harness-layout")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", aliases=["harness-init"], help="create .env, index Wiki and generate clients")
    init.add_argument("--install-mcp", action="store_true", help="also install local MCP runtime")
    sub.add_parser("init-mcp", aliases=["harness-init-mcp"], help="initialize core and install MCP")
    descriptions = {
        "help": "list Make workflows and portable equivalents",
        "check": "validate configuration, Wiki, OpenSpec and core tests",
        "check-delegated": "secret-free repository gate for CI",
        "test": "run core tests",
        "index": "rebuild disposable Markdown Wiki SQLite index",
        "wiki-init": "validate existing Wiki and initialize its index",
        "wiki-validate": "validate Wiki stable IDs and links",
        "openspec-check": "validate current state, naming and OpenSpec artifacts",
        "mcp-install": "install project-context MCP into local virtualenv",
        "client-config": "generate Claude/OpenCode/Codex configs",
        "manifest-generate": "regenerate source artifact manifest",
        "manifest-check": "verify source artifact manifest",
        "clean": "remove generated state after background MCP is stopped",
        "run-mcp": "start connectable background MCP on localhost",
        "stop-mcp": "stop only the harness-owned background MCP",
        "mcp-status": "show background MCP readiness",
        "mcp-logs": "show recent background MCP logs",
        "mcp-clean": "remove stopped background MCP state and logs",
        "mcp-stdio": "run MCP in foreground stdio mode for a client",
    }
    extra_aliases = {"index": ["wiki-index", "harness-wiki-index"],
                     "wiki-init": ["init-wiki"], "run-mcp": ["mcp-run"], "stop-mcp": ["mcp-stop"]}
    for command, description in descriptions.items():
        aliases = extra_aliases.get(command, [])
        if command not in {"help", "index", "wiki-init", "run-mcp", "stop-mcp", "mcp-status", "mcp-logs", "mcp-clean", "mcp-stdio"}:
            aliases = [*aliases, "harness-" + command]
        child = sub.add_parser(command, aliases=aliases, help=description)
        child.set_defaults(command=command)
    init.set_defaults(command="init")
    return p


def main() -> None:
    args = parser().parse_args()
    if args.command in {"init-mcp", "harness-init-mcp"}:
        args.install_mcp = True
        cmd_init(args)
        return
    actions = {"run-mcp": "start", "stop-mcp": "stop", "mcp-status": "status",
               "mcp-logs": "logs", "mcp-clean": "clean"}
    if args.command in actions:
        result = subprocess.run([sys.executable, str(ROOT / "scripts/project_mcp.py"), actions[args.command]], cwd=ROOT)
        raise SystemExit(result.returncode)
    {
        "init": lambda: cmd_init(args), "help": cmd_help, "check": cmd_check,
        "test": cmd_test, "index": cmd_index, "wiki-init": cmd_wiki_init,
        "check-delegated": lambda: cmd_check(delegated=True),
        "wiki-validate": cmd_wiki_validate, "openspec-check": cmd_openspec_check,
        "mcp-install": cmd_mcp_install, "mcp-stdio": cmd_mcp_stdio,
        "client-config": cmd_client_config, "clean": cmd_clean,
        "manifest-generate": lambda: run([sys.executable, "scripts/artifact_manifest.py", "generate"]),
        "manifest-check": lambda: run([sys.executable, "scripts/artifact_manifest.py", "verify"]),
    }[args.command]()


if __name__ == "__main__":
    main()
