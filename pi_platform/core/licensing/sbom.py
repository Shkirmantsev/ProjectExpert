"""SBOM and NOTICE emitter.

The Phase 1 emitter uses an SPDX-2.3-compatible JSON shape. The
NOTICE file lists every ``allow``-resolved dependency as a single
line ``<name>:<version> - SPDX:<license-id> - <source>``.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from pathlib import Path
from typing import Iterable, Mapping, Optional

from ...core.canonical import canonical_dump_json
from ...ports import Dependency
from .policy import LicensePolicy

__all__ = ["emit_spdx_sbom", "emit_notice_file",
           "DEFAULT_SBOM_PATH", "DEFAULT_NOTICE_PATH"]


DEFAULT_SBOM_PATH = Path("distribution/sbom/PROJECT-INTELLIGENCE.sbom.json")
DEFAULT_NOTICE_PATH = Path("distribution/sbom/NOTICE.txt")


def emit_spdx_sbom(dependencies: Iterable[Dependency],
                  *,
                  name: str = "project-intelligence-platform",
                  version: str = "0.1.0",
                  output_root: Path,
                  path: Optional[Path] = None) -> Path:
    """Write an SPDX-2.3-compatible SBOM to ``output_root / path``."""

    target = (output_root / (path or DEFAULT_SBOM_PATH)).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": f"SPDXRef-DOCUMENT-{uuid.uuid4().hex[:8]}",
        "name": name,
        "documentNamespace": f"https://project-intelligence.local/spdx/{uuid.uuid4().hex}",
        "creationInfo": {
            # SPDX 2.3 requires the trailing 'Z' UTC form.
            "created": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
                                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "creators": ["Tool: project-intelligence-platform-0.1.0"],
        },
        "packages": [_sbom_package(dep) for dep in dependencies],
    }
    target.write_bytes(canonical_dump_json(document))
    return target


def emit_notice_file(dependencies: Iterable[Dependency],
                     *,
                     output_root: Path,
                     path: Optional[Path] = None) -> Path:
    target = (output_root / (path or DEFAULT_NOTICE_PATH)).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    policy = LicensePolicy()
    lines = ["Project Intelligence Platform", "Copyright contributors.",
             "", "This distribution includes the following third-party "
             "software components:", ""]
    for dep in dependencies:
        decision, reason = policy.evaluate(dep)
        # The license-governance spec restricts the NOTICE file to
        # ``allow``-resolved dependencies; ``review`` deps belong in a
        # separate acceptance record; ``deny`` deps must not ship.
        if decision != "allow":
            continue
        spdx = (dep.spdx or "NOASSERTION").strip() or "NOASSERTION"
        source = dep.source or "NOASSERTION"
        lines.append(f"- {dep.name}:{dep.version} - SPDX:{spdx} - {source}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _sbom_package(dep: Dependency) -> dict:
    return {
        "SPDXID": f"SPDXRef-Package-{_safe_id(dep.name)}-{_safe_id(dep.version)}",
        "name": dep.name,
        "versionInfo": dep.version,
        "downloadLocation": dep.source or "NOASSERTION",
        "licenseConcluded": dep.spdx or "NOASSERTION",
        "licenseDeclared": dep.spdx or "NOASSERTION",
        "copyrightText": "NOASSERTION",
    }


def _safe_id(text: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in text)[:32]