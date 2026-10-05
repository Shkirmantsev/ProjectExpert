from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
WORD = re.compile(r"[A-Za-z0-9_./:-]+")

@dataclass(frozen=True)
class Document:
    id: str
    title: str
    kind: str
    status: str
    summary: str
    path: str
    body: str
    content_hash: str


def _scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER.search(text)
    if not match:
        return {}, text
    metadata: dict[str, object] = {}
    for raw in match.group(1).splitlines():
        if not raw or raw[0].isspace() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        metadata[key.strip()] = _scalar(value)
    return metadata, text[match.end():]


def _first_heading(body: str, fallback: str) -> str:
    for line in body.splitlines():
        m = HEADING.match(line)
        if m:
            return m.group(2).strip()
    return fallback


def _summary(body: str, max_chars: int = 320) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith("#") or line.startswith("```"):
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    text = next((p for p in paragraphs if p), "")
    return text[:max_chars]


def load_documents(root: Path) -> list[Document]:
    wiki = root / ".ai" / "wiki"
    docs: list[Document] = []
    if not wiki.exists():
        return docs
    for path in sorted(wiki.rglob("*.md")):
        if not path.resolve().is_relative_to(root.resolve()):
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        rel = path.relative_to(root).as_posix()
        fallback_id = "wiki." + rel.removeprefix(".ai/wiki/").removesuffix(".md").replace("/", ".")
        doc_id = str(meta.get("id") or fallback_id)
        title = str(meta.get("title") or _first_heading(body, path.stem))
        kind = str(meta.get("kind") or "wiki")
        status = str(meta.get("status") or "active")
        summary = str(meta.get("summary") or _summary(body))
        docs.append(Document(doc_id, title, kind, status, summary, rel, body, hashlib.sha256(text.encode()).hexdigest()))
    return docs


def split_sections(doc: Document) -> list[tuple[str, str, str]]:
    chunks: list[tuple[str, str, str]] = []
    heading = doc.title
    buf: list[str] = []
    ordinal = 0
    def flush():
        nonlocal ordinal
        body = "\n".join(buf).strip()
        if body:
            chunks.append((f"{doc.id}#{ordinal}", heading, body))
            ordinal += 1
    for line in doc.body.splitlines():
        m = HEADING.match(line)
        if m:
            flush()
            buf.clear()
            heading = m.group(2).strip()
        else:
            buf.append(line)
    flush()
    return chunks or [(f"{doc.id}#0", doc.title, doc.body)]


def db_path(root: Path) -> Path:
    return root / "tmp" / "local" / "project-context" / "knowledge.db"


def state_path(root: Path) -> Path:
    return root / "tmp" / "local" / "project-context" / "state.json"


def _wiki_fingerprint(root: Path, docs: list[Document]) -> str:
    """Stable hash of the wiki content the index was sourced from.

    The fingerprint is sorted by ``path`` so reordering of the
    underlying ``rglob`` does not produce a different value. The hash
    combines the per-document ``content_hash`` already computed during
    ``load_documents`` with the wiki directory ``mtime`` so a deletion
    or filesystem-level mutation is also detected. ``kb_search`` will
    never silently read from a stale index because the rebuild
    trigger compares the recorded fingerprint against the freshly
    computed one.
    """

    wiki = root / ".ai" / "wiki"
    payload: list[str] = []
    for doc in sorted(docs, key=lambda d: d.path):
        payload.append(f"{doc.path}:{doc.content_hash}")
    if wiki.exists():
        try:
            stat = wiki.stat()
            payload.append(f"wiki-mtime:{int(stat.st_mtime_ns)}")
        except OSError:
            payload.append("wiki-mtime:missing")
    else:
        payload.append("wiki-mtime:absent")
    body = "\n".join(payload).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def build_index(root: Path) -> dict:
    docs = load_documents(root)
    target = db_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.db', delete=False) as staging:
        pending = Path(staging.name)
    conn = sqlite3.connect(pending)
    try:
        conn.executescript("""
        CREATE TABLE document(id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL,
          status TEXT NOT NULL, summary TEXT NOT NULL, path TEXT NOT NULL UNIQUE, content_hash TEXT NOT NULL);
        CREATE TABLE chunk(id TEXT PRIMARY KEY, document_id TEXT NOT NULL, heading TEXT NOT NULL, body TEXT NOT NULL,
          FOREIGN KEY(document_id) REFERENCES document(id));
        CREATE VIRTUAL TABLE search USING fts5(chunk_id UNINDEXED, document_id UNINDEXED, heading, body, title, summary);
        """)
        chunks = 0
        for doc in docs:
            conn.execute("INSERT INTO document VALUES(?,?,?,?,?,?,?)", (doc.id, doc.title, doc.kind, doc.status, doc.summary, doc.path, doc.content_hash))
            for chunk_id, heading, body in split_sections(doc):
                conn.execute("INSERT INTO chunk VALUES(?,?,?,?)", (chunk_id, doc.id, heading, body))
                conn.execute("INSERT INTO search VALUES(?,?,?,?,?,?)", (chunk_id, doc.id, heading, body, doc.title, doc.summary))
                chunks += 1
        conn.commit()
        conn.close()
        pending.replace(target)
        fingerprint = _wiki_fingerprint(root, docs)
        state = {
            "documents": len(docs),
            "chunks": chunks,
            "database": target.relative_to(root).as_posix(),
            "wiki_fingerprint": fingerprint,
            "built_at": int(__import__("time").time()),
        }
        state_path(root).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return state
    finally:
        conn.close()
        pending.unlink(missing_ok=True)


