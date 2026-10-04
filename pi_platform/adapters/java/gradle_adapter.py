"""Declared Groovy/Kotlin dependency extraction; unresolved expressions stay visible."""

import re
from pathlib import Path
from pi_platform.core.ingest.records import read_text
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterPort,
    SourceContentFamily,
)
from .dependencies import BuildTreeMixin, dependency_records


class GradleAdapter(BuildTreeMixin, SourceAdapterPort):
    family = SourceContentFamily.GRADLE_BUILD
    binary, build_name = "gradle", "build.gradle"

    def __init__(self, inventory_path=None):
        self.inventory_path = inventory_path

    def parse(self, source, context=None):
        text = read_text(source.uri)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
        rows = []
        for match in re.finditer(
            r'\b(\w+)\s*\(?\s*[\'"]([^\'"\s]+):([^\'"\s]+):([^\'"]+)[\'"]', text
        ):
            config, group, artifact, version = match.groups()
            rows.append(
                {
                    "groupId": group,
                    "artifactId": artifact,
                    "version": version,
                    "scope": "test" if config.lower().startswith("test") else config,
                    "type": "jar",
                    "classifier": "",
                }
            )
        for match in re.finditer(
            r'\b(\w+)\s+group\s*:\s*[\'"]([^\'"]+)[\'"]\s*,\s*name\s*:\s*[\'"]([^\'"]+)[\'"]\s*,\s*version\s*:\s*[\'"]([^\'"]+)[\'"]',
            text,
        ):
            config, group, artifact, version = match.groups()
            rows.append(
                {
                    "groupId": group,
                    "artifactId": artifact,
                    "version": version,
                    "scope": "test" if config.lower().startswith("test") else config,
                    "type": "jar",
                    "classifier": "",
                }
            )
        return dependency_records(
            source,
            rows,
            Path(source.uri).parent.name,
            "gradle-declarations-1",
            self.inventory_path,
        )
