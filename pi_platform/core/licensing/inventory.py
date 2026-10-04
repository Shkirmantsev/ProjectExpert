"""Dependency and model-license inventories."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence

from ...core.canonical import canonical_dump_json, canonical_load_json
from ...ports import Dependency, DependencyInventoryPort, ModelLicense, ModelLicenseInventoryPort

__all__ = [
    "DEFAULT_DEPENDENCY_INVENTORY_PATH",
    "DEFAULT_MODEL_LICENSE_PATH",
    "DependencyInventory",
    "ModelLicenseInventory",
]


DEFAULT_DEPENDENCY_INVENTORY_PATH = Path("distribution/licenses/dependency-inventory.json")
DEFAULT_MODEL_LICENSE_PATH = Path("distribution/licenses/model-licenses.json")


@dataclass(frozen=True)
class DependencyInventory(DependencyInventoryPort):
    path: Path

    def load(self, path: Optional[Path] = None) -> List[Dependency]:
        target = path or self.path
        if not target.is_file():
            return []
        body = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(body, Mapping):
            return []
        return [_dep_from_dict(entry) for entry in body.get("dependencies", [])]

    def save(self, dependencies: Iterable[Dependency], *,
             path: Optional[Path] = None) -> Path:
        target = path or self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"dependencies": [_dep_to_dict(d) for d in dependencies]}
        target.write_bytes(canonical_dump_json(payload))
        return target


@dataclass(frozen=True)
class ModelLicenseInventory(ModelLicenseInventoryPort):
    path: Path

    def load(self, path: Optional[Path] = None) -> List[ModelLicense]:
        target = path or self.path
        if not target.is_file():
            return []
        body = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(body, Mapping):
            return []
        return [
            ModelLicense(
                name=entry["name"],
                version=entry["version"],
                spdx=entry.get("spdx"),
                source=entry.get("source"),
            )
            for entry in body.get("models", [])
        ]

    def save(self, models: Iterable[ModelLicense], *,
             path: Optional[Path] = None) -> Path:
        target = path or self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"models": [
            {"name": m.name, "version": m.version,
             "spdx": m.spdx, "source": m.source}
            for m in models
        ]}
        target.write_bytes(canonical_dump_json(payload))
        return target


def _dep_to_dict(dep: Dependency) -> dict:
    return {
        "name": dep.name,
        "version": dep.version,
        "spdx": dep.spdx,
        "source": dep.source,
        "scope": dep.scope,
    }


def _dep_from_dict(entry: Mapping[str, object]) -> Dependency:
    return Dependency(
        name=str(entry["name"]),
        version=str(entry["version"]),
        spdx=entry.get("spdx"),  # type: ignore[arg-type]
        source=entry.get("source"),  # type: ignore[arg-type]
        scope=str(entry.get("scope", "runtime")),
    )


def stub_inventory() -> List[Dependency]:
    """Return the documented stub inventory produced by ``init-project``.

    The stub lists every Python standard-library module dependency as
    ``scope=system`` with SPDX ``NOASSERTION`` (per the
    ``license-governance`` spec) so the Phase 1 license gate does not
    block a fresh target repository.
    """

    return [
        Dependency(name="python", version="3.11", spdx="NOASSERTION",
                  source="https://www.python.org/", scope="system"),
        Dependency(name="python-stdlib", version="3.11", spdx="NOASSERTION",
                  source="https://docs.python.org/3/library/", scope="system"),
    ]