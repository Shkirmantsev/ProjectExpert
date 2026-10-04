#!/usr/bin/env python3
"""Build a provider-neutral stable-prefix manifest for prompt caching."""

from __future__ import annotations

import argparse
import hashlib
import json
import re

from common import ROOT
from skill_router import CANONICAL, discover


SAFE_LABEL = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
HASH_REF = re.compile(r"^sha256:[0-9a-fA-F]+$")


class ManifestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def hash_file(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(args: argparse.Namespace) -> dict:
    if not SAFE_LABEL.fullmatch(args.role) or not SAFE_LABEL.fullmatch(args.tool_profile):
        raise ManifestError("invalid_label", "role and tool profile must be safe labels")
    if not HASH_REF.fullmatch(args.project_profile_hash):
        raise ManifestError(
            "invalid_project_profile_hash", "project profile hash must use sha256:<hex>"
        )

    catalog = discover()
    requested = sorted({CANONICAL.get(name, name) for name in args.skill or []})
    unknown = [name for name in requested if name not in catalog]
    if unknown:
        raise ManifestError("unknown_skill", "unknown skill: " + ", ".join(unknown))

    skill_prefix = [
        {
            "name": name,
            "sha256": hash_file(catalog[name].path),
        }
        for name in requested
    ]
    policy_files = [ROOT / "AGENTS.md", ROOT / ".harness" / "runtime.json"]
    policy_prefix = [
        {
            "path": str(path.relative_to(ROOT)),
            "sha256": hash_file(path),
        }
        for path in policy_files
    ]
    stable = {
        "policy_prefix": policy_prefix,
        "role": args.role,
        "tool_profile": args.tool_profile,
        "skill_prefix": skill_prefix,
        "project_profile_hash": args.project_profile_hash.lower(),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    prefix_hash = hashlib.sha256(encoded).hexdigest()
    return {
        "schema_version": "1.0",
        **stable,
        "stable_prefix_hash": "sha256:" + prefix_hash,
        "cache_key": f"harness:{args.role}:{args.tool_profile}:{prefix_hash[:16]}",
        "cache_intent": {
            "scope": "project-role-tool-skillset",
            "reuse": "high",
            "stability": "high",
            "provider_adapter_required": True,
        },
        "volatile_suffix": [
            "task-delta",
            "latest-tool-output",
            "latest-diff-or-error",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True)
    parser.add_argument("--tool-profile", required=True)
    parser.add_argument("--project-profile-hash", required=True)
    parser.add_argument("--skill", action="append")
    args = parser.parse_args()
    try:
        payload = build(args)
        status = 0
    except ManifestError as exc:
        payload = {"error": exc.code, "message": str(exc)}
        status = 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
