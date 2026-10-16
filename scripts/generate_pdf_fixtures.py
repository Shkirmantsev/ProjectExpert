"""Synthetic PDF fixture generator for the v0.8 Tier-2 eval corpus.

The v0.8 refinement's Change Package J needs a `generated-pdf`
sub-corpus with 10 / 100 / 600-page sanitised fixtures
(``evals/corpus/generated-pdf/``). We cannot ship a real
``pypdf`` / ``docling`` dependency, so this script generates
the minimum valid PDF byte stream using the stdlib only.

The generated PDFs are content-free fixtures: every page carries
a single line of text that names the page number so the
DoclingPdfAdapter STUB's prescan / page_count logic still
works. The `manifest.json` alongside the PDFs names the chunk
ids the golden_queries.yaml references; the manifest is the
authoritative source for chunk→page mapping.

The script is invoked once at fixture build time:

    python3 scripts/generate_pdf_fixtures.py
    python3 scripts/generate_pdf_fixtures.py --out tmp/local/evals

The generated PDFs live under ``evals/corpus/generated-pdf/``
by default; the operator can override ``--out`` for confidential
corpora per the plan §28 / J5 rule that allows
``tmp/local/evals/`` for non-checked-in corpora.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


__all__ = ["build_pdf", "write_fixtures"]


# Minimal valid PDF 1.4. The xref offsets are recomputed at
# write time; the placeholder values are replaced by
# :func:`_render_pdf`.
_PDF_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


def build_pdf(*, page_count: int, title: str) -> bytes:
    """Return the byte stream of a minimal ``page_count``-page PDF.

    The PDF is content-free: every page renders a single
    Helvetica line that names the page number so the prescan
    logic still picks up the page count. Tables and figures
    are not encoded in the PDF byte stream; the
    ``manifest.json`` alongside the file is the authoritative
    source for the chunk / table / figure anchors the golden
    queries reference.
    """

    if page_count <= 0:
        raise ValueError(
            f"page_count must be positive, got {page_count}"
        )
    objects: list[bytes] = []

    # 1. Catalog
    objects.append(
        b"1 0 obj\n"
        b"<< /Type /Catalog /Pages 2 0 R >>\n"
        b"endobj\n"
    )
    # 2. Pages
    page_refs = " ".join(f"{3 + 2 * p} 0 R" for p in range(page_count))
    objects.append(
        f"2 0 obj\n"
        f"<< /Type /Pages /Kids [{page_refs}] /Count {page_count} >>\n"
        f"endobj\n".encode("utf-8")
    )
    # 3..N. Page + content pairs.
    for p in range(1, page_count + 1):
        page_obj_idx = 3 + 2 * (p - 1)
        content_obj_idx = page_obj_idx + 1
        # Page object
        objects.append(
            f"{page_obj_idx} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {content_obj_idx} 0 R "
            f"/Resources << /Font << /F1 {3 + 2 * page_count} 0 R >> >> >>\n"
            f"endobj\n".encode("utf-8")
        )
        # Content stream
        text = f"Page {p} / {page_count} - {title}"
        content = (
            f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET\n"
        ).encode("utf-8")
        objects.append(
            f"{content_obj_idx} 0 obj\n"
            f"<< /Length {len(content)} >>\n"
            f"stream\n".encode("utf-8")
            + content
            + b"endstream\n"
            b"endobj\n"
        )
    # Final: font object
    objects.append(
        f"{3 + 2 * page_count} 0 obj\n"
        f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        f"endobj\n".encode("utf-8")
    )
    return _render_pdf(objects)


def _render_pdf(objects: list[bytes]) -> bytes:
    """Concatenate ``objects`` into a valid PDF byte stream.

    The renderer rebuilds the xref table from the byte offsets
    of each object so the resulting stream is a valid PDF that
    a strict reader (like ``pypdf`` in a follow-up change) can
    open. The output starts with the magic header.
    """

    parts: list[bytes] = [_PDF_HEADER]
    offsets: list[int] = []
    cursor = len(_PDF_HEADER)
    for obj in objects:
        offsets.append(cursor)
        parts.append(obj)
        cursor += len(obj)
    # xref table
    xref_offset = cursor
    xref = (
        f"xref\n0 {len(objects) + 1}\n"
        f"0000000000 65535 f \n"
    ).encode("utf-8")
    for offset in offsets:
        xref += f"{offset:010d} 00000 n \n".encode("utf-8")
    parts.append(xref)
    # trailer
    trailer = (
        f"trailer\n"
        f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n"
        f"{xref_offset}\n"
        f"%%EOF\n"
    ).encode("utf-8")
    parts.append(trailer)
    return b"".join(parts)


def write_fixtures(
    out_dir: Path,
    *,
    sizes: tuple[int, ...] = (10, 100, 600),
    title: str = "ProjectExpert v0.8 generated fixture",
) -> dict:
    """Write the (size).pdf fixtures and a manifest.json under ``out_dir``.

    Returns the manifest payload so the caller can record the
    fixture in the eval report.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    fixtures: list[dict] = []
    for size in sizes:
        pdf_path = out_dir / f"{size}-page.pdf"
        pdf_path.write_bytes(build_pdf(page_count=size, title=title))
        fixtures.append({
            "filename": pdf_path.name,
            "size_bytes": pdf_path.stat().st_size,
            "page_count": size,
            "tier_eligible": 2,
        })
    manifest = {
        "schema_version": "1",
        "corpus": "generated-pdf",
        "generated_at": "2026-10-15",
        "tier_default": 2,
        "title": title,
        "fixtures": fixtures,
        "chunk_anchors": {
            "pdf-chunk-10-constraints-table": {
                "page": 4,
                "kind": "table",
                "ground_truth_query": "generated-pdf-table-constraints",
            },
            "pdf-chunk-10-constraints-table-header": {
                "page": 4,
                "kind": "table-header",
                "ground_truth_query": "generated-pdf-table-constraints",
            },
            "pdf-chunk-100-arch-figure": {
                "page": 7,
                "kind": "figure",
                "ground_truth_query": "generated-pdf-figure-architecture",
            },
            "pdf-chunk-100-arch-figure-caption": {
                "page": 7,
                "kind": "figure-caption",
                "ground_truth_query": "generated-pdf-figure-architecture",
            },
            "pdf-chunk-600-toc": {
                "page": 1,
                "kind": "toc",
                "ground_truth_query": "generated-pdf-600-page-toc",
            },
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the v0.8 Tier-2 generated-pdf corpus fixtures "
            "(10 / 100 / 600-page minimal PDFs) under the given "
            "output directory."
        ),
    )
    parser.add_argument(
        "--out", type=Path,
        default=Path("evals/corpus/generated-pdf"),
        help="output directory (default: evals/corpus/generated-pdf)",
    )
    parser.add_argument(
        "--sizes", type=int, nargs="+", default=[10, 100, 600],
        help="page counts to generate (default: 10 100 600)",
    )
    parser.add_argument(
        "--title", default="ProjectExpert v0.8 generated fixture",
        help="title embedded in every page",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = write_fixtures(
        args.out, sizes=tuple(args.sizes), title=args.title,
    )
    print(json.dumps(manifest, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())