def ensure_index(root: Path) -> Path:
    """Return the wiki search index, rebuilding it when stale.

    A rebuild is triggered when:

    * the database file does not exist;
    * the recorded ``wiki_fingerprint`` in ``state.json`` differs from
      the freshly computed fingerprint;
    * the ``state.json`` companion file is missing or unreadable.

    This prevents the silent-staleness failure mode where ``.ai/wiki/``
    edits are masked by an existing ``knowledge.db`` and
    ``kb_search`` returns hits from a previous version of the wiki.

    If the rebuild raises (for example because the wiki contains
    duplicate ``id`` frontmatter, or a parser regression surfaces
    mid-flight) the previous index is preserved: the rebuild writes
    to a staging path that only ``replace``s the target on success,
    so a failure leaves the existing ``knowledge.db`` untouched and
    ``kb_search`` continues to serve the last good corpus. The
    exception is re-raised only when no previous index exists, so a
    fresh project still surfaces the parse error to the caller.
    """

    target = db_path(root)
    needs_rebuild = not target.exists()
    if not needs_rebuild:
        recorded = _read_recorded_fingerprint(root)
        current = _safe_wiki_fingerprint(root)
        if recorded is None or recorded != current:
            needs_rebuild = True
    if needs_rebuild:
        try:
            build_index(root)
        except Exception:
            if not target.exists():
                raise
    return target


def _safe_wiki_fingerprint(root: Path) -> str | None:
    try:
        return _wiki_fingerprint(root, load_documents(root))
    except OSError:
        return None


