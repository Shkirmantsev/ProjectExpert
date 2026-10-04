from __future__ import annotations
import argparse, json
from pathlib import Path
from .core import build_index, validate

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("command", choices=["index","validate"]); p.add_argument("--root", default=".")
    a=p.parse_args(); root=Path(a.root).resolve()
    result=build_index(root) if a.command=="index" else validate(root)
    print(json.dumps(result, indent=2))
    if a.command=="validate" and not result["ok"]: raise SystemExit(1)
if __name__ == "__main__": main()
