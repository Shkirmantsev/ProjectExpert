"""Dependency records with SPDX pass-through and explicit partial-tree advisories."""

import logging
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from pi_platform.core.canonical.content_address import (
    content_address,
    content_address_bytes,
)
from pi_platform.core.canonical.value_types import (
    Entity,
    Evidence,
    KnowledgeState,
    Relation,
    Source,
)
from pi_platform.core.ingest.records import document_result
from pi_platform.core.licensing import DependencyInventory
from pi_platform.ports.ingest.source_adapter import SourceAdapterError

log = logging.getLogger(__name__)
INVENTORY = (
    Path(__file__).resolve().parents[3]
    / "distribution/licenses/dependency-inventory.json"
)


def dependency_records(source, rows, module_name, parser_version, inventory_path=None):
    inventory = {
        d.name: d for d in DependencyInventory(Path(inventory_path or INVENTORY)).load()
    }
    result = document_result(
        source,
        [
            (
                module_name,
                1,
                "\n".join(
                    f'{r["groupId"]}:{r["artifactId"]}:{r["version"]}' for r in rows
                ),
                {},
            )
        ],
        source.family,
        parser_version,
    )
    module_id = content_address({"source": source.id, "module": module_name})
    module = Entity(
        module_id,
        "MavenModule" if source.family == "maven_pom" else "Module",
        module_name,
        metadata=result.document.metadata,
        knowledgeState=KnowledgeState.VERIFIED,
    )
    entities, relations, evidence = [module], [], []
    for row in rows:
        coordinate = f'{row["groupId"]}:{row["artifactId"]}'
        dep = inventory.get(coordinate)
        state = (
            KnowledgeState.VERIFIED if dep and dep.spdx else KnowledgeState.ASSUMPTION
        )
        attrs = {**row, "spdx": dep.spdx if dep else None}
        ev = Evidence(
            state,
            parser_version,
            source.contentHash,
            rationale=(
                None if dep else "dependency SPDX unavailable; license review required"
            ),
        )
        eid = content_address(
            {
                "coordinate": coordinate,
                "version": row["version"],
                "scope": row.get("scope", "compile"),
            }
        )
        meta = replace(
            result.document.metadata,
            extensions={
                **attrs,
                "pi_evidence": {
                    "knowledgeState": state.value,
                    "parserVersion": parser_version,
                    "sourceHash": source.contentHash,
                },
            },
        )
        entities.append(
            Entity(eid, "Dependency", coordinate, metadata=meta, knowledgeState=state)
        )
        evidence.append(ev)
        for a, b, f in (
            (eid, module_id, "PART_OF"),
            (module_id, eid, "DEPENDSON"),
            (eid, module_id, "DECLARED_BY"),
        ):
            relations.append(Relation(a, b, f, evidence=(ev,), knowledgeState=state))
    return replace(
        result,
        entities=tuple(entities),
        relations=tuple(relations),
        evidence=tuple(evidence),
    )


class BuildTreeMixin:
    def resolve_tree(self, project_root, binary=None):
        root = Path(project_root)
        source_path = root / self.build_name
        if not source_path.exists() and self.build_name == "build.gradle":
            source_path = root / "build.gradle.kts"
        data = source_path.read_bytes()
        source = Source(
            content_address({"path": str(source_path)}),
            str(source_path),
            self.family.value,
            content_address_bytes(data),
        )
        declared = self.parse(source)
        command = binary or self.binary
        if not shutil.which(str(command)):
            log.warning(
                "transient advisory: missing %s; %d declared dependencies only",
                command,
                sum(e.family == "Dependency" for e in declared.entities),
            )
            return tuple(r for r in declared.relations if r.family == "DEPENDSON")
        args = (
            ["dependency:tree", "-DoutputType=text", "-Dstyle.color=never"]
            if self.binary == "mvn"
            else ["dependencies", "--console=plain", "--no-daemon"]
        )
        try:
            output = subprocess.run(
                [str(command), *args],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SourceAdapterError(
                f"{command} dependency tree failed: {exc}"
            ) from exc
        return self._parse_tree(output.stdout, declared)

    def _parse_tree(self, text, declared):
        import re

        module = declared.entities[0].id
        stack = [(0, module)]
        relations = []
        for line in text.splitlines():
            line = re.sub(r"^\[INFO\]\s?", "", line)
            marker = re.search(r"(\+-|\\-|\+---|\\---)", line)
            if not marker:
                continue
            match = re.search(r"([\w.\-]+):([\w.\-]+):([^\s]+)", line[marker.end() :])
            if not match:
                continue
            group, artifact, tail = match.groups()
            bits = tail.split(":")
            version = bits[-2] if len(bits) >= 3 else bits[0]
            override = re.search(r"->\s*([^\s]+)", line)
            if override:
                version = override[1]
            eid = content_address(
                {
                    "coordinate": f"{group}:{artifact}",
                    "version": version,
                    "scope": "compile",
                }
            )
            depth = marker.start()
            while len(stack) > 1 and stack[-1][0] >= depth:
                stack.pop()
            relations.append(
                Relation(
                    stack[-1][1],
                    eid,
                    "DEPENDSON",
                    knowledgeState=KnowledgeState.INFERRED,
                )
            )
            stack.append((depth, eid))
        return tuple(relations) or tuple(
            r for r in declared.relations if r.family == "DEPENDSON"
        )
