#!/usr/bin/env python3
from __future__ import annotations
import argparse, shutil
from pathlib import Path
from common import parse_env, project_root, validate_project_root
p=argparse.ArgumentParser(description="Copy an external document/image into the active project inbox so native Hermes can access it through SSH.")
p.add_argument("file")
a=p.parse_args(); src=Path(a.file).expanduser().resolve()
if not src.is_file(): raise SystemExit(f"Not a file: {src}")
env=parse_env(); root=project_root(env); validate_project_root(root)
inbox=root/".harness/inbox"; inbox.mkdir(parents=True,exist_ok=True)
dst=inbox/src.name; shutil.copy2(src,dst)
print(dst.relative_to(root))
