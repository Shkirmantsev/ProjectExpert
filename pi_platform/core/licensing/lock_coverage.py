"""Compare a fully pinned production lock to reviewed dependency identities."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ...ports import Dependency


def check_lock_coverage(lock_path: Path, dependencies: Iterable[Dependency]) -> list[str]:
    """Report missing or drifted exact coordinates; never infer license approval."""
    normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    reviewed = {(normalize(dep.name), dep.version) for dep in dependencies}
    requirements = []
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith(("#", "--")):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;\\]+)\s*(?:\\)?", text)
        if not match:
            raise ValueError(f"Production lock contains an unpinned or unsupported requirement: {text}")
        requirements.append((normalize(match.group(1)), match.group(2)))
    if not requirements:
        raise ValueError("Production lock contains no pinned dependencies")
    return [f"{name}=={version}: exact coordinate missing from reviewed inventory"
            for name, version in requirements if (name, version) not in reviewed]
