from __future__ import annotations

import hashlib
import posixpath
import re
import uuid

_SESSION_RE = re.compile(r"[A-Za-z0-9_.:-]{1,160}")


def validate_project_root(
    project_root: str,
    allowed_roots: tuple[str, ...] | None = None,
) -> str:
    root = (project_root or "").strip()
    if not root.startswith("/"):
        raise ValueError("project_root must be an absolute POSIX path on the main machine")
    if "\n" in root or "\r" in root or "\x00" in root:
        raise ValueError("project_root contains forbidden control characters")
    if root == "/":
        raise ValueError("project_root=/ is forbidden")
    normalized = posixpath.normpath(root)
    if allowed_roots is not None:
        allowed = {posixpath.normpath(item) for item in allowed_roots if item}
        if not allowed:
            raise ValueError("no allowed project roots are configured")
        # These paths live on the main machine behind Hermes' SSH backend, not
        # on this sidecar host. Enforce exact operator-configured roots rather
        # than pretending local resolve()/stat() can authorize remote files.
        if normalized not in allowed:
            raise ValueError("project_root is outside HERMES_ALLOWED_PROJECT_ROOTS")
    return normalized


def native_session_id(project_root: str, requested: str = "") -> str:
    """Return an explicit session id or create a fresh project-scoped one.

    A fresh session is the safe default: unrelated Claude delegations in the
    same repository must not silently share Hermes conversation history.
    Callers that intentionally continue a prior delegation pass the returned
    session_id back on the next hermes_run call.
    """
    requested = (requested or "").strip()
    if requested:
        if not _SESSION_RE.fullmatch(requested):
            raise ValueError("session_id contains unsupported characters or is too long")
        return requested
    digest = hashlib.sha256(validate_project_root(project_root).encode("utf-8")).hexdigest()[:10]
    return f"claude-hermes-{digest}-{uuid.uuid4().hex[:12]}"


def instructions(project_root: str) -> str:
    root = validate_project_root(project_root)
    return f"""You are the native remote Hermes Agent delegated from Claude Code.
The caller's authorized working repository on the MAIN machine is:
{root}

Use YOUR OWN Hermes tools. Your terminal/file/search/vision operations are backed by the configured native SSH environment on the main machine.
At the beginning of this run, establish repository context with a harmless command equivalent to:
  cd {root} && pwd
Then keep repository work inside {root}. Do not use or request any custom project-file bridge, binding database, attachment relay, Claude Code, OpenCode, or Codex to perform the task.

For source/text/config/PDF/archive/other repository files, use your native file/terminal tools and relevant installed skills/CLI utilities. For repository images, use Hermes native vision/image tooling on the repository path; current Hermes can resolve image bytes through a non-local SSH backend. If the active main model is text-only, use the configured auxiliary vision route rather than fabricating image contents.

Respect AGENTS.md and project-local instructions found in the repository. Never expose credentials or files that the dedicated SSH account cannot access."""
