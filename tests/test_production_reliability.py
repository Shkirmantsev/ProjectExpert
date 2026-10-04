import importlib.util
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name: str, path: pathlib.Path):
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class ProductionReliabilityTests(unittest.TestCase):
    def test_atomic_secret_write_is_private_on_first_publish(self):
        common = load("common_reliability", ROOT / "scripts/common.py")
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "secret"
            common.atomic_write_text(path, "sensitive\n", mode=0o600)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.read_text(), "sensitive\n")
            self.assertEqual(list(path.parent.glob(".secret.*")), [])

    def test_state_scripts_do_not_import_posix_lock_at_module_load(self):
        for name in ("session_state.py", "lesson_candidate.py"):
            text = (ROOT / "scripts" / name).read_text()
            self.assertNotIn("import fcntl", text)
            self.assertIn("from file_lock import file_lock", text)
        lock = (ROOT / "scripts/file_lock.py").read_text()
        self.assertIn('os.name == "nt"', lock)
        self.assertIn("import msvcrt", lock)
        self.assertIn("import fcntl", lock)
        bootstrap = (ROOT / "scripts/bootstrap_env.py").read_text()
        self.assertIn('hasattr(os, "getuid")', bootstrap)
        self.assertIn('hasattr(os, "getgid")', bootstrap)

    def test_client_generator_owns_opencode_dependency_and_private_runtime(self):
        generator = load("configure_clients_reliability", ROOT / "scripts/configure_clients.py")
        with tempfile.TemporaryDirectory() as raw:
            project = pathlib.Path(raw)
            env = {
                "HERMES_ENABLED": "true",
                "PROJECT_ROOT": raw,
                "HERMES_REMOTE_HOST": "worker.invalid",
                "HERMES_REMOTE_API_KEY": "test-key",
            }
            with (
                mock.patch.object(generator, "ROOT", project),
                mock.patch.object(generator, "GEN", project / ".generated"),
            ):
                (project / "templates/opencode").mkdir(parents=True)
                (project / "templates/opencode/hermes.js").write_text("export {}\n")
                generator.write_secrets(env)
                generator.configure_opencode(env, {})
            package = project / ".opencode/package.json"
            self.assertTrue(package.is_file())
            self.assertIn("@opencode-ai/plugin", package.read_text())
            self.assertIn('"type": "module"', package.read_text())
            for path in (
                project / ".generated/hermes-api-key",
                project / ".generated/opencode-hermes-runtime.json",
            ):
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_full_gate_owns_strict_specs_manifest_and_secret_free_profile(self):
        harness = (ROOT / "harness.py").read_text()
        self.assertIn('"validate", "--all", "--strict"', harness)
        self.assertIn('"scripts/artifact_manifest.py", "verify"', harness)
        self.assertIn('"check-delegated"', harness)
        workflow = (ROOT / ".github/workflows/verify.yml").read_text()
        self.assertIn("windows-latest", workflow)
        self.assertIn("python harness.py check-delegated", workflow)

    def test_manifest_does_not_adopt_unrelated_untracked_files_by_default(self):
        manifest = load(
            "artifact_manifest_reliability", ROOT / "scripts/artifact_manifest.py"
        )
        with (
            mock.patch.object(manifest, "git_paths", return_value={"tracked.txt"}),
            mock.patch.object(manifest, "manifest_paths", return_value={"owned-new.txt"}),
            mock.patch.object(manifest, "ROOT", pathlib.Path("/repo")),
            mock.patch.object(pathlib.Path, "is_file", return_value=True),
        ):
            paths = manifest.owned_paths()
        self.assertEqual(
            [path.as_posix() for path in paths],
            ["/repo/owned-new.txt", "/repo/tracked.txt"],
        )

    def test_manifest_can_adopt_one_explicit_untracked_file(self):
        manifest = load(
            "artifact_manifest_explicit", ROOT / "scripts/artifact_manifest.py"
        )
        with tempfile.TemporaryDirectory() as raw:
            project = pathlib.Path(raw)
            selected = project / "selected.txt"
            selected.write_text("owned")
            unrelated = project / "unrelated.txt"
            unrelated.write_text("user")
            with (
                mock.patch.object(manifest, "git_paths", return_value=set()),
                mock.patch.object(manifest, "manifest_paths", return_value=set()),
                mock.patch.object(manifest, "ROOT", project),
            ):
                paths = manifest.owned_paths(additions=("selected.txt",))
            self.assertEqual(paths, [selected])
            self.assertNotIn(unrelated, paths)

    def test_hermes_patch_helper_is_exact_revision_scoped(self):
        helper = (ROOT / "scripts/apply_hermes_approval_patch.py").read_text()
        self.assertIn("SUPPORTED_PATCHES", helper)
        self.assertIn("4f22543509d1b91dc45bcb369447126c5eb14fb7", helper)
        self.assertIn("981101239a064c020a9d18fc3b1060ae306934ed", helper)
        self.assertIn("SUPPORTED_PATCHES.get(revision)", helper)
        legacy_patch = (
            ROOT
            / "patches/hermes-agent/0002-legacy-981101-advertise-run-approval-resolver.patch"
        ).read_text()
        self.assertIn("approval_events=approval_events[-20:]", legacy_patch)
        self.assertIn("pending_approvals=[event]", legacy_patch)
        self.assertIn("pending_approvals=[]", legacy_patch)


if __name__ == "__main__":
    unittest.main()
