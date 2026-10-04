"""One-shot tree-sitter worker; only JSON crosses the process boundary."""

import json
import re
import sys
from importlib.metadata import version


def parse(source):
    from tree_sitter import Language, Parser
    import tree_sitter_java

    raw = source.encode("utf-8")
    tree = Parser(Language(tree_sitter_java.language())).parse(raw)
    if tree.root_node.has_error:
        raise ValueError("Java syntax errors in parser tree")
    entities = []

    def text(node):
        return raw[node.start_byte : node.end_byte].decode("utf-8") if node else ""

    def field(node, name):
        return text(node.child_by_field_name(name))

    package = next(
        (
            text(n).removeprefix("package ").rstrip(";").strip()
            for n in tree.root_node.named_children
            if n.type == "package_declaration"
        ),
        "",
    )
    if package:
        entities.append({"kind": "package", "name": package, "signature": package})
    kinds = {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "annotation_type_declaration": "annotation",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
        "field_declaration": "field",
        "method_invocation": "call",
    }

    def visit(node, parent=None):
        kind = kinds.get(node.type)
        owner = parent
        if kind:
            name = field(node, "name")
            if kind == "field":
                declarator = next(
                    (n for n in node.named_children if n.type == "variable_declarator"),
                    None,
                )
                name = field(declarator, "name") if declarator else ""
            modifiers = next(
                (n for n in node.named_children if n.type == "modifiers"), None
            )
            annotations = (
                [
                    text(n)
                    for n in modifiers.named_children
                    if n.type in ("annotation", "marker_annotation")
                ]
                if modifiers
                else []
            )
            body = node.child_by_field_name("body")
            signature = (
                raw[node.start_byte : body.start_byte if body else node.end_byte]
                .decode()
                .strip()
            )
            attrs = {
                "body": text(node),
                "packageName": package,
                "qualifiedName": f"{parent or package}.{name}".strip("."),
                "startByte": node.start_byte,
                "endByte": node.end_byte,
            }
            if kind in ("class", "interface", "enum"):
                attrs["extends"] = re.findall(
                    r"[\w.]+", field(node, "superclass").removeprefix("extends").strip()
                )
                attrs["implements"] = re.findall(
                    r"[\w.]+",
                    field(node, "interfaces").removeprefix("implements").strip(),
                )
            if kind == "field":
                attrs["type"] = field(node, "type")
            if kind == "call":
                attrs["object"] = field(node, "object")
            if name:
                entities.append(
                    {
                        "kind": kind,
                        "name": name,
                        "signature": signature,
                        "parent": parent,
                        "annotations": annotations,
                        "modifiers": re.findall(
                            r"\b(public|protected|private|static|final|abstract)\b",
                            text(modifiers),
                        ),
                        "line": node.start_point.row + 1,
                        "attributes": attrs,
                    }
                )
                if kind in ("class", "interface", "enum", "method", "constructor"):
                    owner = attrs["qualifiedName"]
        for child in node.named_children:
            visit(child, owner)

    visit(tree.root_node)
    return entities


def main():
    try:
        if "--version" in sys.argv:
            print(
                json.dumps(
                    {
                        "parser_version": "tree-sitter-java-"
                        + version("tree-sitter-java"),
                        "binding_version": version("tree-sitter"),
                    }
                )
            )
            return 0
        request = json.load(sys.stdin)
        print(
            json.dumps(
                {
                    "parser_version": "tree-sitter-java-" + version("tree-sitter-java"),
                    "entities": parse(request["source"]),
                }
            )
        )
        return 0
    except ImportError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 3
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
