"""Golden query loader for the v0.8 Tier-3 evaluation command.

Package J of the v0.8 refinement (``improve-ingestion-retrieval-
local-models``) ships a Tier-3 retrieval evaluation command
backed by ``evals/corpus/golden_queries.yaml``. Each entry
pairs a query string with the canonical ground truth chunk
ids the multi-stage retrieval pipeline is expected to surface.

The YAML loader tries PyYAML first (the project already has
PyYAML in the ``yaml`` optional dependency group); when PyYAML
is unavailable the loader raises a clear
:class:`GoldenQueryError` so the operator knows which
dependency to install. A minimal YAML subset parser is not
viable here because the schema has nested mappings and lists
(top-level ``queries:`` list of entries with structured
``ground_truth:`` maps and ``tags:`` arrays).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


__all__ = [
    "DEFAULT_GOLDEN_QUERIES_PATH",
    "GoldenQuery",
    "GoldenQueryError",
    "load_golden_queries",
]


DEFAULT_GOLDEN_QUERIES_PATH = Path(
    "evals/corpus/golden_queries.yaml",
)


@dataclass(frozen=True)
class GoldenQuery:
    """One labelled retrieval query from the golden query set.

    The ``id`` is the operator-facing name (also the key the
    eval report table uses); ``corpus`` names the sub-corpus
    the eval command resolves at run time;
    ``ground_truth_chunk_ids`` is the chunk-id set the
    pipeline is expected to surface;
    ``protected_chunk_ids`` is the subset that MUST survive
    the protected path (engineering identifiers, quoted
    phrases, target symbols); ``tags`` drive the per-tag
    breakdown in the eval report; ``tier`` is the lowest
    evaluation tier that exercises this query.
    """

    id: str
    corpus: str
    text: str
    ground_truth_chunk_ids: tuple[str, ...]
    protected_chunk_ids: tuple[str, ...]
    tags: tuple[str, ...]
    tier: int


class GoldenQueryError(RuntimeError):
    """Raised when ``golden_queries.yaml`` cannot be loaded."""


def _yaml() -> Any:
    """Return the ``yaml`` module or raise :class:`GoldenQueryError`.

    The project already uses PyYAML via the lazy ``_yaml()``
    pattern (see :mod:`pi_platform.core.canonical.okf` /
    :mod:`pi_platform.core.canonical.serializer`); this
    loader follows the same convention so an operator
    without PyYAML gets a single, clear error.
    """

    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise GoldenQueryError(
            "PyYAML is required to parse golden_queries.yaml; "
            "install the 'yaml' optional dependency group "
            "(pip install '.[yaml]') or convert the query set "
            "to JSON. The minimal YAML fallback in "
            "pi_platform.core.canonical.okf only supports "
            "flat key:value mappings and cannot represent "
            "the nested golden-query schema."
        ) from exc
    return yaml


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
    except ImportError:
        loaded = _parse_golden_yaml_fallback(text)
    if loaded is None:
        raise GoldenQueryError(
            f"golden_queries.yaml at {path!s} is empty"
        )
    if not isinstance(loaded, Mapping):
        raise GoldenQueryError(
            f"golden_queries.yaml at {path!s} must be a YAML "
            f"mapping at the top level, got {type(loaded).__name__}"
        )
    return loaded


def _parse_golden_yaml_fallback(text: str) -> Mapping[str, Any]:
    """Stdlib-only fallback parser for ``evals/corpus/golden_queries.yaml``."""
    result: dict[str, Any] = {"queries": []}
    current_q: dict[str, Any] | None = None
    in_gt = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0 and ":" in stripped:
            key, _, val = stripped.partition(":")
            if key.strip() != "queries":
                result[key.strip()] = val.strip().strip('"').strip("'")
            continue
        if stripped.startswith("- id:"):
            _, _, val = stripped.partition(":")
            current_q = {"id": val.strip().strip('"').strip("'"), "ground_truth": {}}
            result["queries"].append(current_q)
            in_gt = False
            continue
        if current_q is None:
            continue
        if stripped == "ground_truth:":
            in_gt = True
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            k = key.strip()
            v = val.strip()
            if in_gt and indent >= 6:
                current_q["ground_truth"][k] = json.loads(v) if v.startswith("[") else v
            else:
                in_gt = False
                if v.startswith("["):
                    current_q[k] = json.loads(v)
                elif k == "tier":
                    current_q[k] = int(v)
                else:
                    current_q[k] = v.strip('"').strip("'")
    return result


def _as_str_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, (list, tuple)):
        raise GoldenQueryError(
            f"{field_name} must be a list of strings, got "
            f"{type(value).__name__}"
        )
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise GoldenQueryError(
                f"{field_name} must contain only strings, got "
                f"{type(item).__name__}"
            )
        out.append(item)
    return tuple(out)


def parse_golden_queries(
    payload: Mapping[str, Any],
    *,
    source_path: str = "<memory>",
) -> tuple[GoldenQuery, ...]:
    """Parse an already-loaded YAML mapping into GoldenQuery rows.

    The function is exposed separately from
    :func:`load_golden_queries` so unit tests can pass a
    pre-built mapping without touching the file system.
    """

    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, (list, tuple)):
        raise GoldenQueryError(
            f"golden_queries.yaml at {source_path} must define a "
            f"'queries' list, got {type(raw_queries).__name__}"
        )
    out: list[GoldenQuery] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_queries):
        if not isinstance(raw, Mapping):
            raise GoldenQueryError(
                f"query entry #{index} in {source_path} must be a "
                f"mapping, got {type(raw).__name__}"
            )
        qid = str(raw.get("id") or "").strip()
        if not qid:
            raise GoldenQueryError(
                f"query entry #{index} in {source_path} is missing "
                f"a non-empty 'id'"
            )
        if qid in seen_ids:
            raise GoldenQueryError(
                f"duplicate query id {qid!r} in {source_path}"
            )
        seen_ids.add(qid)
        text = str(raw.get("text") or "").strip()
        if not text:
            raise GoldenQueryError(
                f"query {qid!r} has no 'text'"
            )
        corpus = str(raw.get("corpus") or "").strip()
        if not corpus:
            raise GoldenQueryError(
                f"query {qid!r} has no 'corpus'"
            )
        gt = raw.get("ground_truth") or {}
        if not isinstance(gt, Mapping):
            raise GoldenQueryError(
                f"query {qid!r}.ground_truth must be a mapping"
            )
        chunk_ids = _as_str_tuple(
            gt.get("chunk_ids"), field_name=f"{qid}.ground_truth.chunk_ids",
        )
        protected = _as_str_tuple(
            gt.get("protected"),
            field_name=f"{qid}.ground_truth.protected",
        )
        tags = _as_str_tuple(raw.get("tags"), field_name=f"{qid}.tags")
        try:
            tier = int(raw.get("tier", 3))
        except (TypeError, ValueError) as exc:
            raise GoldenQueryError(
                f"query {qid!r}.tier must be an integer"
            ) from exc
        out.append(GoldenQuery(
            id=qid, corpus=corpus, text=text,
            ground_truth_chunk_ids=chunk_ids,
            protected_chunk_ids=protected,
            tags=tags, tier=tier,
        ))
    return tuple(out)


def load_golden_queries(
    path: Path | os.PathLike[str] = DEFAULT_GOLDEN_QUERIES_PATH,
) -> tuple[GoldenQuery, ...]:
    """Load the golden query set from ``path``.

    The default path is the in-tree
    ``evals/corpus/golden_queries.yaml``; an operator can
    pass ``tmp/local/evals/golden_queries.yaml`` for a
    confidential corpus per plan §28 J5.
    """

    resolved = Path(path)
    if not resolved.exists():
        raise GoldenQueryError(
            f"golden query set not found at {resolved!s}"
        )
    payload = _load_yaml_mapping(resolved)
    return parse_golden_queries(payload, source_path=str(resolved))


def load_golden_queries_from_json(
    path: Path | os.PathLike[str],
) -> tuple[GoldenQuery, ...]:
    """Variant of :func:`load_golden_queries` for JSON inputs.

    Operators who cannot install PyYAML can convert
    ``golden_queries.yaml`` to a JSON document with the same
    schema; this helper parses the JSON form.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise GoldenQueryError(
            f"golden query set at {path!s} must be a JSON object"
        )
    return parse_golden_queries(payload, source_path=str(path))


def collect_corpora(queries: Iterable[GoldenQuery]) -> set[str]:
    """Return the set of sub-corpus names referenced by ``queries``."""
    return {q.corpus for q in queries}
