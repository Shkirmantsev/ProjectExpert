"""Phase 6 task 86 — skill distribution plane tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pi_platform.mcp.skill_plane import (
    DISTRIBUTION_SCHEMA_VERSION,
    SkillDistributionError,
    SkillDistributionPlane,
)


__all__ = ["SkillDistributionPlaneTests"]


class SkillDistributionPlaneTests(unittest.TestCase):

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        skill_dir = self.tmp / "project-intelligence"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_bytes(
            b"---\nname: project-intelligence\nversion: 1.4.0\n"
            b"description: test\nlicense: Apache-2.0\n---\n\n"
            b"# Project Intelligence Test Skill\n",
        )
        refs = skill_dir / "references"
        refs.mkdir()
        (refs / "MCP-TOOLS.md").write_bytes(b"# tools\n")
        (refs / "SECURITY.md").write_bytes(b"# security\n")
        self.plane = SkillDistributionPlane(skills_root=self.tmp)

    def test_manifest_carries_documented_fields(self):
        manifest = self.plane.manifest()
        self.assertEqual(manifest["platformVersion"], "0.8.0")
        self.assertEqual(manifest["mcpApiVersion"], "1.3.0")
        self.assertEqual(manifest["distributionSchemaVersion"],
                         DISTRIBUTION_SCHEMA_VERSION)
        self.assertEqual(manifest["skill"]["name"],
                         "project-intelligence")
        self.assertEqual(manifest["skill"]["version"], "1.4.0")
        self.assertIn("sha256", manifest["skill"])
        self.assertIn("0.2", manifest["okf"]["supported"])

    def test_manifest_bytes_are_byte_stable(self):
        first = self.plane.manifest_bytes()
        second = self.plane.manifest_bytes()
        self.assertEqual(first, second)

    def test_manifest_bytes_are_byte_stable_across_instances(self):
        plane2 = SkillDistributionPlane(skills_root=self.tmp)
        self.assertEqual(self.plane.manifest_bytes(),
                         plane2.manifest_bytes())

    def test_list_resources_returns_indexed_uris(self):
        uris = self.plane.list_resources()
        self.assertIn("project-intelligence://distribution/manifest",
                      uris)
        self.assertIn("project-intelligence://skills/index", uris)
        self.assertIn("project-intelligence://skills/project-intelligence/"
                      "1.4.0/SKILL.md", uris)
        self.assertIn("project-intelligence://skills/project-intelligence/"
                      "1.4.0/references/MCP-TOOLS.md", uris)

    def test_read_resource_returns_skill_bytes(self):
        body = self.plane.read_resource(
            "project-intelligence://skills/project-intelligence/1.4.0/"
            "SKILL.md",
        )
        self.assertTrue(body.startswith(b"---"))

    def test_read_resource_returns_reference_bytes(self):
        body = self.plane.read_resource(
            "project-intelligence://skills/project-intelligence/1.4.0/"
            "references/MCP-TOOLS.md",
        )
        self.assertEqual(body, b"# tools\n")

    def test_read_resource_refuses_unknown_uri_scheme(self):
        with self.assertRaises(SkillDistributionError):
            self.plane.read_resource("https://example.com/foo")

    def test_read_resource_refuses_wrong_version(self):
        with self.assertRaises(SkillDistributionError):
            self.plane.read_resource(
                "project-intelligence://skills/project-intelligence/"
                "9.9.9/SKILL.md",
            )

    def test_read_resource_refuses_escape(self):
        with self.assertRaises(SkillDistributionError):
            self.plane.read_resource(
                "project-intelligence://skills/project-intelligence/1.4.0/"
                "../../etc/passwd",
            )

    def test_read_resource_refuses_symlink(self):
        # Create a symlink under the skill dir.
        skill = self.tmp / "project-intelligence"
        (skill / "evil.md").symlink_to("/etc/passwd")
        with self.assertRaises(SkillDistributionError):
            self.plane.read_resource(
                "project-intelligence://skills/project-intelligence/1.4.0/"
                "evil.md",
            )

    def test_read_resource_refuses_unknown_skill(self):
        with self.assertRaises(SkillDistributionError):
            self.plane.read_resource(
                "project-intelligence://skills/missing/1.4.0/SKILL.md",
            )

    def test_distribution_schema_version_is_identifier_not_semver(self):
        # The schema version is documented as an identifier, not a
        # semver range. Pinning to "1" (not "1.0.0") enforces the
        # contract.
        self.assertEqual(DISTRIBUTION_SCHEMA_VERSION, "1")

    def test_skills_index_lists_all_skills(self):
        body = self.plane.read_resource(
            "project-intelligence://skills/index",
        )
        index = json.loads(body.decode("utf-8"))
        self.assertEqual(len(index["skills"]), 1)
        self.assertEqual(index["skills"][0]["name"],
                         "project-intelligence")
        self.assertEqual(index["skills"][0]["version"], "1.4.0")

    def test_unknown_skill_dir_without_skill_md_raises(self):
        # Extra dir without SKILL.md is ignored; only the skill
        # package with SKILL.md counts. The plane constructor does
        # NOT raise on missing-dir; it raises when no skills at all.
        (self.tmp / "empty-dir").mkdir()
        # Re-instantiate; should still succeed with the real skill.
        plane = SkillDistributionPlane(skills_root=self.tmp)
        self.assertEqual(plane.manifest()["skill"]["name"],
                         "project-intelligence")

    def test_no_skills_raises(self):
        empty = self.tmp / "no-skills"
        empty.mkdir()
        with self.assertRaises(SkillDistributionError):
            SkillDistributionPlane(skills_root=empty)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()