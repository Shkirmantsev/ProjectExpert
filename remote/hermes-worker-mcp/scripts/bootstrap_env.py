#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]
example = ROOT / ".env.example"
env = ROOT / ".env"
if not env.exists():
    env.write_text(example.read_text(), encoding="utf-8")
text = env.read_text(encoding="utf-8")
if "HERMES_SIDECAR_TOKEN=AUTO_GENERATE" in text:
    text = text.replace("HERMES_SIDECAR_TOKEN=AUTO_GENERATE", "HERMES_SIDECAR_TOKEN=" + secrets.token_urlsafe(48))
env.write_text(text, encoding="utf-8")
env.chmod(0o600)
print(env)
