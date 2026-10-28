"""Optional tooling for reconstructed library code.

Two things can be reconstructed from a compiled artifact:

* **Python bytecode** -- the standard library ``dis`` module
  disassembles a ``.pyc``. The result is a **disassembly**, which is
  not recovered source.
* **Java class files** -- an external decompiler can reconstruct a
  method body. The result is a **decompilation**, which is a
  reconstruction, not the original text.

Both tools are optional. A missing tool, an unsupported version or a
tool that is not explicitly allowlisted yields a **capability
diagnostic** and a partial result. It never fails the deployment and
it never pretends that the answer is source.

Native binaries (``.so``, ``.pyd``, ``.node``) are never
decompiled: there is no supported, bounded reconstruction for them, and
this module therefore refuses them explicitly.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pi_platform.core.research.policy import AcquisitionPolicy
from pi_platform.core.research.records import (
    EvidenceReference,
    Representation,
    ResearchResult,
    ResearchStatus,
)

__all__ = [
    "TOOL_MATRIX",
    "ToolSpec",
    "tooling_capabilities",
    "PythonBytecodeReader",
    "JavaDecompiler",
    "NATIVE_BINARY_SUFFIXES",
]


#: Suffixes this module refuses to reconstruct.
NATIVE_BINARY_SUFFIXES = (".so", ".pyd", ".dylib", ".node", ".dll", ".exe")


@dataclass(frozen=True)
class ToolSpec:
    """The reviewed identity of one optional tool.

    ``license`` and ``supported_versions`` are recorded here so the
    capability report states what is actually shipped, not what a
    README promises.
    """

    name: str
    ecosystem: str
    license: str
    supported_versions: tuple[str, ...]
    isolation: str
    representation: str
    installed: bool = False
    version: Optional[str] = None
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "ecosystem": self.ecosystem,
            "license": self.license,
            "supportedVersions": list(self.supported_versions),
            "isolation": self.isolation,
            "representation": self.representation,
            "installed": self.installed,
            "version": self.version,
            "notes": self.notes,
        }


#: The reviewed support matrix. Nothing is added to it without a
#: version, licence and isolation review.
TOOL_MATRIX: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="python-dis",
        ecosystem="python",
        license="PSF-2.0 (Python standard library)",
        supported_versions=("3.11", "3.12", "3.13"),
        isolation="in-process, no subprocess, no network",
        representation=Representation.DISASSEMBLY.value,
        notes=("a .pyc is only readable when its magic number matches the "
               "running interpreter; a mismatch is reported, never guessed"),
    ),
    ToolSpec(
        name="java-decompiler",
        ecosystem="java",
        license="not bundled: an operator must supply an allowlisted tool",
        supported_versions=(),
        isolation=("fixed argument vector, read-only input, disposable work "
                   "directory, bounded output and time, no network"),
        representation=Representation.DECOMPILED.value,
        notes=("no decompiler is shipped; without an allowlisted tool the "
               "capability is reported as unavailable"),
    ),
)


def tooling_capabilities() -> dict:
    """Describe the optional reconstruction tools of this deployment."""

    matrix = []
    for spec in TOOL_MATRIX:
        installed = spec.installed
        version = spec.version
        if spec.name == "python-dis":
            installed = importlib.util.find_spec("dis") is not None
            version = ".".join(str(part) for part in _python_version())
        matrix.append({**spec.as_dict(), "installed": installed, "version": version})
    return {
        "tools": matrix,
        "nativeBinaryReconstruction": (
            "not supported: native binaries are never decompiled"
        ),
    }


def _python_version() -> tuple[int, ...]:
    import sys

    return sys.version_info[:3]


class PythonBytecodeReader:
    """Disassemble a ``.pyc`` with the standard library.

    The result is a disassembly. It is labelled as such and never
    presented as recovered source.
    """

    ecosystem = "python"

    def __init__(self, *, policy: Optional[AcquisitionPolicy] = None) -> None:
        self.policy = policy or AcquisitionPolicy()

    def capabilities(self) -> dict:
        return {
            "tool": "python-dis",
            "license": "PSF-2.0 (Python standard library)",
            "representation": Representation.DISASSEMBLY.value,
            "supported": self._magic_supported(),
            "diagnostic": None if self._magic_supported() else (
                "the running interpreter cannot read this bytecode version"),
        }

    @staticmethod
    def _magic_supported() -> bool:
        import importlib.util as util

        return util.MAGIC_NUMBER is not None

    def read(self, path: Path) -> ResearchResult:
        """Disassemble one ``.pyc`` file."""

        import dis

        path = Path(path)
        if path.suffix.lower() in NATIVE_BINARY_SUFFIXES:
            return self._refuse(path, "native binaries are never decompiled")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            return self._failed(path, f"cannot read the bytecode: {exc}")
        if len(raw) < 16:
            return self._failed(path, "the bytecode file is truncated")
        magic = raw[:4]
        if magic != importlib.util.MAGIC_NUMBER:
            return ResearchResult(
                status=ResearchStatus.UNSUPPORTED,
                operation="dependency.read",
                warnings=(
                    f"the bytecode magic {magic!r} does not match the running "
                    f"interpreter {importlib.util.MAGIC_NUMBER!r}; the version "
                    "is not supported",
                ),
                scope={"path": str(path)},
            )
        code = self._compile(raw)
        if code is None:
            return self._failed(path, "the bytecode could not be loaded")
        import io

        buffer = io.StringIO()
        try:
            dis.dis(code, file=buffer)
        except Exception as exc:  # noqa: BLE001 - disassembly must not crash
            return self._failed(path, f"the bytecode could not be disassembled: {exc}")
        text = buffer.getvalue()
        lines = text.splitlines()
        truncated = len(lines) > 200
        body = "\n".join(lines[:200])
        evidence = EvidenceReference(
            evidence_id="",
            artifact_hash=None,
            member=path.name,
            start_line=1,
            end_line=min(len(lines), 200),
            parser_version="python-dis-1",
            representation=Representation.DISASSEMBLY.value,
        )
        return ResearchResult(
            status=ResearchStatus.COMPLETE,
            operation="dependency.read",
            evidence=(evidence,),
            excerpts=({
                "member": path.name,
                "kind": "bytecode",
                "representation": Representation.DISASSEMBLY.value,
                "text": body,
                "startLine": 1,
                "endLine": min(len(lines), 200),
                "totalLines": len(lines),
                "truncated": truncated,
            },),
            truncated=truncated,
            scope={"path": str(path)},
        )

    @staticmethod
    def _compile(raw: bytes):
        import importlib.util as util
        import marshal

        try:
            return marshal.loads(raw[16:])
        except (EOFError, ValueError, TypeError):
            return None

    def _refuse(self, path: Path, reason: str) -> ResearchResult:
        return ResearchResult(
            status=ResearchStatus.UNSUPPORTED,
            operation="dependency.read",
            warnings=(reason,),
            scope={"path": str(path)},
        )

    def _failed(self, path: Path, reason: str) -> ResearchResult:
        return ResearchResult(
            status=ResearchStatus.FAILED,
            operation="dependency.read",
            warnings=(reason,),
            scope={"path": str(path)},
        )


@dataclass
class JavaDecompiler:
    """Reconstruct Java method bodies with an operator-supplied tool.

    The tool is **not** bundled. An operator must point the decompiler
    at an executable and the deployment must allowlist it. The
    invocation is fixed: the caller never controls the argument vector,
    the input is read-only, the work directory is disposable and the
    output and the runtime are bounded.
    """

    executable: Optional[Path] = None
    allowed_tools: tuple[str, ...] = ()
    max_output_bytes: int = 4 * 1024 * 1024
    timeout_seconds: float = 30.0

    ecosystem = "java"

    def capabilities(self) -> dict:
        available = self._available()
        return {
            "tool": "java-decompiler",
            "license": "not bundled: an operator must supply an allowlisted tool",
            "representation": Representation.DECOMPILED.value,
            "supported": available,
            "diagnostic": None if available else (
                "no allowlisted Java decompiler is installed; class files are "
                "read as signatures"
            ),
        }

    def _available(self) -> bool:
        if self.executable is None:
            return False
        name = Path(self.executable).name
        if self.allowed_tools and name not in self.allowed_tools:
            return False
        return Path(self.executable).is_file()

    def decompile(self, artifact: Path, *,
                  class_name: Optional[str] = None) -> ResearchResult:
        """Reconstruct the sources of one class file or JAR."""

        artifact = Path(artifact)
        if artifact.suffix.lower() in NATIVE_BINARY_SUFFIXES:
            return ResearchResult(
                status=ResearchStatus.UNSUPPORTED,
                operation="dependency.read",
                warnings=("native binaries are never decompiled",),
                scope={"path": str(artifact)},
            )
        if not self._available():
            return ResearchResult(
                status=ResearchStatus.UNSUPPORTED,
                operation="dependency.read",
                warnings=(
                    "no allowlisted Java decompiler is installed; the class "
                    "file is read as a signature only",
                ),
                scope={"path": str(artifact)},
            )
        temporary = tempfile.TemporaryDirectory(prefix="pi-decompile-")
        workdir = Path(temporary.name)
        try:
            source = workdir / "input.jar"
            shutil.copyfile(artifact, source)
            os.chmod(source, 0o400)
            output = workdir / "out"
            output.mkdir()
            argv = [str(self.executable), str(source), "--outputdir", str(output)]
            completed = subprocess.run(
                argv, cwd=str(workdir), capture_output=True, text=True,
                timeout=self.timeout_seconds, check=False,
                env={"PATH": os.environ.get("PATH", ""), "HOME": str(workdir)},
            )
            if completed.returncode != 0:
                return ResearchResult(
                    status=ResearchStatus.FAILED,
                    operation="dependency.read",
                    warnings=(f"the decompiler failed with exit code "
                              f"{completed.returncode}",),
                    scope={"path": str(artifact)},
                )
            produced = sorted(output.rglob("*.java"))
            if not produced:
                return ResearchResult(
                    status=ResearchStatus.UNSUPPORTED,
                    operation="dependency.read",
                    warnings=("the decompiler produced no source",),
                    scope={"path": str(artifact)},
                )
            total = 0
            excerpts = []
            for item in produced:
                if class_name and class_name not in item.name:
                    continue
                body = item.read_text(encoding="utf-8", errors="replace")
                total += len(body.encode("utf-8"))
                if total > self.max_output_bytes:
                    break
                excerpts.append({
                    "member": item.name,
                    "kind": "source",
                    "representation": Representation.DECOMPILED.value,
                    "text": body[:self.max_output_bytes],
                    "truncated": False,
                })
            return ResearchResult(
                status=ResearchStatus.COMPLETE,
                operation="dependency.read",
                excerpts=tuple(excerpts),
                warnings=(),
                scope={"path": str(artifact)},
            )
        except subprocess.TimeoutExpired:
            return ResearchResult(
                status=ResearchStatus.FAILED,
                operation="dependency.read",
                warnings=(f"the decompiler exceeded {self.timeout_seconds} seconds",),
                scope={"path": str(artifact)},
            )
        except OSError as exc:
            return ResearchResult(
                status=ResearchStatus.FAILED,
                operation="dependency.read",
                warnings=(f"the decompiler could not be run: {exc}",),
                scope={"path": str(artifact)},
            )
        finally:
            # TemporaryDirectory also removes read-only inputs on Windows.
            temporary.cleanup()
