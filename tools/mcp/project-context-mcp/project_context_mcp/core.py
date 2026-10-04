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
        state = {"documents": len(docs), "chunks": chunks, "database": target.relative_to(root).as_posix()}
        (target.parent / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return state
    finally:
        conn.close()
        pending.unlink(missing_ok=True)


def ensure_index(root: Path) -> Path:
    target = db_path(root)
    if not target.exists():
        build_index(root)
    return target


def search(root: Path, query: str, top_k: int = 8) -> list[dict]:
    target = ensure_index(root)
    terms = [t for t in WORD.findall(query) if len(t) > 1]
    if not terms:
        return []
    fts = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms[:12])
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
          SELECT s.document_id, d.kind, d.title, d.summary, d.path, s.heading, bm25(search) AS rank
          FROM search s JOIN document d ON d.id=s.document_id
          WHERE search MATCH ? ORDER BY rank LIMIT ?
        """, (fts, max(1, min(top_k, 20)))).fetchall()
        seen: set[str] = set(); out: list[dict] = []
        for row in rows:
            if row["document_id"] in seen:
                continue
            seen.add(row["document_id"])
            out.append({"id": row["document_id"], "kind": row["kind"], "title": row["title"], "summary": row["summary"], "path": row["path"], "matchedSection": row["heading"]})
        return out
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
    for path in root.rglob("*"):
        if len(out) >= max_results:
            break
        if not path.is_file() or any(part in ignored for part in path.relative_to(root).parts):
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            continue
        if path.suffix.lower() not in {".py", ".java", ".go", ".js", ".ts", ".tsx", ".jsx", ".cs", ".rs", ".kt", ".kts", ".rb", ".php"}:
            continue
        try:
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if needle in line.lower():
                    out.append({"path": path.relative_to(root).as_posix(), "line": n, "text": line.strip()[:300]})
                    if len(out) >= max_results:
                        break
        except OSError:
            pass
    return out