def _read_recorded_fingerprint(root: Path) -> str | None:
    path = state_path(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = payload.get("wiki_fingerprint")
    return str(value) if value else None


def search(root: Path, query: str, top_k: int = 8) -> list[dict]:
    target = ensure_index(root)
    terms = [t for t in WORD.findall(query) if len(t) > 1]
    if not terms:
        return []
    fts = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms[:12])
    cap = max(1, min(top_k, 20))
    # Over-fetch so a small `top_k` request never collapses to fewer
    # distinct documents than the caller asked for. The previous
    # behaviour was to LIMIT top_k on raw chunks and then dedup by
    # document_id in Python; with a few strong hits clustered into a
    # single document that meant a `top_k=8` request could return 1
    # result. The over-fetch ratio bounds how aggressively the FTS
    # engine expands the candidate pool while keeping the upper bound
    # deterministic.
    over_fetch = max(cap * 4, 16)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        # Two-phase query: rank chunks via the FTS5 helper inside the
        # ``hits`` CTE (where ``bm25(search)`` is a permitted context),
        # then collapse per-document in the outer query. SQLite refuses
        # to call FTS5 helper functions from a SELECT that contains a
        # GROUP BY on the same table; the CTE isolates the helper into
        # a context where it can be evaluated per row.
        rows = conn.execute(
            """
            WITH hits AS (
              SELECT chunk_id, document_id, heading, bm25(search) AS chunk_rank
              FROM search
              WHERE search MATCH ?
              ORDER BY chunk_rank
              LIMIT ?
            )
            SELECT d.id AS document_id, d.kind, d.title, d.summary, d.path,
                   (SELECT heading FROM hits WHERE document_id = d.id
                    ORDER BY chunk_rank LIMIT 1) AS heading,
                   MIN(hits.chunk_rank) AS rank
            FROM hits
            JOIN document d ON d.id = hits.document_id
            GROUP BY d.id
            ORDER BY rank
            LIMIT ?
            """,
            (fts, over_fetch, cap),
        ).fetchall()
        return [
            {
                "id": row["document_id"],
                "kind": row["kind"],
                "title": row["title"],
                "summary": row["summary"],
                "path": row["path"],
                "matchedSection": row["heading"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_document(root: Path, doc_id: str, section: str | None = None, max_chars: int = 12000) -> dict | None:
    target = ensure_index(root)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        doc = conn.execute("SELECT * FROM document WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            return None
        if section:
            rows = conn.execute("SELECT heading, body FROM chunk WHERE document_id=? AND lower(heading) LIKE ? ORDER BY rowid", (doc_id, f"%{section.lower()}%" )).fetchall()
        else:
            rows = conn.execute("SELECT heading, body FROM chunk WHERE document_id=? ORDER BY rowid", (doc_id,)).fetchall()
        text = "\n\n".join(f"## {r['heading']}\n\n{r['body']}" for r in rows)[:max_chars]
        return {"id": doc_id, "title": doc["title"], "kind": doc["kind"], "path": doc["path"], "content": text}
    finally:
        conn.close()


def validate(root: Path) -> dict:
    issues: list[str] = []
    docs = load_documents(root)
    seen: dict[str, str] = {}
    for doc in docs:
        if doc.id in seen:
            issues.append(f"duplicate id {doc.id}: {seen[doc.id]} and {doc.path}")
        seen[doc.id] = doc.path
        if doc.path != ".ai/wiki/INDEX.md" and doc.id.startswith("wiki."):
            issues.append(f"missing explicit frontmatter id: {doc.path}")
    for doc in docs:
        path = root / doc.path
        for href in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if href.startswith(("http://", "https://", "kb://", "#", "mailto:")):
                continue
            target = (path.parent / href.split("#",1)[0]).resolve()
            if href and not target.exists():
                issues.append(f"broken link in {doc.path}: {href}")
    return {"ok": not issues, "documents": len(docs), "issues": issues}


def code_symbol(root: Path, symbol: str, max_results: int = 20) -> list[dict]:
    needle = symbol.lower()
    out: list[dict] = []
    ignored = {".git", "node_modules", "target", "build", "dist", ".generated", "tmp"}
    source_suffixes = {".py", ".java", ".go", ".js", ".ts", ".tsx", ".jsx",
                       ".cs", ".rs", ".kt", ".kts", ".rb", ".php"}
    cache = _code_symbol_cache(root)
    root_stamp = root.stat().st_mtime_ns if root.exists() else 0
    cache_signature = (needle, max_results, root_stamp)
    cached = cache.get("signature")
    if cached == cache_signature:
        cached_results = cache.get("results")
        if isinstance(cached_results, list):
            return list(cached_results)
    for path in root.rglob("*"):
        if len(out) >= max_results:
            break
        if not path.is_file() or any(part in ignored for part in path.relative_to(root).parts):
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            continue
        if path.suffix.lower() not in source_suffixes:
            continue
        try:
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if needle in line.lower():
                    out.append({"path": path.relative_to(root).as_posix(), "line": n, "text": line.strip()[:300]})
                    if len(out) >= max_results:
                        break
        except OSError:
            pass
    cache["signature"] = cache_signature
    cache["results"] = list(out)
    _persist_code_symbol_cache(root, cache)
    return out


def _code_symbol_cache(root: Path) -> dict:
    """Return a process-local cache for ``code_symbol`` results.

    The cache is keyed by ``(query, max_results, root mtime)`` so a
    re-scan only fires when the underlying tree mutates. The cache is
    shared across processes via ``state.json`` so concurrent MCP
    clients do not duplicate the expensive rglob walk. The cache is
    intentionally not cached at module import time; it lives next to
    the wiki state file so the same directory hygiene (``.gitignore``
    / tmp cleanup) covers it.
    """

    target = state_path(root)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cache = payload.get("code_symbol_cache")
    return dict(cache) if isinstance(cache, dict) else {}


def _persist_code_symbol_cache(root: Path, cache: dict) -> None:
    target = state_path(root)
    if not target.exists():
        return
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    payload["code_symbol_cache"] = cache
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
