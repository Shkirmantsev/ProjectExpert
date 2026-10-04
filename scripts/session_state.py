#!/usr/bin/env python3
"""Crash-safe, evidence-oriented session checkpoints for the harness."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

from common import ROOT
from file_lock import file_lock


SCHEMA_VERSION = "1.0"
RUNTIME_CONFIG = ROOT / ".harness" / "runtime.json"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
CURRENT_ID_PATTERN = re.compile(r"<!--\s*harness-session-id:\s*([^\s]+)\s*-->")
STATUSES = {"planning", "executing", "verifying", "reviewing", "blocked", "complete"}
TRANSITIONS = {
    "planning": {"executing", "verifying", "reviewing", "blocked"},
    "executing": {"verifying", "blocked"},
    "verifying": {"executing", "reviewing", "blocked"},
    "reviewing": {"executing", "complete", "blocked"},
    "blocked": {"planning", "executing", "verifying", "reviewing"},
    "complete": set(),
}


class StateError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def configured_project_path(variable: str, default: Path) -> Path:
    raw = os.environ.get(variable)
    candidate = Path(raw).expanduser() if raw else default
    resolved = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise StateError(
            "path_outside_project", f"{variable} must stay inside the project"
        ) from exc
    return resolved


STATE_HOME = configured_project_path(
    "HARNESS_SESSION_STATE_HOME", ROOT / ".ai" / "state"
)
STATE_ROOT = STATE_HOME / "handoffs"
CURRENT_STATE = STATE_HOME / "CURRENT.md"
LEGACY_STATE_ROOT = configured_project_path(
    "HARNESS_SESSION_LEGACY_ROOT", ROOT / "tmp" / "local" / "sessions"
)
LOCK_ROOT = ROOT / "tmp" / "local" / "session-locks"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def default_max_steps() -> int:
    try:
        value = int(
            json.loads(RUNTIME_CONFIG.read_text(encoding="utf-8"))["goal_loop"][
                "max_steps"
            ]
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StateError("invalid_runtime_config", str(exc)) from exc
    if value < 1:
        raise StateError("invalid_runtime_config", "goal_loop.max_steps must be positive")
    return value


def runtime_limits() -> dict[str, int]:
    try:
        loop = json.loads(RUNTIME_CONFIG.read_text(encoding="utf-8"))["goal_loop"]
        limits = {
            "max_repeated_failure": int(loop["max_repeated_failure"]),
            "max_no_progress_windows": int(loop["max_no_progress_windows"]),
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StateError("invalid_runtime_config", str(exc)) from exc
    if any(value < 1 for value in limits.values()):
        raise StateError("invalid_runtime_config", "runtime limits must be positive")
    return limits


def progress_fingerprint(payload: dict) -> str:
    evidence = {
        "progress": payload["progress"],
        "decisions": payload["decisions"],
        "verification": payload["verification"],
        "working_set": payload["working_set"],
    }
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def session_id(value: str | None) -> str:
    if value is None:
        value = f"SESSION-{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"
    if not ID_PATTERN.fullmatch(value):
        raise StateError("invalid_session_id", "session id must be 3-80 safe characters")
    return value


def state_path(identifier: str) -> Path:
    return STATE_ROOT / f"{session_id(identifier)}.json"


def legacy_state_path(identifier: str) -> Path:
    return LEGACY_STATE_ROOT / session_id(identifier) / "state.json"


def locked():
    return file_lock(LOCK_ROOT / "state.lock")


def read(identifier: str) -> dict:
    path = state_path(identifier)
    if not path.exists():
        path = legacy_state_path(identifier)
    if not path.exists():
        raise StateError("session_not_found", f"checkpoint does not exist: {identifier}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError("invalid_checkpoint", str(exc)) from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise StateError("unsupported_schema", "checkpoint schema is not supported")
    data.setdefault("context", [])
    data.setdefault("working_set", [])
    data["task"].setdefault("openspec_change", "")
    return data


def atomic_write_bytes(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(encoded)
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


def atomic_write_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(path, encoded)


def markdown_items(items: list[str], *, code: bool = False) -> list[str]:
    if not items:
        return ["- none"]
    rendered = []
    for item in items:
        value = str(item).replace("\r", "").replace("\n", " ").strip()
        rendered.append(f"- `{value}`" if code else f"- {value}")
    return rendered


def render_current(payload: dict) -> str:
    identifier = payload["session"]["id"]
    task = payload["task"]
    progress = payload["progress"]
    verification = payload["verification"]
    working_files = [item["path"] for item in payload.get("working_set", [])]
    change = task.get("openspec_change") or "none"
    next_action = payload["resume"].get("next_action") or "none"
    lines = [
        "<!-- Generated by scripts/session_state.py; do not edit manually. -->",
        f"<!-- harness-session-id: {identifier} -->",
        "# Current task state",
        "",
        f"Structured source: [handoffs/{identifier}.json](handoffs/{identifier}.json)",
        "",
        f"Task: `{identifier}`",
        f"Status: `{task['status']}`",
        f"Updated: `{payload['session']['updated_at']}`",
        f"Active OpenSpec change: `{change}`" if change != "none" else "Active OpenSpec change: none",
        "",
        "## Objective",
        "",
        task["goal"],
        "",
        "## Acceptance criteria",
        "",
        *markdown_items(task.get("acceptance", [])),
        "",
        "## Completed",
        "",
        *markdown_items(progress.get("done", [])),
        "",
        "## Remaining",
        "",
        *markdown_items(progress.get("todo", [])),
        "",
        "## Blocked",
        "",
        *markdown_items(progress.get("blocked", [])),
        "",
        "## Decisions",
        "",
        *markdown_items(payload.get("decisions", [])),
        "",
        "## Relevant context",
        "",
        *markdown_items(payload.get("context", []), code=True),
        "",
        "## Working set",
        "",
        *markdown_items(working_files, code=True),
        "",
        "## Verification passed",
        "",
        *markdown_items(verification.get("passed", [])),
        "",
        "## Verification pending",
        "",
        *markdown_items(verification.get("pending", [])),
        "",
        "## Next action",
        "",
        next_action,
        "",
        "## Prerequisites",
        "",
        *markdown_items(payload["resume"].get("prerequisites", [])),
        "",
    ]
    return "\n".join(lines)


def write_state(payload: dict) -> None:
    atomic_write_json(state_path(payload["session"]["id"]), payload)
    atomic_write_bytes(CURRENT_STATE, render_current(payload).encode("utf-8"))


def current_session_id() -> str | None:
    if not CURRENT_STATE.is_file():
        return None
    try:
        text = CURRENT_STATE.read_text(encoding="utf-8")
    except OSError as exc:
        raise StateError("invalid_current_state", str(exc)) from exc
    match = CURRENT_ID_PATTERN.search(text)
    return session_id(match.group(1)) if match else None


def selected_session_id(value: str | None) -> str:
    if value is not None:
        return session_id(value)
    identifier = current_session_id()
    if identifier is None:
        raise StateError(
            "current_session_not_found",
            "no active handoff; start a task or pass --id",
        )
    return identifier


def project_file(raw: str) -> tuple[Path, str]:
    candidate = Path(raw).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise StateError("path_outside_project", f"working file is outside project: {raw}") from exc
    if not resolved.is_file():
        raise StateError("file_not_found", f"working file does not exist: {relative}")
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return relative, digest


def start(args: argparse.Namespace) -> dict:
    identifier = session_id(args.id)
    steps_max = args.steps_max if args.steps_max is not None else default_max_steps()
    if steps_max < 1:
        raise StateError("invalid_budget", "steps_max must be positive")
    with locked():
        path = state_path(identifier)
        if (path.exists() or legacy_state_path(identifier).exists()) and not args.replace:
            raise StateError("session_exists", f"checkpoint already exists: {identifier}")
        active_identifier = current_session_id()
        if active_identifier and active_identifier != identifier and not args.replace_current:
            active = read(active_identifier)
            if active["task"]["status"] != "complete":
                raise StateError(
                    "active_session_exists",
                    f"complete {active_identifier} or pass --replace-current",
                )
        timestamp = now()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "session": {
                "id": identifier,
                "project": ROOT.name,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            "task": {
                "goal": args.goal,
                "acceptance": args.acceptance or [],
                "status": "planning",
                "openspec_change": args.openspec_change or "",
            },
            "progress": {"done": [], "todo": args.todo or [], "blocked": []},
            "context": args.context or [],
            "decisions": [],
            "verification": {"passed": [], "pending": []},
            "working_set": [],
            "budgets": {"steps_used": 0, "steps_max": steps_max},
            "resume": {"next_action": "", "prerequisites": []},
            "runtime": {
                "no_progress_windows": 0,
                "last_failure_fingerprint": "",
                "repeated_failure_count": 0,
                "next_decision": "continue",
            },
        }
        for raw in args.file or []:
            relative, digest = project_file(raw)
            payload["working_set"].append(
                {"path": relative.as_posix(), "sha256": digest}
            )
        payload["working_set"].sort(key=lambda item: item["path"])
        write_state(payload)
    return payload


def checkpoint(args: argparse.Namespace) -> dict:
    with locked():
        identifier = selected_session_id(args.id)
        payload = read(identifier)
        before = progress_fingerprint(payload)
        if args.status and args.status != payload["task"]["status"]:
            current = payload["task"]["status"]
            if args.status not in TRANSITIONS.get(current, set()):
                raise StateError(
                    "invalid_transition", f"cannot transition from {current} to {args.status}"
                )
            payload["task"]["status"] = args.status
        for key in ("done", "todo", "blocked"):
            value = getattr(args, key)
            if value is not None:
                payload["progress"][key] = value
        if args.decision is not None:
            payload["decisions"] = args.decision
        if args.context is not None:
            payload["context"] = args.context
        if args.openspec_change is not None:
            payload["task"]["openspec_change"] = args.openspec_change
        if args.verified is not None:
            payload["verification"]["passed"] = args.verified
        if args.pending_verification is not None:
            payload["verification"]["pending"] = args.pending_verification
        for target in args.clear or []:
            if target in {"done", "todo", "blocked"}:
                payload["progress"][target] = []
            elif target in {"decisions", "context", "working-set"}:
                key = "working_set" if target == "working-set" else target
                payload[key] = []
            elif target in {"verified", "pending-verification"}:
                key = "passed" if target == "verified" else "pending"
                payload["verification"][key] = []
            elif target == "prerequisites":
                payload["resume"]["prerequisites"] = []
            elif target == "next-action":
                payload["resume"]["next_action"] = ""
            elif target == "openspec-change":
                payload["task"]["openspec_change"] = ""
        if payload["task"]["status"] == "complete" and (
            not payload["verification"]["passed"]
            or payload["verification"]["pending"]
        ):
            raise StateError(
                "verification_required",
                "completion requires recorded verification and no pending checks",
            )
        if payload["task"]["status"] == "complete" and (
            payload["progress"]["todo"] or payload["progress"]["blocked"]
        ):
            raise StateError(
                "unfinished_work",
                "completion requires empty todo and blocked lists",
            )
        if args.file is not None:
            working_set = []
            for raw in args.file:
                relative, digest = project_file(raw)
                working_set.append({"path": relative.as_posix(), "sha256": digest})
            payload["working_set"] = sorted(working_set, key=lambda item: item["path"])
        if args.steps_used is not None:
            if args.steps_used < payload["budgets"]["steps_used"]:
                raise StateError("invalid_budget", "steps_used may not decrease")
            if args.steps_used > payload["budgets"]["steps_max"]:
                raise StateError("budget_exceeded", "steps_used exceeds steps_max")
            payload["budgets"]["steps_used"] = args.steps_used
        if args.next_action is not None:
            payload["resume"]["next_action"] = args.next_action
        if args.prerequisite is not None:
            payload["resume"]["prerequisites"] = args.prerequisite

        runtime = payload.setdefault(
            "runtime",
            {
                "no_progress_windows": 0,
                "last_failure_fingerprint": "",
                "repeated_failure_count": 0,
                "next_decision": "continue",
            },
        )
        after = progress_fingerprint(payload)
        runtime["no_progress_windows"] = (
            0 if after != before else runtime["no_progress_windows"] + 1
        )
        if args.clear_failure:
            runtime["last_failure_fingerprint"] = ""
            runtime["repeated_failure_count"] = 0
        elif args.failure_fingerprint:
            if args.failure_fingerprint == runtime["last_failure_fingerprint"]:
                runtime["repeated_failure_count"] += 1
            else:
                runtime["last_failure_fingerprint"] = args.failure_fingerprint
                runtime["repeated_failure_count"] = 1

        limits = runtime_limits()
        if payload["task"]["status"] == "complete":
            runtime["no_progress_windows"] = 0
            runtime["last_failure_fingerprint"] = ""
            runtime["repeated_failure_count"] = 0
            runtime["next_decision"] = "stop"
        elif (
            runtime["repeated_failure_count"] >= limits["max_repeated_failure"]
            or runtime["no_progress_windows"] >= limits["max_no_progress_windows"]
        ):
            runtime["next_decision"] = "escalate"
        elif runtime["no_progress_windows"]:
            runtime["next_decision"] = "reflect"
        else:
            runtime["next_decision"] = "continue"
        payload["session"]["updated_at"] = now()
        write_state(payload)
    return payload


def resume(identifier: str | None) -> tuple[dict, bool]:
    with locked():
        payload = read(selected_session_id(identifier))
        # This also promotes a compatible legacy checkpoint into durable state.
        write_state(payload)
    changed: list[dict[str, str]] = []
    missing: list[str] = []
    for item in payload.get("working_set", []):
        path = (ROOT / item["path"]).resolve()
        if not path.is_file():
            missing.append(item["path"])
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != item["sha256"]:
            changed.append({"path": item["path"], "expected": item["sha256"], "actual": actual})
    drifted = bool(changed or missing)
    compact = {
        "schema_version": payload["schema_version"],
        "session": payload["session"],
        "task": payload["task"],
        "progress": payload["progress"],
        "context": payload.get("context", []),
        "decisions": payload["decisions"],
        "verification": payload["verification"],
        "budgets": payload["budgets"],
        "resume": payload["resume"],
        "runtime": payload.get("runtime", {}),
        "integrity": {
            "status": "drifted" if drifted else "clean",
            "changed": changed,
            "missing": missing,
        },
    }
    return compact, drifted


def show(identifier: str | None) -> dict:
    return read(selected_session_id(identifier))


def verify_current() -> dict:
    if not CURRENT_STATE.is_file():
        raise StateError("current_state_missing", f"missing {CURRENT_STATE.relative_to(ROOT)}")
    identifier = current_session_id()
    if identifier is None:
        text = CURRENT_STATE.read_text(encoding="utf-8")
        if "Task: none" not in text:
            raise StateError(
                "invalid_current_state",
                "CURRENT.md has no generated session marker or empty-task sentinel",
            )
        return {"ok": True, "current": None, "status": "empty"}
    payload = read(identifier)
    expected = render_current(payload)
    actual = CURRENT_STATE.read_text(encoding="utf-8")
    if actual != expected:
        raise StateError(
            "current_state_out_of_sync",
            f"regenerate with: {Path(sys.argv[0]).name} resume --id {identifier}",
        )
    return {
        "ok": True,
        "current": identifier,
        "status": payload["task"]["status"],
        "source": state_path(identifier).relative_to(ROOT).as_posix(),
    }


def list_sessions() -> dict:
    by_id = {}
    locations = []
    if LEGACY_STATE_ROOT.exists():
        locations.extend(sorted(LEGACY_STATE_ROOT.glob("*/state.json")))
    if STATE_ROOT.exists():
        locations.extend(sorted(STATE_ROOT.glob("*.json")))
    for path in locations:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            by_id[state["session"]["id"]] = {
                "id": state["session"]["id"],
                "status": state["task"]["status"],
                "updated_at": state["session"]["updated_at"],
                "goal": state["task"]["goal"],
                "durable": path.parent == STATE_ROOT,
            }
        except (KeyError, OSError, json.JSONDecodeError):
            identifier = path.stem if path.parent == STATE_ROOT else path.parent.name
            by_id[identifier] = {"id": identifier, "status": "invalid"}
    items = sorted(by_id.values(), key=lambda item: item["id"])
    return {"schema_version": SCHEMA_VERSION, "sessions": items}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    create = commands.add_parser("start")
    create.add_argument("--id")
    create.add_argument("--goal", required=True)
    create.add_argument("--acceptance", action="append")
    create.add_argument("--todo", action="append")
    create.add_argument("--context", action="append")
    create.add_argument("--openspec-change")
    create.add_argument("--file", action="append")
    create.add_argument("--steps-max", type=int)
    create.add_argument("--replace", action="store_true")
    create.add_argument("--replace-current", action="store_true")

    update = commands.add_parser("checkpoint")
    update.add_argument("--id")
    update.add_argument("--status", choices=sorted(STATUSES))
    update.add_argument("--done", action="append")
    update.add_argument("--todo", action="append")
    update.add_argument("--blocked", action="append")
    update.add_argument("--decision", action="append")
    update.add_argument("--context", action="append")
    update.add_argument("--openspec-change")
    update.add_argument("--verified", action="append")
    update.add_argument("--pending-verification", action="append")
    update.add_argument("--file", action="append")
    update.add_argument("--next-action")
    update.add_argument("--prerequisite", action="append")
    update.add_argument("--steps-used", type=int)
    update.add_argument("--failure-fingerprint")
    update.add_argument("--clear-failure", action="store_true")
    update.add_argument(
        "--clear",
        action="append",
        choices=[
            "blocked",
            "context",
            "decisions",
            "done",
            "next-action",
            "openspec-change",
            "pending-verification",
            "prerequisites",
            "todo",
            "verified",
            "working-set",
        ],
        help="clear a state field; repeat for multiple fields",
    )

    for name in ("show", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--id")
    commands.add_parser("verify")
    commands.add_parser("list")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "start":
            payload = start(args)
            status = 0
        elif args.command == "checkpoint":
            payload = checkpoint(args)
            status = 0
        elif args.command == "show":
            payload = show(args.id)
            status = 0
        elif args.command == "resume":
            payload, drifted = resume(args.id)
            status = 3 if drifted else 0
        elif args.command == "verify":
            payload = verify_current()
            status = 0
        else:
            payload = list_sessions()
            status = 0
    except StateError as exc:
        payload = {"error": exc.code, "message": str(exc)}
        status = 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
