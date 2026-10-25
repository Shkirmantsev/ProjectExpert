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

import os
import re
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


class LlmWikiError(RuntimeError):
    """Raised when a Wiki operation cannot be completed."""


@dataclass(frozen=True)
class WikiPage:
    """One curated Wiki page."""

    path: str
    title: str
    type: str
    summary: str
    body: str
    frontmatter: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self, *, include_body: bool = False) -> dict:
        payload = {
            "path": self.path,
            "title": self.title,
            "type": self.type,
            "summary": self.summary,
        }
        if include_body:
            payload["body"] = self.body
            payload["frontmatter"] = dict(self.frontmatter)
        return payload


def wiki_root_for(repo_root: Path) -> Path:
    """Return the canonical Wiki root for ``repo_root``."""

    return Path(repo_root) / "project-knowledge" / WIKI_DIR_NAME


class LlmWiki:
    """Read and write the OKF Wiki bundle of one project."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)
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

    def validate(self) -> list[str]:
        """Validate the bundle against the OKF profile."""

        if not self.root.is_dir():
            return [f"wiki root is not a directory: {self.root}"]
        errors = []
        for error in validate_wiki_bundle(self.root, adapter=self.profile):
            errors.append(str(error))
        return errors

    # -- writing ----------------------------------------------------------

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
    ) -> dict:
        """Create or update one curated page.

        The page is rendered with OKF frontmatter and validated against
        the OKF profile BEFORE it is written. An invalid page is never
        stored. The write is atomic and the change is recorded in the
        reserved log.
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
        rendered = self.profile.render_concept_markdown(frontmatter, body)
        try:
            self.profile.validate_file(path, rendered)
        except OkfValidationError as exc:
            raise LlmWikiError(
                f"the page does not satisfy the OKF v{self.profile.profile_version} "
                f"profile: {exc.reason}"
            ) from exc
        if dry_run:
            return {
                "ok": True,
                "written": False,
                "dry_run": True,
                "path": relative,
                "bytes": len(rendered.encode("utf-8")),
            }
        existed = path.is_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
        self._append_log(
            "updated" if existed else "created", relative, title, now,
        )
        self.refresh_index()
        return {
            "ok": True,
            "written": True,
            "created": not existed,
            "path": relative,
            "bytes": len(rendered.encode("utf-8")),
            "index_refreshed": True,
        }

    def refresh_index(self) -> Path | None:
        """Rewrite the navigation section of the reserved ``index.md``.

        The OKF-required frontmatter is preserved; only the generated
        navigation list is replaced.
        """

        index_path = self.root / INDEX_FILENAME
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
        temporary = index_path.with_name(index_path.name + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, index_path)
        return index_path

    def ensure_scaffold(self) -> list[str]:
        """Create the reserved files of an empty Wiki bundle.

        Returns the list of created paths. Existing files are preserved:
        the scaffold never overwrites curated knowledge.
        """

        created: list[str] = []
        self.root.mkdir(parents=True, exist_ok=True)
        index_path = self.root / INDEX_FILENAME
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
        log_path = self.root / LOG_FILENAME
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
        path = (self.root / Path(*parts)).resolve()
        root = self.root.resolve()
        if not path.is_relative_to(root):
            raise LlmWikiError(
                "a wiki page path must not traverse outside the wiki root"
            )
        return path

    def _read(self, path: Path, relative: str) -> WikiPage | None:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
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
        )

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
        log_path = self.root / LOG_FILENAME
        if not log_path.is_file():
            self.ensure_scaffold()
        entry = (
            f"\n- {timestamp} — {action} `{relative}` — {title}\n"
        )
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(entry)
        except OSError:
            # The audit trail must never block the write itself.
            pass
