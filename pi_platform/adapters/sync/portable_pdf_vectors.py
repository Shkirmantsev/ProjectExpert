"""Exact PDF projection identity, independent of machine-local crop paths."""
from contextlib import closing
import json
import sqlite3
from .portable_format import PortableSnapshotError, sha


def projection_hash(value):
    return sha(json.dumps(value, sort_keys=True).encode())


def validate_projection(value, *, canonical_hash, image_hash, expected):
    from pi_platform.adapters.pdf.runtime_projection import PDF_RUNTIME_PROJECTION_VERSION
    if (not isinstance(value, dict) or set(value) != {'version', 'aggregation', 'max_tokens', 'canonical_text_hash', 'segments', 'image_hash'}
            or value['version'] != PDF_RUNTIME_PROJECTION_VERSION or value['aggregation'] != 'normalized-mean/v1'
            or value['max_tokens'] != 512 or value['canonical_text_hash'] != canonical_hash
            or value['image_hash'] not in (None, image_hash) or not isinstance(value['segments'], (list, tuple))
            or not value['segments'] or any(not isinstance(s, str) or not s for s in value['segments'])
            or projection_hash(value) != expected):
        raise PortableSnapshotError('Invalid PDF vector projection binding')


def persist_projections(cache_root, profile, projections):
    if not projections:
        return
    with closing(sqlite3.connect(cache_root / 'indexes' / 'embeddings.sqlite')) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS portable_pdf_projections(
            chunk_id TEXT,profile TEXT,projection_hash TEXT,body TEXT,
            PRIMARY KEY(chunk_id,profile,projection_hash))''')
        db.executemany('INSERT OR IGNORE INTO portable_pdf_projections VALUES(?,?,?,?)',
            ((cid, profile, projection_hash(value), json.dumps(value, sort_keys=True)) for cid, value in projections.items()))
