import contextlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import harness


class HarnessInitTests(unittest.TestCase):
    def test_init_disables_openspec_telemetry_when_cli_is_available(self):
        configure = getattr(harness, "configure_openspec", None)
        self.assertIsNotNone(configure, "initialization needs an OpenSpec config step")

        with tempfile.TemporaryDirectory() as raw:
            fixture = pathlib.Path(raw)
            log = fixture / "openspec-args.txt"
            executable = fixture / "openspec"
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import os, pathlib, sys\n"
                "pathlib.Path(os.environ['OPENSPEC_TEST_LOG']).write_text('\\n'.join(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)

            def run_without_project_side_effects(command, *, check=True):
                if command[0] == "openspec":
                    return subprocess.run([sys.executable, str(executable), *command[1:]], check=check)
                return subprocess.CompletedProcess(command, 0)

            environment = {
                "PATH": f"{fixture}{os.pathsep}{os.environ.get('PATH', '')}",
                "OPENSPEC_TEST_LOG": str(log),
            }
            args = types.SimpleNamespace(install_mcp=False)
            with (
                mock.patch.dict(os.environ, environment),
                mock.patch.object(harness.shutil, "which", return_value=str(executable)),
                mock.patch.object(harness, "ensure_env"),
                mock.patch.object(harness, "cmd_index"),
                mock.patch.object(harness, "cmd_client_config"),
                mock.patch.object(harness, "run", side_effect=run_without_project_side_effects),
            ):
                harness.cmd_init(args)

            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["config", "set", "telemetry.enabled", "false"],
            )

    def test_init_continues_when_openspec_is_unavailable(self):
        configure = getattr(harness, "configure_openspec", None)
        self.assertIsNotNone(configure, "initialization needs an OpenSpec config step")

        commands = []
        args = types.SimpleNamespace(install_mcp=False)
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"PATH": ""}),
            mock.patch.object(harness, "ensure_env"),
            mock.patch.object(harness, "cmd_index"),
            mock.patch.object(harness, "cmd_client_config"),
            mock.patch.object(
                harness,
                "run",
                side_effect=lambda command, **_: commands.append(command),
            ),
            contextlib.redirect_stdout(output),
        ):
            harness.cmd_init(args)

        self.assertFalse(any(command[0] == "openspec" for command in commands))
        self.assertIn("OpenSpec telemetry: NOT RUN", output.getvalue())


if __name__ == "__main__":
    unittest.main()
