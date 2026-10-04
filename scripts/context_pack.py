#!/usr/bin/env python3
"""Build a bounded, content-addressed ContextPack without copying source bodies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from common import ROOT


OUTPUT_ROOT = ROOT / "tmp" / "local" / "context-packs"
SECRET_PATTERN = re.compile(
    r"(?i)(?:password|passwd|api[_ -]?key|access[_ -]?token|authorization)\s*[:=]\s*\S+|-----BEGIN [A-Z ]+PRIVATE KEY-----|bearer\s+[A-Za-z0-9._~+/-]{12,}"
)


class PackError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def ensure_safe_text(values: list[str]) -> None:
    for value in values:
        if SECRET_PATTERN.search(value):
            raise PackError("possible_secret", "inline context resembles a credential")


def file_evidence(raw: str) -> dict:
    path_text, separator, reason = raw.partition("::")
    if separator:
        reason = reason.strip()
        if not reason:
            raise PackError("invalid_file_reason", "file reason may not be empty")
        ensure_safe_text([reason])
    else:
        reason = "selected task evidence"
    candidate = Path(path_text).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise PackError("path_outside_project", f"file is outside project: {raw}") from exc
    if not resolved.is_file():
        raise PackError("file_not_found", f"file does not exist: {relative}")
    content = resolved.read_bytes()
    return {
        "path": relative.as_posix(),
        "reason": reason,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def unique(values: list[str] | None) -> list[str]:
    return sorted(set(values or []))


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            # Directory fsync is a POSIX-only durability step; Windows rejects
            # opening a directory handle this way.
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def build(args: argparse.Namespace) -> dict:
    inline = [args.goal] + (args.acceptance or []) + (args.constraint or [])
    inline += (args.symbol or []) + (args.command or []) + (args.reference or [])
    ensure_safe_text(inline)
    if args.target_tokens < 1 or args.hard_max_tokens < args.target_tokens:
        raise PackError(
            "invalid_budget", "hard_max_tokens must be at least target_tokens and both positive"
        )
    files = sorted(
        {item["path"]: item for item in (file_evidence(raw) for raw in args.file or [])}.values(),
        key=lambda item: item["path"],
    )
    if len(files) > 24:
        raise PackError("too_many_files", "a ContextPack may contain at most 24 files")

    payload = {
        "schema_version": "1.0",
        "goal": args.goal,
        "acceptance": unique(args.acceptance),
        "constraints": unique(args.constraint),
        "files": files,
        "symbols": unique(args.symbol),
        "verification_commands": unique(args.command),
        "references": unique(args.reference),
        "repository_profile_hash": args.repository_profile_hash or "",
        "budget": {
            "target_tokens": args.target_tokens,
            "hard_max_tokens": args.hard_max_tokens,
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["id"] = "CP-" + hashlib.sha256(canonical).hexdigest()[:16].upper()
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--goal", required=True)
    result.add_argument("--acceptance", action="append")
    result.add_argument("--constraint", action="append")
    result.add_argument("--file", action="append")
    result.add_argument("--symbol", action="append")
    result.add_argument("--command", action="append")
    result.add_argument("--reference", action="append")
    result.add_argument("--repository-profile-hash")
    result.add_argument("--target-tokens", type=int, default=12000)
    result.add_argument("--hard-max-tokens", type=int, default=24000)
    result.add_argument("--write", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        payload = build(args)
        if args.write:
            atomic_write(OUTPUT_ROOT / f"{payload['id']}.json", payload)
        status = 0
    except PackError as exc:
        payload = {"error": exc.code, "message": str(exc)}
        status = 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
