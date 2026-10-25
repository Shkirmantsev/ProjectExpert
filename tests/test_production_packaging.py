"""Packaging must preserve the model-free core and install a locked production stack."""
from __future__ import annotations

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sync_skills


class ProductionPackagingTests(unittest.TestCase):
    def test_every_direct_production_requirement_is_exact_and_in_hash_lock(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        lock = (ROOT / "requirements-production-linux-x86_64.txt").read_text() + (ROOT / "requirements-production-java-linux-x86_64.txt").read_text()
        self.assertEqual(metadata["project"]["dependencies"], [])
        for requirement in metadata["project"]["optional-dependencies"]["production"]:
            name, version = requirement.split("==")
            # PyTorch local +cpu versions satisfy the public exact version.
            expected = f"{name.lower()}=={version}"
            self.assertIn(expected, lock.lower())
        requirements = lock.splitlines()
        pinned = [i for i, line in enumerate(requirements) if "==" in line and not line.startswith("#")]
        self.assertGreater(len(pinned), 80)
        for index in pinned:
            self.assertIn("--hash=sha256:", requirements[index + 1])
        self.assertNotIn("nvidia-", lock)
        self.assertIn("torch==2.14.1+cpu", lock)

    def test_reviewed_production_inventory_covers_exact_lock_and_preserves_evidence(self):
        import hashlib
        import base64
        import json
        from pi_platform.core.licensing import DependencyInventory
        from pi_platform.core.licensing.lock_coverage import check_lock_coverage
        lock = ROOT / "requirements-production-linux-x86_64.txt"
        inventory = ROOT / "distribution/licenses/production-dependency-inventory.json"
        self.assertEqual(check_lock_coverage(lock, DependencyInventory(inventory).load()), [])
        evidence = json.loads((ROOT / "distribution/licenses/production-license-evidence.json").read_text())
        for entry in json.loads(inventory.read_text())["dependencies"]:
            self.assertEqual(entry["evidence"]["lock_sha256"], hashlib.sha256(lock.read_bytes()).hexdigest())
            for file in entry["evidence"]["audited_license_files"]:
                key = f"{entry['name']}=={entry['version']}/{file['path']}"
                self.assertEqual(evidence[key]["sha256"], file["sha256"])
                self.assertEqual(hashlib.sha256(base64.b64decode(evidence[key]["bytes_base64"])).hexdigest(), file["sha256"])

    def test_core_and_production_image_contracts_are_separate(self):
        text = (ROOT / "Containerfile").read_text()
        core, production = text.split("FROM core AS production")
        self.assertIn("AS core", core)
        self.assertIn("PI_STARTUP_PROFILE=minimal", core)
        self.assertNotIn('".[production]"', core)
        self.assertIn("--require-hashes", core.split("AS production-dependencies", 1)[1])
        self.assertIn("COPY --from=production-dependencies /opt/production/ /usr/local/", production)
        self.assertIn('".[production]"', production)
        self.assertIn("pip check", production)
        self.assertIn("PI_STARTUP_PROFILE=production", production)

    def test_wheel_data_includes_model_inventory_and_agent_resources(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        data = metadata["tool"]["setuptools"]["data-files"]
        self.assertIn("distribution/licenses/model-licenses.json", data["distribution/licenses"])
        for name in ("distribution/skills/project-intelligence", "distribution/okf-profile"):
            self.assertIn(name, data)

    def test_codex_inventory_contains_nested_catalog_and_integration_skills(self):
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw)
            for name in (*sync_skills.CORE_SKILL_NAMES, "catalog/optional", "openspec-propose"):
                skill = source / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text("test skill")
            with patch.object(sync_skills, "SOURCE", source):
                names = {path.relative_to(source).as_posix() for path in sync_skills.codex_skills()}
            self.assertEqual(len(names), 6)
            self.assertIn("catalog/optional", names)
            self.assertIn("openspec-propose", names)



class LicenseGatePortabilityTests(unittest.TestCase):
    def _run(self, args):
        import contextlib
        import io
        import json
        from pi_platform.cli.main import main
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["license-gate", *args])
        return status, json.loads(output.getvalue())

    def test_missing_and_empty_explicit_inventory_fail(self):
        import json
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "inventory.json"
            self.assertEqual(self._run(["--inventory", str(path)])[0], 1)
            path.write_text(json.dumps({"dependencies": []}))
            self.assertEqual(self._run(["--inventory", str(path)])[0], 1)

    def test_installed_prefix_fallback_loads_inventory_outside_checkout(self):
        import json
        # Import the module explicitly: the package also exports a main callable.
        import importlib
        cli = importlib.import_module("pi_platform.cli.main")
        with tempfile.TemporaryDirectory() as raw:
            prefix = Path(raw)
            inventory = prefix / "distribution/licenses/dependency-inventory.json"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(json.dumps({"dependencies": [
                {"name": "runtime", "version": "1", "spdx": "MIT"}
            ]}))
            with patch.object(cli.sys, "prefix", str(prefix)), patch.dict(cli.os.environ, {"PI_PLATFORM_HOME": str(prefix / "absent")}):
                status, payload = self._run(["--target", str(prefix / "elsewhere")])
            self.assertEqual(status, 0)
            self.assertEqual(payload["inventory"], str(inventory))
            self.assertEqual(len(payload["findings"]), 1)

    def test_production_lock_requires_every_exact_coordinate(self):
        from pi_platform.core.licensing.lock_coverage import check_lock_coverage
        from pi_platform.ports import Dependency
        with tempfile.TemporaryDirectory() as raw:
            lock = Path(raw) / "requirements.txt"
            lock.write_text("name-one==1.0\\\n    --hash=sha256:fake\nother==2.0\n")
            reviewed = [Dependency(name="name_one", version="1.0", spdx="MIT")]
            self.assertEqual(check_lock_coverage(lock, reviewed), ["other==2.0: exact coordinate missing from reviewed inventory"])
            lock.write_text("name-one>=1\n")
            with self.assertRaises(ValueError):
                check_lock_coverage(lock, reviewed)


