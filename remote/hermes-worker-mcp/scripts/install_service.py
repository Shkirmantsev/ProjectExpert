#!/usr/bin/env python3
from __future__ import annotations
import os, pwd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = ROOT / ".env"
if not env.exists():
    raise SystemExit("Run scripts/bootstrap_env.py and fill .env first")

# Use the actual passwd-database home for the current Linux UID instead of
# trusting $HOME. Hermes profile shells can override HOME to a profile-local
# directory, which would otherwise install the unit where systemd --user cannot
# see it.
runtime_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
unit_dir = runtime_home / ".config/systemd/user"
unit_dir.mkdir(parents=True, exist_ok=True)
unit = unit_dir / "hermes-worker-mcp.service"
unit.write_text(f"""[Unit]
Description=Claude Code MCP sidecar for native Hermes Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={ROOT}
EnvironmentFile={env}
ExecStart={ROOT}/.venv/bin/hermes-worker-mcp
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={ROOT}

[Install]
WantedBy=default.target
""", encoding="utf-8")
print(unit)
