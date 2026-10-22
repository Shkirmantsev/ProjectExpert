"""Tests for repository source discovery (open spec change PR 9).

Covers the ``repository-source-discovery-incremental`` spec delta:

* default include / exclude rules honor the documented lists;
* the discovered inventory records path, source family, content
  hash, parser version and (optionally) retrieval text hash;
* unchanged sources keep their ``retrieval_text_hash`` across
  runs;
* modified sources are classified as MODIFIED;
* removed sources are detectable via the path diff;
* family classification is stable across runs.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from pi_platform.core.ingest.repository_source_discovery import (
    DEFAULT_EXCLUDE_PATTERNS,
    DEFAULT_INCLUDE_PATTERNS,
    DEFAULT_PARSER_VERSION,
    RepositorySourceDiscovery,
    SOURCE_FAMILY_CONFIGURATION,
    SOURCE_FAMILY_DOCUMENTATION,
    SOURCE_FAMILY_OPENSPEC,
    SOURCE_FAMILY_SOURCE_CODE,
    SourceInventory,
    SourceInventoryEntry,
    classify_source_family,
)


def _make_tree(root: Path) -> None:
    """Build a small but realistic repository tree."""

    (root / "src").mkdir()
    (root / "src" / "Foo.java").write_text("class Foo {}")
    (root / "src" / "main.py").write_text("def main(): pass")
    (root / "src" / "App.kt").write_text("class App")
    (root / "openspec").mkdir()
    (root / "openspec" / "spec.md").write_text("# spec")
    (root / "openspec" / "changes").mkdir()
    (root / "openspec" / "changes" / "c1").mkdir()
    (root / "openspec" / "changes" / "c1" / "spec.md").write_text(
        "# delta"
    )
    (root / "docs").mkdir()
    (root / "docs" / "README.md").write_text("# docs")
    (root / "pom.xml").write_text("<project/>")
    (root / "requirements").mkdir()
    (root / "requirements" / "base.txt").write_text("flask==3.0")
    # Non-source noise that MUST be excluded:
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main")
    (root / "target").mkdir()
    (root / "target" / "Foo.class").write_bytes(b"\xca\xfe\xba\xbe")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "x.js").write_text("// 3rd party")
    (root / ".project-intelligence-cache").mkdir()
    (root / ".project-intelligence-cache" / "x.json").write_text("{}")


class DefaultPatternsTests(unittest.TestCase):
    """The default include / exclude lists MUST exist and be
    non-empty."""

    def test_default_includes_have_documented_entries(self) -> None:
        self.assertIn("*.java", DEFAULT_INCLUDE_PATTERNS)
        self.assertIn("*.py", DEFAULT_INCLUDE_PATTERNS)
        self.assertIn("*.md", DEFAULT_INCLUDE_PATTERNS)
        self.assertIn("pom.xml", DEFAULT_INCLUDE_PATTERNS)
        self.assertIn("openspec/**", DEFAULT_INCLUDE_PATTERNS)
        self.assertIn("docs/**", DEFAULT_INCLUDE_PATTERNS)
        self.assertIn("requirements/**", DEFAULT_INCLUDE_PATTERNS)

    def test_default_excludes_have_documented_entries(self) -> None:
        self.assertIn(".git/**", DEFAULT_EXCLUDE_PATTERNS)
        self.assertIn(".project-intelligence-cache/**", DEFAULT_EXCLUDE_PATTERNS)
        self.assertIn("target/**", DEFAULT_EXCLUDE_PATTERNS)
        self.assertIn("build/**", DEFAULT_EXCLUDE_PATTERNS)
        self.assertIn("node_modules/**", DEFAULT_EXCLUDE_PATTERNS)
        self.assertIn("tmp/local/**", DEFAULT_EXCLUDE_PATTERNS)


class ClassifySourceFamilyTests(unittest.TestCase):
    """Family classification is deterministic and stable."""

    def test_java_is_source_code(self) -> None:
        self.assertEqual(
            classify_source_family("src/Foo.java"),
            SOURCE_FAMILY_SOURCE_CODE,
        )

    def test_python_is_source_code(self) -> None:
        self.assertEqual(
            classify_source_family("scripts/main.py"),
            SOURCE_FAMILY_SOURCE_CODE,
        )

    def test_openspec_change_is_openspec_family(self) -> None:
        self.assertEqual(
            classify_source_family("openspec/changes/c1/spec.md"),
            SOURCE_FAMILY_OPENSPEC,
        )

    def test_root_openspec_md_is_openspec(self) -> None:
        self.assertEqual(
            classify_source_family("openspec/spec.md"),
            SOURCE_FAMILY_OPENSPEC,
        )

    def test_pom_xml_is_configuration(self) -> None:
        self.assertEqual(
            classify_source_family("pom.xml"),
            SOURCE_FAMILY_CONFIGURATION,
        )

    def test_requirements_txt_is_configuration(self) -> None:
        self.assertEqual(
            classify_source_family("requirements/base.txt"),
            SOURCE_FAMILY_CONFIGURATION,
        )

    def test_docs_markdown_is_documentation(self) -> None:
        self.assertEqual(
            classify_source_family("docs/README.md"),
            SOURCE_FAMILY_DOCUMENTATION,
        )


class DiscoveryTests(unittest.TestCase):
    """The discovery service walks the tree and applies defaults."""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="discovery-"))
        self.addCleanup(
            lambda: shutil.rmtree(self._tmp, ignore_errors=True),
        )
        _make_tree(self._tmp)
        self.service = RepositorySourceDiscovery()

    def test_discover_finds_expected_sources(self) -> None:
        inventory = self.service.discover(self._tmp)
        paths = inventory.paths()
        self.assertIn("src/Foo.java", paths)
        self.assertIn("src/main.py", paths)
        self.assertIn("src/App.kt", paths)
        self.assertIn("openspec/spec.md", paths)
        self.assertIn("docs/README.md", paths)
        self.assertIn("pom.xml", paths)
        self.assertIn("requirements/base.txt", paths)

    def test_discover_excludes_non_sources(self) -> None:
        inventory = self.service.discover(self._tmp)
        paths = inventory.paths()
        self.assertNotIn(".git/HEAD", paths)
        self.assertNotIn("target/Foo.class", paths)
        self.assertNotIn("node_modules/x.js", paths)
        self.assertNotIn(
            ".project-intelligence-cache/x.json", paths,
        )

    def test_discover_records_content_hash(self) -> None:
        inventory = self.service.discover(self._tmp)
        for entry in inventory.entries:
            self.assertEqual(
                len(entry.content_hash), 64,
                f"{entry.path} MUST carry a SHA-256 hex content hash",
            )

    def test_discover_records_parser_version(self) -> None:
        inventory = self.service.discover(self._tmp)
        for entry in inventory.entries:
            self.assertEqual(
                entry.parser_version, DEFAULT_PARSER_VERSION,
            )

    def test_discover_classifies_families(self) -> None:
        inventory = self.service.discover(self._tmp)
        family_by_path = {
            entry.path: entry.source_family
            for entry in inventory.entries
        }
        self.assertEqual(
            family_by_path["src/Foo.java"],
            SOURCE_FAMILY_SOURCE_CODE,
        )
        self.assertEqual(
            family_by_path["openspec/spec.md"],
            SOURCE_FAMILY_OPENSPEC,
        )
        self.assertEqual(
            family_by_path["pom.xml"],
            SOURCE_FAMILY_CONFIGURATION,
        )
        self.assertEqual(
            family_by_path["docs/README.md"],
            SOURCE_FAMILY_DOCUMENTATION,
        )


class IncrementalReuseTests(unittest.TestCase):
    """Unchanged files carry their retrieval_text_hash forward."""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="incremental-"))
        self.addCleanup(
            lambda: shutil.rmtree(self._tmp, ignore_errors=True),
        )
        _make_tree(self._tmp)
        self.service = RepositorySourceDiscovery()

    def test_unchanged_source_keeps_retrieval_text_hash(self) -> None:
        first = self.service.discover(self._tmp)
        # Simulate the ingestion pipeline recording the
        # retrieval text hash for one file.
        carried_entries = []
        for entry in first.entries:
            if entry.path == "src/Foo.java":
                carried_entries.append(
                    SourceInventoryEntry(
                        path=entry.path,
                        source_family=entry.source_family,
                        content_hash=entry.content_hash,
                        parser_version=entry.parser_version,
                        retrieval_text_hash="rth-Foo",
                        discovered_at=entry.discovered_at,
                    ),
                )
            else:
                carried_entries.append(entry)
        carried = SourceInventory(
            entries=tuple(carried_entries),
            captured_at=first.captured_at,
            schema_version=first.schema_version,
        )
        # Re-walk without touching anything.
        second = self.service.discover(self._tmp)
        merged, unchanged, modified = (
            self.service.incremental_reuse(
                previous_inventory=carried,
                new_inventory=second,
            )
        )
        # The merge MUST carry the retrieval_text_hash forward
        # for the file that already had one.
        rth_by_path = {
            entry.path: entry.retrieval_text_hash
            for entry in merged.entries
        }
        self.assertEqual(rth_by_path["src/Foo.java"], "rth-Foo")
        self.assertEqual(len(unchanged), len(second.entries))
        self.assertEqual(modified, ())

    def test_modified_source_is_classified(self) -> None:
        first = self.service.discover(self._tmp)
        # Edit one file.
        (self._tmp / "src" / "Foo.java").write_text(
            "class Foo { void bar() {} }",
        )
        second = self.service.discover(self._tmp)
        _, unchanged, modified = (
            self.service.incremental_reuse(
                previous_inventory=first,
                new_inventory=second,
            )
        )
        modified_paths = {entry.path for entry in modified}
        self.assertIn("src/Foo.java", modified_paths)
        # The unchanged count excludes the modified path.
        unchanged_paths = {entry.path for entry in unchanged}
        self.assertNotIn("src/Foo.java", unchanged_paths)

    def test_removed_source_is_detectable(self) -> None:
        first = self.service.discover(self._tmp)
        # Delete a file.
        (self._tmp / "src" / "App.kt").unlink()
        second = self.service.discover(self._tmp)
        first_paths = set(first.paths())
        second_paths = set(second.paths())
        removed = first_paths - second_paths
        self.assertEqual(removed, {"src/App.kt"})


class DiscoveryPersistenceTests(unittest.TestCase):
    """The inventory is persisted and read back."""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="persist-"))
        self.addCleanup(
            lambda: shutil.rmtree(self._tmp, ignore_errors=True),
        )
        _make_tree(self._tmp)
        self.service = RepositorySourceDiscovery()

    def test_persist_and_load_round_trip(self) -> None:
        inventory = self.service.discover(self._tmp)
        path = self._tmp / "inventory.json"
        self.service.persist(inventory, path)
        loaded = self.service.load(path)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(
            loaded.paths(), inventory.paths(),
        )
        for entry in loaded.entries:
            self.assertEqual(
                entry.parser_version, DEFAULT_PARSER_VERSION,
            )

    def test_load_returns_none_when_missing(self) -> None:
        loaded = self.service.load(self._tmp / "missing.json")
        self.assertIsNone(loaded)


if __name__ == "__main__":
    unittest.main()
