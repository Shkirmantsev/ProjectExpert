"""Application services reject pre-ownership images before they can write."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class DeploymentImageCompatibilityTests(unittest.TestCase):
    def test_supported_images_keep_the_application_command_and_force_preparation(self):
        for template, service in (("distribution/deployment/compose.yaml", "production"),
                                  ("docker-compose.yml", "core"),
                                  ("docker-compose.yml", "production")):
            with self.subTest(template=template, service=service), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                package = root / "pi_platform"
                cli = package / "cli"
                fs = package / "adapters" / "fs"
                cli.mkdir(parents=True)
                fs.mkdir(parents=True)
                for folder in (package, cli, fs.parent, fs):
                    (folder / "__init__.py").touch()
                (fs / "container_identity.py").write_text(
                    "import os\nfrom pathlib import Path\n"
                    "def prepare_project_user(target):\n"
                    "    assert os.environ['PI_RUN_AS_PROJECT_OWNER']=='1'\n"
                    "    (Path(target)/'prepared').touch()\n")
                (cli / "main.py").write_text(
                    "import sys\n"
                    "def main():\n"
                    "    return 0 if len(sys.argv)>1 and sys.argv[1] in ('start','serve') else 2\n")
                config = yaml.safe_load((ROOT / template).read_text())["services"][service]
                entrypoint = config["entrypoint"]
                # Compose ignores image CMD when an entrypoint override is set.
                result = subprocess.run(
                    [sys.executable, *entrypoint[1:], *config.get("command", [])],
                    cwd=root, env={**os.environ, "PYTHONPATH": raw, "PI_TARGET_ROOT": raw,
                                   "PI_RUN_AS_PROJECT_OWNER": "0"},
                    capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((root / "prepared").exists())

    def test_legacy_image_cli_cannot_write_through_application_entrypoints(self):
        for template, service in (("distribution/deployment/compose.yaml", "production"),
                                  ("docker-compose.yml", "core"),
                                  ("docker-compose.yml", "production")):
            with self.subTest(template=template, service=service), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                package = root / "pi_platform"
                cli = package / "cli"
                fs = package / "adapters" / "fs"
                cli.mkdir(parents=True)
                fs.mkdir(parents=True)
                for folder in (package, cli, fs.parent, fs):
                    (folder / "__init__.py").touch()
                (cli / "main.py").write_text(
                    "import os\nfrom pathlib import Path\n"
                    "def main():\n"
                    "    (Path(os.environ['PI_TARGET_ROOT'])/'unsafe-write').write_text('root writer')\n"
                    "    return 0\n")
                (cli / "__main__.py").write_text("from .main import main\nraise SystemExit(main())\n")
                config = yaml.safe_load((ROOT / template).read_text())["services"][service]
                # Model the old image's default ENTRYPOINT when Compose supplies none.
                entrypoint = config.get("entrypoint", ["python", "-m", "pi_platform.cli"])
                result = subprocess.run(
                    [sys.executable, *entrypoint[1:], "start", "--target", raw],
                    cwd=root, env={**os.environ, "PYTHONPATH": raw, "PI_TARGET_ROOT": raw},
                    capture_output=True, text=True, timeout=20)
                self.assertFalse((root / "unsafe-write").exists(), result.stderr)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("upgrade", result.stderr.lower())
