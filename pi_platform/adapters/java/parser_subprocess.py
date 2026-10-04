"""Bounded one-shot parser lifecycle, version and license gate, fail-closed errors."""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from pi_platform.core.licensing import DependencyInventory, LicenseGate
from pi_platform.ports.ingest.java_parser import *
from pi_platform.ports.ingest.java_parser import JavaEntity, JavaEntityKind

log = logging.getLogger(__name__)


class TreeSitterJavaSubprocess(JavaParserPort):
    def __init__(self, command=None, *, required=False, inventory_path=None):
        self.command = tuple(
            command or (sys.executable, "-m", "pi_platform.adapters.java.parser_worker")
        )
        self.required = required
        self.inventory_path = (
            Path(inventory_path)
            if inventory_path
            else Path(__file__).resolve().parents[3]
            / "distribution/licenses/dependency-inventory.json"
        )
        if inventory_path is None and not self.inventory_path.exists():
            self.inventory_path = (
                Path(sys.prefix) / "distribution/licenses/dependency-inventory.json"
            )
        deps = DependencyInventory(self.inventory_path).load()
        selected = [d for d in deps if d.name in ("tree-sitter-java", "tree-sitter")]
        if {d.name for d in selected} != {
            "tree-sitter-java",
            "tree-sitter",
        } or not LicenseGate().run(selected)[0]:
            raise JavaParserVersionMismatch(
                "Java parser dependencies must be declared and license-approved before registration"
            )

    @property
    def parser_version(self):
        return "tree-sitter-java-0.23.5"

    def _run(self, arguments, timeout, input=None):
        try:
            return subprocess.run(
                [*self.command, *arguments],
                input=input,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise JavaParserMissing(
                f"parser executable missing: {self.command[0]}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise JavaParserTimeout(
                f"Java parser exceeded {timeout}s; child terminated"
            ) from exc
        except OSError as exc:
            raise JavaParserMissing(str(exc)) from exc

    def is_available(self):
        try:
            return self._run(["--version"], 5).returncode == 0
        except JavaParserMissing:
            return False

    def parse(self, request):
        started = time.perf_counter()
        probe = None
        try:
            probe = self._run(["--version"], request.timeout_seconds)
        except JavaParserMissing:
            if self.required:
                raise
        if probe is None or probe.returncode == 3:
            if self.required:
                raise JavaParserMissing("required Java parser packages are unavailable")
            log.warning(
                "Java parser unavailable; metadata-only assumption source=%s",
                request.file_path,
            )
            return JavaParseResult(
                (),
                self.parser_version,
                0,
                True,
                "parser unavailable; metadata-only assumption",
            )
        try:
            if probe.returncode != 0:
                raise ValueError("version probe failed")
            info = json.loads(probe.stdout)
            if (
                info["parser_version"] != request.parser_version
                or info.get("binding_version") != "0.25.2"
            ):
                raise JavaParserVersionMismatch(f"unsupported parser version: {info}")
            output = self._run(
                [],
                request.timeout_seconds,
                json.dumps(
                    {"source": request.source, "file_path": str(request.file_path)}
                ),
            )
            if output.returncode != 0:
                raise ValueError(f"parser failed: {output.stderr[:400]}")
            result = json.loads(output.stdout)
            if result["parser_version"] != request.parser_version:
                raise JavaParserVersionMismatch(
                    "parser result version differs from request"
                )
            entities = []
            for row in result["entities"]:
                row = dict(row)
                row["kind"] = JavaEntityKind(row["kind"])
                row["source_path"] = request.file_path
                entities.append(JavaEntity(**row))
            return JavaParseResult(
                tuple(entities),
                result["parser_version"],
                (time.perf_counter() - started) * 1000,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise JavaParserCorruptOutput(
                f"invalid Java parser response: {exc}"
            ) from exc
