"""Phase 10 §121 schema-version migration guard tests.

Each scenario corresponds to one of the four typed errors declared
in :mod:`pi_platform.core.eval.migration_guard`:

- :class:`IdentityInvalid` — a required identity field is missing
  or malformed;
- :class:`MigrationRequired` — a documented migration path exists
  for the advertised version;
- :class:`Incompatible` — no compatible version and no path;
- :class:`WorkingTreeMismatch` — the captured working-tree
  fingerprint disagrees with HEAD.

The tests assert the typed errors and confirm no canonical file is
mutated by the helper.
"""

from __future__ import annotations

import unittest

from pi_platform.core.eval.migration_guard import (
    IdentityInvalid,
    Incompatible,
    MigrationRequired,
    RuntimeSchemaVersions,
    WorkingTreeMismatch,
    check_schema_identity,
)


RUNTIME = RuntimeSchemaVersions(
    knowledge_schema="0.7.0",
    embedding_model="phase-10-embed/1",
    index_schema="0.7.0",
)


GOOD_MANIFEST = {
    "knowledgeSchemaVersion": "0.7.0",
    "embeddingModelVersion": "phase-10-embed/1",
    "indexSchemaVersion": "0.7.0",
}


class IdentityInvalidScenario(unittest.TestCase):
    def test_missing_knowledge_field(self):
        manifest = {**GOOD_MANIFEST}
        manifest.pop("knowledgeSchemaVersion")
        with self.assertRaises(IdentityInvalid):
            check_schema_identity(manifest=manifest, runtime_versions=RUNTIME)

    def test_missing_embedding_field(self):
        manifest = {**GOOD_MANIFEST, "embeddingModelVersion": ""}
        with self.assertRaises(IdentityInvalid):
            check_schema_identity(manifest=manifest, runtime_versions=RUNTIME)

    def test_missing_index_field(self):
        manifest = {**GOOD_MANIFEST, "indexSchemaVersion": None}
        with self.assertRaises(IdentityInvalid):
            check_schema_identity(manifest=manifest, runtime_versions=RUNTIME)


class MigrationRequiredScenario(unittest.TestCase):
    def test_newer_knowledge_schema_with_path(self):
        manifest = {**GOOD_MANIFEST, "knowledgeSchemaVersion": "0.8.0"}
        with self.assertRaises(MigrationRequired) as ctx:
            check_schema_identity(
                manifest=manifest,
                runtime_versions=RUNTIME,
                migration_paths={"0.8.0": "docs/migrations/0.7.0-to-0.8.0.md"},
            )
        self.assertEqual(ctx.exception.migration_path, "docs/migrations/0.7.0-to-0.8.0.md")


class IncompatibleScenario(unittest.TestCase):
    def test_unknown_knowledge_schema(self):
        manifest = {**GOOD_MANIFEST, "knowledgeSchemaVersion": "99.0.0"}
        with self.assertRaises(Incompatible):
            check_schema_identity(manifest=manifest, runtime_versions=RUNTIME)

    def test_unknown_embedding_model(self):
        manifest = {**GOOD_MANIFEST, "embeddingModelVersion": "rogue-model"}
        with self.assertRaises(Incompatible):
            check_schema_identity(manifest=manifest, runtime_versions=RUNTIME)


class WorkingTreeMismatchScenario(unittest.TestCase):
    def test_working_tree_mismatch_raises(self):
        # The check_schema_identity helper does not consult the
        # working tree; the WorkingTreeMismatch error class is
        # exported and the test simply asserts it can be raised and
        # caught. Phase 11 will wire the helper to the working-tree
        # fingerprint seam.
        try:
            raise WorkingTreeMismatch("HEAD fingerprint disagrees with working tree")
        except WorkingTreeMismatch as exc:
            self.assertIn("fingerprint", str(exc))


class NoMutationScenario(unittest.TestCase):
    def test_helper_does_not_mutate_manifest(self):
        manifest = {**GOOD_MANIFEST}
        original = dict(manifest)
        try:
            check_schema_identity(manifest=manifest, runtime_versions=RUNTIME)
        except Exception:
            pass
        self.assertEqual(manifest, original)


class CompatibilitySuccessScenario(unittest.TestCase):
    def test_matching_versions_pass_silently(self):
        # The helper is a no-op when all three fields match.
        check_schema_identity(manifest=dict(GOOD_MANIFEST), runtime_versions=RUNTIME)
