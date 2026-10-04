import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RECON = ROOT / "scripts" / "repo_recon.py"
CONTEXT = ROOT / "scripts" / "context_pack.py"
PROMPT_MANIFEST = ROOT / "scripts" / "prompt_manifest.py"


def run_json(script: pathlib.Path, *args: str, check: bool = True):
    result = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    payload = json.loads(result.stdout) if result.stdout.strip() else None
    return result, payload


class RepositoryReconTests(unittest.TestCase):
    def test_profile_is_deterministic_and_detects_real_project_contracts(self):
        _, first = run_json(RECON)
        _, second = run_json(RECON)
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "1.0")
        self.assertIn("python", first["languages"])
        self.assertIn("Makefile", first["build_files"])
        self.assertIn("AGENTS.md", first["instruction_files"])
        self.assertIn("test", first["make_targets"])
        self.assertRegex(first["contract_hashes"]["Makefile"], r"^[0-9a-f]{64}$")
        self.assertRegex(first["contract_hashes"]["AGENTS.md"], r"^[0-9a-f]{64}$")
        self.assertRegex(first["profile_hash"], r"^sha256:[0-9a-f]{64}$")

    def test_profile_excludes_generated_and_secret_paths(self):
        _, profile = run_json(RECON)
        serialized = json.dumps(profile)
        self.assertNotIn(".env", serialized)
        self.assertNotIn("node_modules", serialized)
        self.assertNotIn("tmp/local", serialized)


class ContextPackTests(unittest.TestCase):
    def test_pack_is_content_addressed_and_file_order_independent(self):
        common = (
            "--goal",
            "Implement deterministic context packs",
            "--acceptance",
            "same logical input has the same ID",
            "--constraint",
            "do not include source content",
        )
        _, first = run_json(
            CONTEXT,
            *common,
            "--file",
            "scripts/skill_router.py",
            "--file",
            "scripts/session_state.py",
        )
        _, second = run_json(
            CONTEXT,
            *common,
            "--file",
            "scripts/session_state.py",
            "--file",
            "scripts/skill_router.py",
        )
        self.assertEqual(first, second)
        self.assertRegex(first["id"], r"^CP-[0-9A-F]{16}$")
        self.assertEqual(len(first["files"]), 2)
        self.assertNotIn(
            "Deterministic, low-context router", json.dumps(first),
            "ContextPack must store file evidence, not source bodies",
        )

    def test_pack_rejects_outside_project_files(self):
        result, payload = run_json(
            CONTEXT,
            "--goal",
            "Escape project",
            "--file",
            "/etc/hosts",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "path_outside_project")

    def test_pack_rejects_secret_like_inline_context(self):
        result, payload = run_json(
            CONTEXT,
            "--goal",
            "Debug password=super-secret-value",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "possible_secret")

    def test_pack_enforces_token_budget_order(self):
        result, payload = run_json(
            CONTEXT,
            "--goal",
            "Invalid budget",
            "--target-tokens",
            "5000",
            "--hard-max-tokens",
            "1000",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "invalid_budget")

    def test_pack_records_why_each_file_was_selected(self):
        _, payload = run_json(
            CONTEXT,
            "--goal",
            "Review routing behavior",
            "--file",
            "scripts/skill_router.py::implementation under review",
        )
        self.assertEqual(payload["files"][0]["reason"], "implementation under review")


class PromptManifestTests(unittest.TestCase):
    def test_manifest_has_stable_skill_order_and_no_volatile_task_data(self):
        common = (
            "--role",
            "executor",
            "--tool-profile",
            "native-code",
            "--project-profile-hash",
            "sha256:abc",
        )
        _, first = run_json(
            PROMPT_MANIFEST,
            *common,
            "--skill",
            "verification",
            "--skill",
            "systematic-debugging",
        )
        _, second = run_json(
            PROMPT_MANIFEST,
            *common,
            "--skill",
            "systematic-debugging",
            "--skill",
            "verification",
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [item["name"] for item in first["skill_prefix"]],
            ["systematic-debugging", "verification"],
        )
        serialized = json.dumps(first).lower()
        self.assertNotIn("timestamp", serialized)
        self.assertNotIn("request_id", serialized)

    def test_manifest_rejects_unknown_skill(self):
        result, payload = run_json(
            PROMPT_MANIFEST,
            "--role",
            "executor",
            "--tool-profile",
            "native-code",
            "--project-profile-hash",
            "sha256:abc",
            "--skill",
            "does-not-exist",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "unknown_skill")


if __name__ == "__main__":
    unittest.main()
