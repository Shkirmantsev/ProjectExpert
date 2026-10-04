#!/usr/bin/env python3
"""Record and evaluate lesson candidates without automatic promotion."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

from common import ROOT
from file_lock import file_lock


STORE = ROOT / "tmp" / "local" / "lesson-candidates"
ID_PATTERN = re.compile(r"^LESSON-[0-9A-F]{16}$")
FORBIDDEN = re.compile(
    r"(?i)(?:grant|allow|expand|disable|bypass|remove|rewrite|change).{0,30}"
    r"(?:all tool permissions|security policy|root instructions|credentials|"
    r"project boundary|approval requirement)"
)


class LessonError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


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


def store_lock():
    return file_lock(STORE / ".lock")


def candidate_path(identifier: str) -> Path:
    if not ID_PATTERN.fullmatch(identifier):
        raise LessonError("invalid_lesson_id", "lesson id is invalid")
    return STORE / f"{identifier}.json"


def read(identifier: str) -> dict:
    path = candidate_path(identifier)
    if not path.is_file():
        raise LessonError("lesson_not_found", f"lesson candidate does not exist: {identifier}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LessonError("invalid_candidate", str(exc)) from exc


def propose(args: argparse.Namespace) -> dict:
    if not 0.0 <= args.confidence <= 1.0:
        raise LessonError("invalid_confidence", "confidence must be between 0 and 1")
    if FORBIDDEN.search(" ".join(args.prevention)):
        raise LessonError(
            "forbidden_self_modification",
            "lesson candidates may not expand authority or weaken safety policy",
        )
    core = {
        "schema_version": "1.0",
        "failure_mode": args.failure_mode,
        "root_cause": args.root_cause,
        "prevention": sorted(set(args.prevention)),
        "evidence": sorted(set(args.evidence)),
        "scope": args.scope,
        "confidence": args.confidence,
    }
    encoded = json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    identifier = "LESSON-" + hashlib.sha256(encoded).hexdigest()[:16].upper()
    path = candidate_path(identifier)
    with store_lock():
        if path.exists():
            return read(identifier)
        timestamp = now()
        payload = {
            **core,
            "id": identifier,
            "status": "candidate",
            "automatic_promotion": False,
            "promotion": "not-eligible-until-validated",
            "validation": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        atomic_write(path, payload)
    return payload


def validate(args: argparse.Namespace) -> dict:
    with store_lock():
        payload = read(args.id)
        payload["validation"] = {
            "eval_ref": args.eval_ref,
            "reviewer": args.reviewer,
            "result": args.result,
        }
        payload["status"] = "validated" if args.result == "passed" else "candidate"
        payload["promotion"] = (
            "manual-review-required" if args.result == "passed" else "not-eligible"
        )
        payload["updated_at"] = now()
        atomic_write(candidate_path(args.id), payload)
    return payload


def list_candidates() -> dict:
    items = []
    if STORE.exists():
        for path in sorted(STORE.glob("LESSON-*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                items.append(
                    {
                        "id": payload["id"],
                        "status": payload["status"],
                        "scope": payload["scope"],
                        "failure_mode": payload["failure_mode"],
                    }
                )
            except (KeyError, OSError, json.JSONDecodeError):
                items.append({"id": path.stem, "status": "invalid"})
    return {"schema_version": "1.0", "candidates": items}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    create = commands.add_parser("propose")
    create.add_argument("--failure-mode", required=True)
    create.add_argument("--root-cause", required=True)
    create.add_argument("--prevention", action="append", required=True)
    create.add_argument("--evidence", action="append", required=True)
    create.add_argument("--scope", choices=("project", "reusable"), required=True)
    create.add_argument("--confidence", type=float, required=True)

    review = commands.add_parser("validate")
    review.add_argument("--id", required=True)
    review.add_argument("--eval-ref", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--result", choices=("passed", "failed"), required=True)

    commands.add_parser("list")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "propose":
            payload = propose(args)
        elif args.command == "validate":
            payload = validate(args)
        else:
            payload = list_candidates()
        status = 0
    except LessonError as exc:
        payload = {"error": exc.code, "message": str(exc)}
        status = 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
