"""Static analysis of Node source files.

The parser is **tree-sitter** with the maintained JavaScript and
TypeScript grammars:

============================  ==========  ==========================
package                       license     role
============================  ==========  ==========================
``tree-sitter``               MIT         parser runtime
``tree-sitter-javascript``    MIT         ECMAScript grammar
``tree-sitter-typescript``    MIT         TypeScript grammar
============================  ==========  ==========================

They are **optional** dependencies. When they are not installed the
caller receives a capability diagnostic and partial manifest evidence;
the deployment never fails to start because of a missing parser, and a
regular expression is never substituted for a real parse.

The extraction is read-only and side-effect free: it never evaluates the
module, never resolves an import and never runs a build script.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "PARSER_VERSION",
    "NodeSymbol",
    "NodeImport",
    "NodeSourceAnalysis",
    "parser_available",
    "parser_status",
    "analyse_source",
    "SUPPORTED_SUFFIXES",
]

PARSER_VERSION = "node-tree-sitter-1"

#: Source suffixes this analyser understands.
SUPPORTED_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts")

_PARSER_CACHE: dict[str, Any] = {}


@dataclass(frozen=True)
class NodeSymbol:
    """One exported or top-level symbol."""

    name: str
    kind: str
    line: int
    exported: bool
    declaration: bool


@dataclass(frozen=True)
class NodeImport:
    """One import or re-export of another module."""

    specifier: str
    line: int
    kind: str  # "import" | "reexport" | "dynamic-import"


@dataclass(frozen=True)
class NodeSourceAnalysis:
    """The result of analysing one source file."""

    path: str
    symbols: tuple[NodeSymbol, ...] = ()
    imports: tuple[NodeImport, ...] = ()
    warnings: tuple[str, ...] = ()


def _load_parser(suffix: str):
    """Return a configured parser for ``suffix`` or ``None``."""

    if suffix in _PARSER_CACHE:
        return _PARSER_CACHE[suffix]
    try:
        from tree_sitter import Language, Parser
    except ImportError:
        _PARSER_CACHE[suffix] = None
        return None
    try:
        if suffix in {".ts", ".mts", ".cts"}:
            import tree_sitter_typescript as ts_typescript
            language = Language(ts_typescript.language_typescript())
        elif suffix == ".tsx":
            import tree_sitter_typescript as ts_typescript
            language = Language(ts_typescript.language_tsx())
        else:
            import tree_sitter_javascript as ts_javascript
            language = Language(ts_javascript.language())
    except ImportError:
        _PARSER_CACHE[suffix] = None
        return None
    parser = Parser(language)
    _PARSER_CACHE[suffix] = parser
    return parser


def parser_available() -> bool:
    """Report whether the static Node parser is installed."""

    return _load_parser(".js") is not None


def parser_status() -> dict:
    """Describe the parser installation for capability discovery."""

    available = parser_available()
    return {
        "parser": "tree-sitter",
        "grammars": ["tree-sitter-javascript", "tree-sitter-typescript"],
        "license": "MIT",
        "available": available,
        "parserVersion": PARSER_VERSION,
        "diagnostic": None if available else (
            "the tree-sitter Node grammars are not installed; Node source "
            "symbols are unavailable and the manifest evidence stays partial"
        ),
    }


def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _string_value(node, source: bytes) -> Optional[str]:
    if node is None:
        return None
    raw = _text(node, source)
    if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
        return raw[1:-1]
    return raw


def _declaration_symbols(node, source: bytes, *, exported: bool) -> list[NodeSymbol]:
    symbols: list[NodeSymbol] = []
    kind_map = {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
        "abstract_class_declaration": "class",
        "function_signature": "function",
        "method_signature": "method",
    }
    kind = kind_map.get(node.type)
    name_node = node.child_by_field_name("name")
    if kind and name_node is not None:
        symbols.append(NodeSymbol(
            name=_text(name_node, source),
            kind=kind,
            line=node.start_point[0] + 1,
            exported=exported,
            declaration=True,
        ))
        return symbols
    if node.type in {"lexical_declaration", "variable_declaration"}:
        for child in node.named_children:
            if child.type != "variable_declarator":
                continue
            target = child.child_by_field_name("name")
            if target is None:
                continue
            value = child.child_by_field_name("value")
            inferred = "variable"
            if value is not None and value.type in {
                "arrow_function", "function_expression", "function",
                "generator_function",
            }:
                inferred = "function"
            elif value is not None and value.type == "class":
                inferred = "class"
            symbols.append(NodeSymbol(
                name=_text(target, source),
                kind=inferred,
                line=child.start_point[0] + 1,
                exported=exported,
                declaration=True,
            ))
    return symbols


def analyse_source(path: Path) -> NodeSourceAnalysis:
    """Analyse one Node source file.

    A missing parser is reported as a warning on the analysis, not as
    an exception: the caller can still use the manifest evidence.
    """

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return NodeSourceAnalysis(path=str(path), warnings=(
            f"unsupported source suffix {suffix!r}",))
    parser = _load_parser(suffix)
    if parser is None:
        return NodeSourceAnalysis(path=str(path), warnings=(
            "the tree-sitter Node grammars are not installed",))
    try:
        source = path.read_bytes()
    except OSError as exc:
        return NodeSourceAnalysis(path=str(path), warnings=(f"cannot read source: {exc}",))

    tree = parser.parse(source)
    symbols: list[NodeSymbol] = []
    imports: list[NodeImport] = []

    def visit(node, handled: frozenset = frozenset()) -> None:
        node_type = node.type
        skip: set[tuple[int, int]] = set()
        if node_type == "import_statement":
            specifier = _string_value(node.child_by_field_name("source"), source)
            if specifier:
                imports.append(NodeImport(specifier=specifier,
                                          line=node.start_point[0] + 1,
                                          kind="import"))
        elif node_type == "export_statement":
            specifier = _string_value(node.child_by_field_name("source"), source)
            if specifier:
                imports.append(NodeImport(specifier=specifier,
                                          line=node.start_point[0] + 1,
                                          kind="reexport"))
            declaration = node.child_by_field_name("declaration")
            if declaration is not None:
                symbols.extend(_declaration_symbols(declaration, source, exported=True))
                # The declaration is reported through the export; it must
                # not be counted a second time as a plain declaration.
                skip.add((declaration.start_byte, declaration.end_byte))
        elif node_type in {"lexical_declaration", "variable_declaration",
                           "function_declaration", "class_declaration",
                           "interface_declaration", "type_alias_declaration",
                           "enum_declaration"}:
            symbols.extend(_declaration_symbols(node, source, exported=False))
        elif node_type == "call_expression":
            text = _text(node, source)
            if text.startswith("import("):
                arguments = node.child_by_field_name("arguments")
                specifier = _string_value(arguments, source)
                if specifier and specifier[:1] in ("'", '"'):
                    imports.append(NodeImport(
                        specifier=specifier[1:-1],
                        line=node.start_point[0] + 1,
                        kind="dynamic-import"))
        for child in node.named_children:
            if (child.start_byte, child.end_byte) in skip:
                continue
            visit(child)

    visit(tree.root_node)

    symbols.sort(key=lambda item: (item.line, item.name))
    imports.sort(key=lambda item: (item.line, item.specifier))
    return NodeSourceAnalysis(path=str(path), symbols=tuple(symbols),
                              imports=tuple(imports))
