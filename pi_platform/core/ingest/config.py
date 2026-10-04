"""Load ingestion configuration without making optional PyYAML a core prerequisite."""

import json
from pathlib import Path


def load_ingest_config(path):
    path = Path(path)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError:
        # Mapping-only YAML subset covers init-project defaults and policy maps.
        # More complex lists must use JSON or the optional YAML adapter.
        root = {}
        stack = [(-1, root)]
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped == "---":
                continue
            if stripped.startswith("-"):
                # Ignore unrelated licensing lists; ingest list configuration is rejected.
                if any("domainRules" in m for _, m in stack):
                    raise ValueError(
                        "domainRules lists require optional PyYAML or JSON config"
                    )
                continue
            indent = len(line) - len(line.lstrip())
            key, sep, value = stripped.partition(":")
            if not sep:
                raise ValueError("configuration requires YAML mappings")
            while stack[-1][0] >= indent:
                stack.pop()
            key = key.strip("\"'")
            value = value.strip()
            parent = stack[-1][1]
            if not value:
                parent[key] = {}
                stack.append((indent, parent[key]))
                continue
            value = value.strip("\"'")
            if value.lower() in ("true", "false"):
                value = value.lower() == "true"
            elif value.isdigit():
                value = int(value)
            parent[key] = value
        return root
    else:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError("project context must be a mapping")
        return data
