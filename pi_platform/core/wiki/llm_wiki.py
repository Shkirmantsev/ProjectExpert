"""LLM Wiki: the canonical, LLM-curated knowledge layer of a project.

ProjectExpert separates two kinds of knowledge:

* **Derived knowledge** — parsed from the sources, chunked, embedded and
  indexed. It is rebuilt from the repository.
* **Curated knowledge** — the LLM Wiki: pages a calling LLM writes after
  it has understood the project. It explains *why* the code looks the way
  it does, which the parser cannot know.

The Wiki is the OKF v0.2 bundle under ``project-knowledge/wiki/``. The
calling LLM drives it through the MCP server: it searches the project,
writes a page, and the page becomes part of the searchable corpus on the
next refresh.

This module owns the storage contract:

* a page is a Markdown file with OKF frontmatter (``type`` is mandatory);
* writes are atomic and validated against the OKF profile before they
  land;
* a write never escapes the Wiki root;
* every write is recorded in the reserved ``log.md`` so the curated
  knowledge has an audit trail;
* the reserved ``index.md`` keeps its navigation in sync.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from pi_platform.core.canonical.okf import (
    OkfV02Profile,
    OkfValidationError,
    parse_frontmatter,
    validate_wiki_bundle,
)

__all__ = [
    "LlmWiki",
    "LlmWikiError",
    "WikiPage",
    "WIKI_DIR_NAME",
    "INDEX_FILENAME",
    "LOG_FILENAME",
    "PAGE_TYPE_ALLOWED",
    "wiki_root_for",
]


WIKI_DIR_NAME = "wiki"
INDEX_FILENAME = "index.md"
LOG_FILENAME = "log.md"

#: The concept types a curated page may declare. They mirror the OKF
#: concept kinds the platform understands.
PAGE_TYPE_ALLOWED = (
    "Concept",
    "Architecture",
    "Module",
    "Interface",
    "Process",
    "Decision",
    "Requirement",
    "Glossary",
    "Domain",
    "Invariant",
)

_SLUG_RE = re.compile(r"[^a-z0-9._/-]+")
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


# HTTP/MCP requests can mutate the same bundle concurrently in one server.
_WIKI_WRITE_LOCK = threading.RLock()

#: One lock per page. The compare-and-write of a research enrichment
#: happens inside the lock of the page it enriches.
_PAGE_LOCKS: dict[str, threading.RLock] = {}
_PAGE_LOCKS_GUARD = threading.Lock()


def _page_lock(relative_path: str) -> threading.RLock:
    """Return the lock of one page."""

    with _PAGE_LOCKS_GUARD:
        lock = _PAGE_LOCKS.get(relative_path)
        if lock is None:
            lock = threading.RLock()
            _PAGE_LOCKS[relative_path] = lock
        return lock


def _serialized(method):
    @wraps(method)
    def locked(*args, **kwargs):
        with _WIKI_WRITE_LOCK:
            return method(*args, **kwargs)
    return locked


class LlmWikiError(RuntimeError):
    """Raised when a Wiki operation cannot be completed."""


@dataclass(frozen=True)
class WikiPage:
    """One curated Wiki page.

    ``revision`` is the content address of the page body. It is the
    precondition a research enrichment writes against: a caller that
    read a page and then writes it back must present the revision it
    read, so a concurrent change is detected instead of overwritten.
    """

    path: str
    title: str
    type: str
    summary: str
    body: str
    frontmatter: Mapping[str, object] = field(default_factory=dict)
    revision: str = ""
    dependency_notes: tuple = ()

    def as_dict(self, *, include_body: bool = False) -> dict:
        payload = {
            "path": self.path,
            "title": self.title,
            "type": self.type,
            "summary": self.summary,
            "revision": self.revision,
        }
        if include_body:
            payload["body"] = self.body
            payload["frontmatter"] = dict(self.frontmatter)
            payload["dependencyNotes"] = [dict(note) for note in self.dependency_notes]
        return payload


def _rendered_body(rendered: str) -> str:
    """The body of a rendered page, without its frontmatter."""

    try:
        _frontmatter, body = parse_frontmatter(rendered)
    except ValueError:
        return rendered
    return body


def content_revision(body: str) -> str:
    """The content address of a page body.

    The revision is the precondition of a research enrichment: it
    changes whenever the curated text changes.
    """

    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def _read_dependency_notes(frontmatter: Mapping[str, object]) -> list[dict]:
    """Read the dependency provenance of a page."""

    raw = frontmatter.get("pi_dependency_notes")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def wiki_root_for(repo_root: Path) -> Path:
    """Return the canonical Wiki root for ``repo_root``."""

    return Path(repo_root) / "project-knowledge" / WIKI_DIR_NAME


class LlmWiki:
    """Read and write the OKF Wiki bundle of one project."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = wiki_root_for(self.repo_root)
        self.profile = OkfV02Profile()

    # -- reading ----------------------------------------------------------

    def exists(self) -> bool:
        return self.root.is_dir()

    def list_pages(self) -> list[dict]:
        """Return the curated pages, excluding the reserved files."""

        if not self.root.is_dir():
            return []
        pages: list[dict] = []
        for path in sorted(self.root.rglob("*.md")):
            relative = path.relative_to(self.root).as_posix()
            if relative in (INDEX_FILENAME, LOG_FILENAME):
                continue
            page = self._read(path, relative)
            if page is not None:
                pages.append(page.as_dict())
        return pages

    def read_page(self, relative_path: str) -> WikiPage:
        """Read one page by its Wiki-relative path."""

        path = self._resolve(relative_path)
        page = self._read(path, path.relative_to(self.root).as_posix())
        if page is None:
            raise LlmWikiError(f"wiki page not found: {relative_path}")
        return page

    def search_pages(self, query: str, top_k: int = 8) -> list[dict]:
        """Search the curated pages by text overlap.

        The curated Wiki is a small, human-scale corpus; a simple,
        dependency-free overlap score is enough and keeps the Wiki
        usable without the dense index (which needs a refresh). The
        body is searched too, so a page is findable by the content it
        explains and not only by its title.
        """

        terms = [
            token for token in re.split(r"\W+", (query or "").lower())
            if len(token) > 2
        ]
        if not terms:
            return []
        scored: list[tuple[int, dict]] = []
        for path in sorted(self.root.rglob("*.md")):
            relative = path.relative_to(self.root).as_posix()
            if relative in (INDEX_FILENAME, LOG_FILENAME):
                continue
            page = self._read(path, relative)
            if page is None:
                continue
            haystack = (
                page.title + " " + page.summary + " " + page.path + " "
                + page.body
            ).lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, page.as_dict()))
        scored.sort(key=lambda item: (-item[0], item[1]["path"]))
        return [page for _score, page in scored[: max(1, top_k)]]

    def stale_dependency_notes(
        self,
        relative_path: str,
        *,
        inputs: Mapping[str, Mapping[str, object]],
    ) -> list[dict]:
        """Report the recorded dependency evidence that is no longer current.

        ``inputs`` maps a package name to the current ``version`` and
        ``artifactHash`` of that package. A note is stale when the
        recorded value differs from the current one: the curated
        explanation is still readable, but it must be renewed.
        """

        page = self.read_page(relative_path)
        stale: list[dict] = []
        for note in page.dependency_notes:
            package = str(note.get("package") or "")
            current = inputs.get(package)
            if not current:
                continue
            version = current.get("version")
            artifact = current.get("artifactHash")
            if version and note.get("version") and version != note.get("version"):
                stale.append({**note, "staleReason": "version",
                              "currentVersion": version})
            elif artifact and note.get("artifactHash") and artifact != note.get("artifactHash"):
                stale.append({**note, "staleReason": "artifactHash",
                              "currentArtifactHash": artifact})
        return stale

    def validate(self) -> list[str]:
        """Validate the bundle against the OKF profile."""

        if not self.root.is_dir():
            return [f"wiki root is not a directory: {self.root}"]
        self._resolve(INDEX_FILENAME)
        self._resolve(LOG_FILENAME)
        for page in self.root.rglob("*.md"):
            self._resolve(page.relative_to(self.root).as_posix())
        errors = []
        for error in validate_wiki_bundle(self.root, adapter=self.profile):
            errors.append(str(error))
        return errors

    # -- writing ----------------------------------------------------------

    @_serialized
    def write_page(
        self,
        *,
        relative_path: str,
        title: str,
        body: str,
        page_type: str = "Concept",
        summary: str = "",
        author: str = "calling-llm",
        source: str = "",
        dry_run: bool = False,
        expected_revision: str | None = None,
        dependency_notes: Sequence[Mapping[str, object]] = (),
    ) -> dict:
        """Create or update one curated page.

        The page is rendered with OKF frontmatter and validated against
        the OKF profile BEFORE it is written. An invalid page is never
        stored. The write is atomic and the change is recorded in the
        reserved log.

        ``expected_revision`` is the precondition of a research
        enrichment: the caller presents the revision it read, and a
        page that changed in the meantime produces a conflict instead
        of a silent overwrite. ``dependency_notes`` records the
        provenance of the research the page explains, so a later reader
        can tell which evidence the text is based on and whether that
        evidence is still current.
        """

        if not title or not title.strip():
            raise LlmWikiError("a wiki page requires a non-empty title")
        if page_type not in PAGE_TYPE_ALLOWED:
            raise LlmWikiError(
                f"unknown page type {page_type!r}; expected one of "
                f"{list(PAGE_TYPE_ALLOWED)}"
            )
        path = self._resolve(relative_path)
        relative = path.relative_to(self.root).as_posix()
        if relative in (INDEX_FILENAME, LOG_FILENAME):
            raise LlmWikiError(
                "the reserved index and log files are maintained by the platform"
            )
        with _page_lock(relative):
            return self._write_page_locked(
                path=path,
                relative=relative,
                title=title,
                body=body,
                page_type=page_type,
                summary=summary,
                author=author,
                source=source,
                dry_run=dry_run,
                expected_revision=expected_revision,
                dependency_notes=dependency_notes,
            )

    def _write_page_locked(
        self,
        *,
        path: Path,
        relative: str,
        title: str,
        body: str,
        page_type: str,
        summary: str,
        author: str,
        source: str,
        dry_run: bool,
        expected_revision: str | None,
        dependency_notes: Sequence[Mapping[str, object]],
    ) -> dict:
        current = self._read(path, relative) if path.is_file() else None
        if expected_revision is not None:
            actual = current.revision if current is not None else ""
            if actual != expected_revision:
                # The page changed since the caller read it. The caller
                # re-reads and merges; nothing is overwritten here.
                return {
                    "ok": False,
                    "written": False,
                    "conflict": True,
                    "path": relative,
                    "expectedRevision": expected_revision,
                    "currentRevision": actual,
                    "reason": ("the page changed since it was read; read it "
                               "again and merge the change"),
                }
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        frontmatter: dict[str, object] = {
            "type": page_type,
            "title": title.strip(),
        }
        if summary and summary.strip():
            frontmatter["summary"] = summary.strip()
        frontmatter["pi_author"] = author
        frontmatter["pi_updated"] = now
        if source:
            frontmatter["pi_source"] = source
        notes = [dict(note) for note in dependency_notes
                 if isinstance(note, Mapping)]
        if notes:
            frontmatter["pi_dependency_notes"] = json.dumps(
                notes, sort_keys=True)
        rendered = self.profile.render_concept_markdown(frontmatter, body)
        try:
            self.profile.validate_file(path, rendered)
        except OkfValidationError as exc:
            raise LlmWikiError(
                f"the page does not satisfy the OKF v{self.profile.profile_version} "
                f"profile: {exc.reason}"
            ) from exc
        # The revision is the address of the *stored* body, so a caller
        # that reads the page back compares equal.
        revision = content_revision(_rendered_body(rendered))
        if dry_run:
            return {
                "ok": True,
                "written": False,
                "dry_run": True,
                "path": relative,
                "bytes": len(rendered.encode("utf-8")),
                "revision": revision,
            }
        # Validate reserved files before committing any page.
        self._resolve(INDEX_FILENAME)
        self._resolve(LOG_FILENAME)
        existed = path.is_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, rendered)
        self._append_log(
            "updated" if existed else "created", relative, title, now,
        )
        index_state = "ready"
        try:
            self.refresh_index()
        except (OSError, LlmWikiError):
            # The page is stored; the navigation index is retried later.
            index_state = "failed"
        return {
            "ok": True,
            "written": True,
            "stored": True,
            "created": not existed,
            "path": relative,
            "bytes": len(rendered.encode("utf-8")),
            "revision": revision,
            "index_refreshed": index_state == "ready",
            "index_state": index_state,
            "retrieval_index_state": "pending",
            "dependency_notes": notes,
        }

    @_serialized
    def refresh_index(self) -> Path | None:
        """Rewrite the navigation section of the reserved ``index.md``.

        The OKF-required frontmatter is preserved; only the generated
        navigation list is replaced.
        """

        index_path = self._resolve(INDEX_FILENAME)
        if not index_path.is_file():
            return None
        raw = index_path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(raw)
        navigation = self._render_navigation()
        marker = "<!-- project-intelligence:wiki-navigation -->"
        if marker in body:
            head, _, _tail = body.partition(marker)
            body = head + marker + "\n" + navigation
        else:
            body = body.rstrip("\n") + "\n\n" + marker + "\n" + navigation
        rendered = self.profile.render_concept_markdown(dict(frontmatter), body)
        self._atomic_write(index_path, rendered)
        return index_path

    @_serialized
    def ensure_scaffold(self) -> list[str]:
        """Create the reserved files of an empty Wiki bundle.

        Returns the list of created paths. Existing files are preserved:
        the scaffold never overwrites curated knowledge.
        """

        created: list[str] = []
        self._resolve(INDEX_FILENAME)
        self._resolve(LOG_FILENAME)
        self.root.mkdir(parents=True, exist_ok=True)
        index_path = self._resolve(INDEX_FILENAME)
        if not index_path.is_file():
            index_path.write_text(
                self.profile.render_concept_markdown(
                    {
                        "okf_version": "0.2",
                        "type": "WikiIndex",
                        "title": "Project Knowledge Index",
                        "pi_status": "active",
                    },
                    "# Project Knowledge Index\n\n"
                    "Curated project knowledge. Each page is written by a "
                    "calling LLM after it understood the project, and is "
                    "validated against the OKF v0.2 profile.\n",
                ),
                encoding="utf-8",
            )
            created.append(index_path.name)
        log_path = self._resolve(LOG_FILENAME)
        if not log_path.is_file():
            log_path.write_text(
                self.profile.render_concept_markdown(
                    {
                        "type": "Log",
                        "title": "Project Knowledge Log",
                        "pi_status": "active",
                    },
                    "# Log\n\n"
                    "Chronological record of the curated knowledge changes.\n",
                ),
                encoding="utf-8",
            )
            created.append(log_path.name)
        return created

    # -- internal helpers -------------------------------------------------

    def _resolve(self, relative_path: str) -> Path:
        """Resolve a Wiki-relative path and refuse to leave the root."""

        candidate = (relative_path or "").strip().replace("\\", "/")
        if not candidate:
            raise LlmWikiError("a wiki page path is required")
        if candidate.startswith("/") or candidate.startswith("~"):
            raise LlmWikiError(
                "a wiki page path must be relative to the wiki root"
            )
        if candidate.endswith(".md") is False:
            candidate = candidate + ".md"
        parts = [segment for segment in candidate.split("/") if segment]
        if not parts:
            raise LlmWikiError("a wiki page path is required")
        for segment in parts:
            if segment in (".", ".."):
                raise LlmWikiError(
                    "a wiki page path must not traverse outside the wiki root"
                )
            if not _SAFE_SEGMENT_RE.match(segment):
                raise LlmWikiError(
                    f"invalid wiki page path segment {segment!r}; use letters, "
                    "digits, '.', '_' or '-'"
                )
        # Reject symlink components, including the root and reserved paths.
        current = self.repo_root
        for segment in ("project-knowledge", WIKI_DIR_NAME, *parts):
            current = current / segment
            if current.is_symlink():
                raise LlmWikiError("wiki paths must not contain symbolic links")
        path = (self.root / Path(*parts)).resolve()
        root = self.root.resolve()
        if not path.is_relative_to(root):
            raise LlmWikiError(
                "a wiki page path must not traverse outside the wiki root"
            )
        return path

    def _read(self, path: Path, relative: str) -> WikiPage | None:
        try:
            self._resolve(relative)
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, LlmWikiError):
            return None
        try:
            frontmatter, body = parse_frontmatter(raw)
        except ValueError:
            return None
        title = str(frontmatter.get("title") or "").strip()
        page_type = str(frontmatter.get("type") or "").strip()
        summary = str(frontmatter.get("summary") or "").strip()
        if not title:
            for line in body.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        if not summary:
            summary = self._first_paragraph(body)
        return WikiPage(
            path=relative,
            title=title,
            type=page_type,
            summary=summary,
            body=body,
            frontmatter=dict(frontmatter),
            revision=content_revision(body),
            dependency_notes=tuple(_read_dependency_notes(frontmatter)),
        )

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                             dir=path.parent, prefix=".wiki-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _first_paragraph(body: str, max_chars: int = 320) -> str:
        for block in body.split("\n\n"):
            cleaned = block.strip()
            if not cleaned or cleaned.startswith("#") or cleaned.startswith("<!--"):
                continue
            return cleaned[:max_chars]
        return ""

    def _render_navigation(self) -> str:
        pages = self.list_pages()
        if not pages:
            return "\n_No curated pages yet._\n"
        lines = ["", "## Curated pages", ""]
        for page in pages:
            lines.append(f"- [{page['title']}]({page['path']}) — {page['type']}")
        lines.append("")
        return "\n".join(lines)

    def _append_log(
        self, action: str, relative: str, title: str, timestamp: str,
    ) -> None:
        log_path = self._resolve(LOG_FILENAME)
        if not log_path.is_file():
            self.ensure_scaffold()
        entry = (
            f"\n- {timestamp} — {action} `{relative}` — {title}\n"
        )
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(entry)
        except OSError as exc:
            raise LlmWikiError(f"page stored but audit log append failed: {exc}") from exc
