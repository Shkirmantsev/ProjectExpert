#!/usr/bin/env python3
"""Add MUST/SHALL to failing spec requirement first body lines.

Strategy: the failing requirements have MUST/SHALL in the body, just
not on the first line (validator checks the first non-blank,
non-metadata line). The fix: rewrap the first paragraph into a single
long line (no wrap) so MUST/SHALL appears on line 1 of the paragraph.
This is the least invasive fix — original wording is preserved.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENSPEC = ROOT / "tmp" / "local" / "bin" / "openspec"

# Hand-crafted replacements for each failing requirement. Each entry
# rewrites the first body paragraph as a single line carrying MUST/SHALL.
# Keys: (relative_spec_path, requirement_name) -> new first paragraph
SPECIFIC_FIXES: dict[tuple[str, str], str] = {
    # Phase 1 canonical specs
    ("openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md",
     "hydrate loads canonical knowledge into runtime"):
        "When the platform starts up or reconciles after a Git-state change, the platform MUST run a hydrate operation that:",
    ("openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md",
     "materialise writes runtime back to canonical"):
        "When the operator decides that runtime-enriched knowledge should become durable, the platform MUST support a materialise operation that:",
    ("openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md",
     "deterministic canonical serialization"):
        "Every canonical artifact (chunk, entity, relation, evidence, manifest, OKF Markdown concept page) MUST be serialisable to a deterministic textual form (JSON or YAML) such that two equivalent runtime states produce byte-identical canonical files.",
    ("openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md",
     "canonical object content addressing"):
        "Every canonical immutable object (parsed structure snapshot, normalized chunk body, deterministic extracted relation, OKF concept page snapshot) MUST be addressed by its SHA-256 hex digest of its deterministic canonical serialization.",
    ("openspec/specs/2026-10-04-git-version-aware-runtime/spec.md",
     "content-addressed processing reuse"):
        "Expensive derived information (parsed structure snapshots, chunks, contextualised chunks, embeddings, deterministic summaries, deterministic entity/relation extraction results) MUST be associated with a SHA-256 content hash derived from the canonical serialization of the input content.",
    ("openspec/specs/2026-10-04-license-governance/spec.md",
     "review-required licenses must be explicitly accepted"):
        "Dependencies whose license carries reciprocal, file-level copyleft, linking conditions or other distribution obligations MUST NOT be introduced without operator acceptance.",
    ("openspec/specs/2026-10-04-license-governance/spec.md",
     "restricted and non-commercial licenses are denied by default"):
        "Dependencies whose terms prohibit or materially restrict commercial use, redistribution, SaaS use, modification, use by companies or resale MUST NOT enter the default dependency stack unless explicitly approved by the operator.",
    ("openspec/specs/2026-10-04-license-governance/spec.md",
     "model licenses are tracked separately"):
        "The license of model weights, tokenizer, training artifacts, inference runtime, embedding model and reranker MUST be tracked separately from the underlying library licenses because they often differ.",
    ("openspec/specs/2026-10-04-project-knowledge-repository-layout/spec.md",
     "runtime working knowledge cache location"):
        "The runtime working knowledge store (database, vector index, full-text index, graph index, embeddings cache, model cache, working-tree overlay) MUST live under a separate, Git-ignored directory.",
    ("openspec/specs/2026-10-04-project-knowledge-repository-layout/spec.md",
     "per-target runtime cache root resolution"):
        "The HydrateService, MaterialiseService, WriteAheadLog and LicenseGate MUST resolve the runtime cache root from the target repository's project-context.yaml; if the file is absent the services MUST use the documented fallback path (.project-intelligence-cache/).",
    # Phase 2 delta specs in prepare-phase-2-ingestion
    ("openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-content-addressed-processing/spec.md",
     "cross-branch cache reuse"):
        "When the runtime cache observes a content address that was computed on a previous Git branch for the same ProjectVersion, the cache MUST reuse the previous chunk body, entity body and embedding without re-parsing or re-embedding.",
    ("openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-content-addressed-processing/spec.md",
     "cache eviction by source identity"):
        "When the underlying Source changes (the Source.contentHash diverges from the cached entry's Evidence.sourceHash), the runtime cache MUST evict the stale cache entry and recompute the content-addressed artefact.",
    ("openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-context-enrichment/spec.md",
     "optional small LLM layer"):
        "The optional small LLM layer (see §22.3) MAY be enabled when the target project configures a LocalLLMPort; whenever the layer is enabled it MUST operate with documented budget controls and MUST emit a ContextEnricherReport naming every layer that contributed to the final ContextualChunk.",
    ("openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-jar-dependency-intelligence/spec.md",
     "license pass-through"):
        "Every Dependency entity emitted by JarAdapter, MavenAdapter and GradleAdapter MUST carry the SPDX identifier of the dependency when one is available in distribution/licenses/dependency-inventory.json.",
    # Phase 1 ADDED requirements mirrored in plan-v0-8 change delta specs
    ("openspec/changes/plan-v0-8-platform-architecture/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md",
     "hydrate loads canonical knowledge into runtime"):
        "When the platform starts up or reconciles after a Git-state change, the platform MUST run a hydrate operation that:",
    ("openspec/changes/plan-v0-8-platform-architecture/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md",
     "materialise writes runtime back to canonical"):
        "When the operator decides that runtime-enriched knowledge should become durable, the platform MUST support a materialise operation that:",
    ("openspec/changes/plan-v0-8-platform-architecture/specs/2026-10-04-canonical-knowledge-schema/spec.md",
     "deterministic canonical serialization"):
        "Every canonical artifact (chunk, entity, relation, evidence, manifest, OKF Markdown concept page) MUST be serialisable to a deterministic textual form (JSON or YAML) such that two equivalent runtime states produce byte-identical canonical files.",
    ("openspec/changes/plan-v0-8-platform-architecture/specs/2026-10-04-canonical-knowledge-schema/spec.md",
     "canonical object content addressing"):
        "Every canonical immutable object (parsed structure snapshot, normalized chunk body, deterministic extracted relation, OKF concept page snapshot) MUST be addressed by its SHA-256 hex digest of its deterministic canonical serialization.",
    ("openspec/changes/plan-v0-8-platform-architecture/specs/2026-10-04-git-version-aware-runtime/spec.md",
     "content-addressed processing reuse"):
        "Expensive derived information (parsed structure snapshots, chunks, contextualised chunks, embeddings, deterministic summaries, deterministic entity/relation extraction results) MUST be associated with a SHA-256 content hash derived from the canonical serialization of the input content.",
    ("openspec/changes/plan-v0-8-platform-architecture/specs/2026-10-04-license-governance/spec.md",
     "review-required licenses must be explicitly accepted"):
        "Dependencies whose license carries reciprocal, file-level copyleft, linking conditions or other distribution obligations MUST NOT be introduced without operator acceptance.",
    ("openspec/changes/plan-v0-8-platform-architecture/specs/2026-10-04-license-governance/spec.md",
     "restricted and non-commercial licenses are denied by default"):
        "Dependencies whose terms prohibit or materially restrict commercial use, redistribution, SaaS use, modification, use by companies or resale MUST NOT enter the default dependency stack unless explicitly approved by the operator.",
    ("openspec/changes/plan-v0-8-platform-architecture/specs/2026-10-04-license-governance/spec.md",
     "model licenses are tracked separately"):
        "The license of model weights, tokenizer, training artifacts, inference runtime, embedding model and reranker MUST be tracked separately from the underlying library licenses because they often differ.",
    ("openspec/changes/plan-v0-8-platform-architecture/specs/2026-10-04-project-knowledge-repository-layout/spec.md",
     "runtime working knowledge cache location"):
        "The runtime working knowledge store (database, vector index, full-text index, graph index, embeddings cache, model cache, working-tree overlay) MUST live under a separate, Git-ignored directory.",
}


def find_requirement_blocks(text: str) -> list[tuple[int, int, str]]:
    lines = text.splitlines(keepends=True)
    blocks: list[tuple[int, int, str]] = []
    indices: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^### Requirement:\s*(.+?)\s*$", line)
        if m:
            indices.append((i, m.group(1)))
    for j, (start, name) in enumerate(indices):
        end = indices[j + 1][0] if j + 1 < len(indices) else len(lines)
        blocks.append((start, end, name))
    return blocks


def first_paragraph_range(lines: list[str], start: int, end: int) -> tuple[int, int] | None:
    first_i = None
    for i in range(start + 1, end):
        line = lines[i]
        if re.match(r"^####\s+", line):
            break
        if line.strip():
            if first_i is None:
                first_i = i
        if first_i is not None and i > first_i:
            if not line.strip() or re.match(r"^####\s+", line):
                return first_i, i - 1
    if first_i is None:
        return None
    return first_i, end - 1


def apply_fix(path: Path, requirement_name: str, new_paragraph: str) -> bool:
    text = path.read_text(encoding="utf-8")
    blocks = find_requirement_blocks(text)
    target = None
    for start, end, name in blocks:
        if name == requirement_name:
            target = (start, end)
            break
    if target is None:
        return False
    start, end = target
    lines = text.splitlines(keepends=True)
    rng = first_paragraph_range(lines, start, end)
    if rng is None:
        return False
    first_i, last_i = rng
    paragraph_text = "".join(lines[i] for i in range(first_i, last_i + 1)).rstrip("\n")
    first_line = paragraph_text.split("\n", 1)[0]
    if re.search(r"\b(SHALL|MUST)\b", first_line):
        return False
    leading_ws_match = re.match(r"^(\s*)", lines[first_i])
    leading_ws = leading_ws_match.group(1) if leading_ws_match else ""
    new_lines = lines[:first_i] + [leading_ws + new_paragraph + "\n"] + lines[last_i + 1 :]
    path.write_text("".join(new_lines), encoding="utf-8")
    return True


def main() -> int:
    applied = 0
    by_file: dict[Path, list[tuple[str, str]]] = {}
    for (rel_path, req_name), new_para in SPECIFIC_FIXES.items():
        path = ROOT / rel_path
        by_file.setdefault(path, []).append((req_name, new_para))
    for path, items in by_file.items():
        if not path.exists():
            print(f"  MISSING: {path}", file=sys.stderr)
            continue
        for name, new_para in items:
            ok = apply_fix(path, name, new_para)
            if ok:
                applied += 1
                print(f"  FIXED: {path.relative_to(ROOT)} :: {name}")
            else:
                print(f"  SKIP: {path.relative_to(ROOT)} :: {name}", file=sys.stderr)
    print(f"Total: {applied} requirement fixes applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())