class SpdxExpressionTests(unittest.TestCase):
    def decision(self, expression):
        from pi_platform.core.licensing import LicensePolicy
        from pi_platform.ports import Dependency
        return LicensePolicy().evaluate(Dependency(name="fixture", version="1", spdx=expression))[0]

    def test_boolean_expressions_preserve_existing_policy(self):
        self.assertEqual(self.decision("MIT AND BSD-3-Clause"), "allow")
        self.assertEqual(self.decision("MIT OR MPL-2.0"), "allow")
        self.assertEqual(self.decision("MIT AND MPL-2.0"), "review")
        self.assertEqual(self.decision("(MIT OR MPL-2.0) AND BSD-2-Clause"), "allow")
        self.assertEqual(self.decision("MIT OR research-only"), "deny")
        self.assertEqual(self.decision("Apache-2.0 WITH LLVM-exception"), "deny")
        self.assertEqual(self.decision("MIT AND"), "deny")
        self.assertEqual(self.decision("MIT garbage BSD-3-Clause"), "deny")


class DockerProductCommandTests(unittest.TestCase):
    def test_docker_commands_operate_on_container_and_preserve_model_selection(self):
        import json
        import os
        import shutil
        import subprocess
        if os.name == "nt":
            self.skipTest("POSIX source Make recipes; native Windows launcher is tested separately")
        if shutil.which("make") is None:
            self.skipTest("make unavailable")
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            docker = directory / "docker"
            docker.write_text("#!/usr/bin/python3\nimport json,os,sys\nprint(json.dumps({'args':sys.argv[1:],'model':os.environ.get('PI_EMBEDDING_MODEL'),'target':os.environ.get('PI_TARGET_REPO')}))\n")
            docker.chmod(0o755)
            env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ["PATH"])
            def run(command):
                output = subprocess.check_output(["make", "--no-print-directory", command, "DOCKER=1", "MODEL=qwen", "TARGET=/tmp/target-with-spaces project"], cwd=ROOT, env=env, text=True)
                return [json.loads(line) for line in output.splitlines()]
            model = run("pi-model")[0]
            self.assertEqual(model["model"], "qwen")
            self.assertEqual(model["target"], "/tmp/target-with-spaces project")
            self.assertEqual(model["args"][-3:], ["-d", "--force-recreate", "production"])
            for command in ("pi-status", "pi-reindex", "pi-doctor"):
                for call in run(command):
                    self.assertEqual(call["args"][:6], ["compose", "--profile", "production", "exec", "-T", "production"])
                    self.assertEqual(call["args"][-2:], ["--target", "/repo"])


if __name__ == "__main__":
    unittest.main()
