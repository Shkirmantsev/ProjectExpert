"""Tests for the artifact acquisition, the safe inspection and the
bounded library reads.

The acquisition tests never reach a registry: the fetcher is a
deterministic stand-in, so the policy, the integrity check, the cache
and the concurrency are all exercised offline.
"""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pi_platform.adapters.research.acquisition import (
    AcquisitionError,
    AcquisitionTimeout,
    ArtifactAcquirer,
    ArtifactLocation,
    FetchResponse,
    IntegrityError,
    PypiLocator,
)
from pi_platform.adapters.research.artifacts import (
    ArchiveInspection,
    ArtifactError,
    UnsafeArchiveMember,
    inspect_archive,
    safe_member_path,
)
from pi_platform.adapters.research.sources import (
    LibraryReader,
    read_member,
    read_source_map,
    select_source_files,
)
from pi_platform.adapters.research.tooling import (
    NATIVE_BINARY_SUFFIXES,
    JavaDecompiler,
    PythonBytecodeReader,
    tooling_capabilities,
)
from pi_platform.core.research.policy import AcquisitionPolicy
from pi_platform.core.research.records import (
    ResearchDenied,
    ResearchStatus,
)
from pi_platform.core.research.service import DependencyResearchService
from pi_platform.ports.research.dependency_research import (
    DependencyAcquireRequest,
    DependencyReadRequest,
    DependencyTreeRequest,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeFetcher:
    """A deterministic stand-in for an HTTP fetcher."""

    def __init__(self, responses=None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, int, float]] = []
        self.lock = threading.Lock()

    def fetch(self, url: str, *, max_bytes: int, timeout: float) -> FetchResponse:
        with self.lock:
            self.calls.append((url, max_bytes, timeout))
            handler = self.responses.get(url)
        if handler is None:
            return FetchResponse(status=404, chain=(url,))
        if callable(handler):
            return handler(url)
        return handler


def wheel_bytes(members: dict[str, str], compress: bool = False) -> bytes:
    buffer = io.BytesIO()
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(buffer, "w", compression=mode) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return buffer.getvalue()


def tar_bytes(members: dict[str, str], links=None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, body in members.items():
            info = tarfile.TarInfo(name)
            payload = body.encode("utf-8")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE if target.startswith("/") is False and \
                target.startswith("..") is False and "/" not in target else tarfile.SYMTYPE
            info.linkname = target
            archive.addfile(info)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Safe inspection
# ---------------------------------------------------------------------------


class ArchiveInspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = __import__("tempfile").TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name: str, payload: bytes) -> Path:
        path = self.root / name
        path.write_bytes(payload)
        return path

    def test_a_wheel_is_inspected_with_its_member_hashes(self):
        path = self.write("demo-1.0-py3-none-any.whl", wheel_bytes({
            "demo/__init__.py": "VALUE = 1\n",
            "demo-1.0.dist-info/METADATA": "Name: demo\nVersion: 1.0\n",
        }))
        inspection = inspect_archive(path)
        self.assertEqual(inspection.kind, "zip")
        names = {member.path for member in inspection.members}
        self.assertIn("demo/__init__.py", names)
        member = inspection.member("demo/__init__.py")
        self.assertEqual(member.size, len("VALUE = 1\n"))
        self.assertEqual(len(member.sha256), 64)

    def test_a_traversal_member_is_rejected(self):
        path = self.write("evil.whl", wheel_bytes({"../escape.py": "x = 1\n"}))
        with self.assertRaises(UnsafeArchiveMember):
            inspect_archive(path)

    def test_an_absolute_member_is_rejected(self):
        path = self.write("evil.whl", wheel_bytes({"/etc/passwd": "x\n"}))
        with self.assertRaises(UnsafeArchiveMember):
            inspect_archive(path)

    def test_a_symlink_that_escapes_is_rejected(self):
        path = self.write("evil.tar", tar_bytes(
            {"pkg/__init__.py": "x = 1\n"},
            links={"pkg/escape.py": "../../etc/passwd"}))
        with self.assertRaises(UnsafeArchiveMember):
            inspect_archive(path)

    def test_an_oversized_member_is_rejected(self):
        policy = AcquisitionPolicy(max_compressed_bytes=64)
        path = self.write("big.whl", wheel_bytes({"pkg/big.py": "x" * 4096}))
        with self.assertRaises(ArtifactError):
            inspect_archive(path, policy=policy)

    def test_too_many_members_are_rejected(self):
        policy = AcquisitionPolicy(max_members=2)
        path = self.write("many.whl", wheel_bytes({
            "a.py": "a", "b.py": "b", "c.py": "c", "d.py": "d"}))
        with self.assertRaises(ArtifactError):
            inspect_archive(path, policy=policy)

    def test_a_compression_bomb_is_rejected(self):
        policy = AcquisitionPolicy(max_compression_ratio=2)
        path = self.write("bomb.whl", wheel_bytes(
            {"big.txt": "0" * (1024 * 1024)}, compress=True))
        with self.assertRaises(ArtifactError):
            inspect_archive(path, policy=policy)

    def test_the_member_path_validation_is_the_single_gate(self):
        with self.assertRaises(UnsafeArchiveMember):
            safe_member_path("../x")
        with self.assertRaises(UnsafeArchiveMember):
            safe_member_path("/x")
        with self.assertRaises(UnsafeArchiveMember):
            safe_member_path("a\\b")
        self.assertEqual(str(safe_member_path("a/b.py")), "a/b.py")


# ---------------------------------------------------------------------------
# Acquisition
# ---------------------------------------------------------------------------


class AcquisitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = __import__("tempfile").TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.payload = wheel_bytes({"demo/__init__.py": "VALUE = 1\n"})
        import hashlib

        self.digest = hashlib.sha256(self.payload).hexdigest()

    def acquirer(self, fetcher, **kwargs) -> ArtifactAcquirer:
        policy = AcquisitionPolicy(
            allowed_sources=("pypi",),
            allowed_hosts=("files.pythonhosted.org", "pypi.org"),
            **kwargs,
        )
        return ArtifactAcquirer(cache_root=self.cache, fetcher=fetcher,
                                policy=policy)

    def index_response(self, url: str, filename: str = "demo-1.0-py3-none-any.whl"):
        payload = {"urls": [{
            "url": f"https://files.pythonhosted.org/packages/{filename}",
            "digests": {"sha256": self.digest},
            "packagetype": "bdist_wheel",
            "size": len(self.payload),
        }]}
        return FetchResponse(status=200, headers={"Content-Type": "application/json"},
                              body=json.dumps(payload).encode("utf-8"),
                              chain=(url,))

    def artifact_response(self, url: str):
        return FetchResponse(status=200, body=self.payload, chain=(url,))

    def test_an_offline_miss_is_reported(self):
        fetcher = FakeFetcher()
        acquirer = self.acquirer(fetcher)
        with self.assertRaises(AcquisitionError):
            acquirer.acquire(DependencyAcquireRequest(
                ecosystem="python", name="demo", version="1.0", source_id="pypi"))

    def test_an_unapproved_source_is_denied(self):
        acquirer = self.acquirer(FakeFetcher())
        with self.assertRaises(ResearchDenied):
            acquirer.acquire(DependencyAcquireRequest(
                ecosystem="python", name="demo", version="1.0", source_id="npm"))

    def test_an_integrity_failure_never_publishes_the_artifact(self):
        fetcher = FakeFetcher({
            "https://pypi.org/pypi/demo/1.0/json": self.index_response(
                "https://pypi.org/pypi/demo/1.0/json"),
            "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl":
                FetchResponse(status=200, body=b"tampered"),
        })
        acquirer = self.acquirer(fetcher)
        with self.assertRaises(IntegrityError):
            acquirer.acquire(DependencyAcquireRequest(
                ecosystem="python", name="demo", version="1.0", source_id="pypi"))
        published = list(self.cache.rglob("*.whl"))
        self.assertEqual(published, [], "a failed download must publish nothing")

    def test_a_download_that_leaves_the_approved_hosts_is_refused(self):
        fetcher = FakeFetcher({
            "https://pypi.org/pypi/demo/1.0/json": self.index_response(
                "https://pypi.org/pypi/demo/1.0/json"),
            "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl":
                FetchResponse(
                    status=200, body=self.payload,
                    chain=("https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl",
                           "https://evil.example.com/demo.whl")),
        })
        acquirer = self.acquirer(fetcher)
        with self.assertRaises(ResearchDenied):
            acquirer.acquire(DependencyAcquireRequest(
                ecosystem="python", name="demo", version="1.0", source_id="pypi"))

    def test_a_timeout_is_reported(self):
        def timeout(url):
            raise AcquisitionTimeout("the registry did not answer")

        fetcher = FakeFetcher({
            "https://pypi.org/pypi/demo/1.0/json": timeout,
        })
        acquirer = self.acquirer(fetcher)
        with self.assertRaises(AcquisitionTimeout):
            acquirer.acquire(DependencyAcquireRequest(
                ecosystem="python", name="demo", version="1.0", source_id="pypi"))

    def test_the_cache_is_reused_instead_of_downloading_again(self):
        fetcher = FakeFetcher({
            "https://pypi.org/pypi/demo/1.0/json": self.index_response(
                "https://pypi.org/pypi/demo/1.0/json"),
            "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl":
                self.artifact_response(
                    "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl"),
        })
        acquirer = self.acquirer(fetcher)
        first = acquirer.acquire(DependencyAcquireRequest(
            ecosystem="python", name="demo", version="1.0", source_id="pypi"))
        self.assertFalse(first.detail["artifact"]["reused"])
        downloads = [call for call in fetcher.calls if "files.pythonhosted" in call[0]]
        self.assertEqual(len(downloads), 1)
        second = acquirer.acquire(DependencyAcquireRequest(
            ecosystem="python", name="demo", version="1.0", source_id="pypi"))
        self.assertTrue(second.detail["artifact"]["reused"])
        downloads = [call for call in fetcher.calls if "files.pythonhosted" in call[0]]
        self.assertEqual(len(downloads), 1, "the cached artifact must be reused")

    def test_concurrent_requests_publish_one_artifact(self):
        fetcher = FakeFetcher({
            "https://pypi.org/pypi/demo/1.0/json": self.index_response(
                "https://pypi.org/pypi/demo/1.0/json"),
            "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl":
                self.artifact_response(
                    "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl"),
        })
        acquirer = self.acquirer(fetcher)
        results = []
        errors = []

        def worker():
            try:
                results.append(acquirer.acquire(DependencyAcquireRequest(
                    ecosystem="python", name="demo", version="1.0",
                    source_id="pypi")))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 4)
        published = list(self.cache.rglob("*.whl"))
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].read_bytes(), self.payload)

    def test_the_acquired_artifact_becomes_readable_through_the_service(self):
        fetcher = FakeFetcher({
            "https://pypi.org/pypi/demo/1.0/json": self.index_response(
                "https://pypi.org/pypi/demo/1.0/json"),
            "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl":
                self.artifact_response(
                    "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl"),
        })
        acquirer = self.acquirer(fetcher)
        reader = LibraryReader()
        service = DependencyResearchService(
            project_root=self.root, acquirer=acquirer, reader=reader)
        acquired = service.acquire(DependencyAcquireRequest(
            ecosystem="python", name="demo", version="1.0", source_id="pypi"))
        self.assertEqual(acquired.status, ResearchStatus.COMPLETE)
        self.assertTrue(acquired.detail["members"])
        reference = next(iter(reader.index(Path(
            acquired.detail["artifact"]["path"])).files))
        read = service.read(DependencyReadRequest(
            evidence_ref="", artifact=acquired.detail["artifact"]["path"],
            member=reference.path))
        self.assertEqual(read.status, ResearchStatus.COMPLETE)
        self.assertEqual(read.excerpts[0]["representation"], "source")
        self.assertIn("VALUE = 1", read.excerpts[0]["text"])


# ---------------------------------------------------------------------------
# Bounded library reads
# ---------------------------------------------------------------------------


class LibraryReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = __import__("tempfile").TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def wheel(self, members: dict[str, str]) -> Path:
        path = self.root / "demo-1.0-py3-none-any.whl"
        path.write_bytes(wheel_bytes(members))
        return path

    def test_the_source_is_preferred_over_the_bytecode(self):
        path = self.wheel({
            "demo/__init__.py": "VALUE = 1\n",
            "demo/__init__.pyc": "\x00" * 32,
            "demo/api.pyi": "def api() -> None: ...\n",
        })
        index = select_source_files(inspect_archive(path))
        kinds = {item.path: item.kind for item in index.files}
        self.assertEqual(kinds["demo/__init__.py"], "source")
        self.assertEqual(kinds["demo/api.pyi"], "stub")
        self.assertEqual(kinds["demo/__init__.pyc"], "bytecode")

    def test_a_read_is_bounded_by_lines_and_bytes(self):
        body = "\n".join(f"line {index}" for index in range(500))
        path = self.wheel({"demo/big.py": body})
        excerpt = read_member(path, "demo/big.py", max_lines=10, max_bytes=4096)
        self.assertEqual(excerpt["totalLines"], 500)
        self.assertTrue(excerpt["truncated"])
        self.assertLessEqual(len(excerpt["text"].splitlines()), 10)
        excerpt = read_member(path, "demo/big.py", max_lines=500, max_bytes=64)
        self.assertLessEqual(len(excerpt["text"].encode("utf-8")), 64)

    def test_a_read_reports_the_representation_it_really_has(self):
        path = self.wheel({"demo/api.pyi": "def api() -> None: ...\n"})
        excerpt = read_member(path, "demo/api.pyi")
        self.assertEqual(excerpt["representation"], "stub")

    def test_a_line_range_is_honoured(self):
        path = self.wheel({"demo/x.py": "a\nb\nc\nd\n"})
        excerpt = read_member(path, "demo/x.py", start_line=2, end_line=3)
        self.assertEqual(excerpt["text"], "b\nc")
        self.assertEqual(excerpt["startLine"], 2)
        self.assertEqual(excerpt["endLine"], 3)

    def test_a_valid_source_map_with_bodies_is_read(self):
        payload = json.dumps({
            "version": 3,
            "file": "out.js",
            "sources": ["../src/original.ts"],
            "sourcesContent": ["export const original = 1;\n"],
        })
        path = self.wheel({"dist/out.js.map": payload})
        parsed = read_source_map(path, "dist/out.js.map")
        self.assertTrue(parsed["valid"])
        self.assertTrue(parsed["hasBodies"])
        self.assertIn("original", parsed["contents"][0]["body"])

    def test_an_invalid_source_map_is_reported_as_invalid(self):
        path = self.wheel({"dist/out.js.map": "{not json"})
        parsed = read_source_map(path, "dist/out.js.map")
        self.assertFalse(parsed["valid"])
        self.assertIn("invalid source map", parsed["reason"])

    def test_a_source_map_without_bodies_reports_the_missing_body(self):
        payload = json.dumps({"version": 3, "sources": ["../src/original.ts"],
                              "sourcesContent": [None]})
        path = self.wheel({"dist/out.js.map": payload})
        parsed = read_source_map(path, "dist/out.js.map")
        self.assertTrue(parsed["valid"])
        self.assertFalse(parsed["hasBodies"])
        self.assertIsNone(parsed["contents"][0]["body"])

    def test_a_symbol_narrows_the_excerpt(self):
        body = "def first():\n    return 1\n\n\ndef second():\n    return 2\n"
        path = self.wheel({"demo/m.py": body})
        reader = LibraryReader()
        result = reader.read(path, "demo/m.py", symbol="second")
        excerpt = result.excerpts[0]
        self.assertTrue(excerpt["symbolFound"])
        self.assertIn("def second", excerpt["text"])
        self.assertNotIn("def first", excerpt["text"])

    def test_a_minified_bundle_is_labelled_generated(self):
        bundle = "!function(e,t){\"use strict\";function n(r){return r.x}" \
                 + "y" * 4000 + ";\n" * 2
        path = self.wheel({"dist/bundle.js": bundle})
        excerpt = read_member(path, "dist/bundle.js")
        self.assertEqual(excerpt["representation"], "generated")
        self.assertTrue(excerpt["minified"])

    def test_a_readable_source_is_not_labelled_generated(self):
        path = self.wheel({"dist/app.js": "export function app() {\n  return 1;\n}\n"})
        excerpt = read_member(path, "dist/app.js")
        self.assertEqual(excerpt["representation"], "source")
        self.assertFalse(excerpt["minified"])

    def test_a_missing_member_is_reported_not_invented(self):
        path = self.wheel({"demo/__init__.py": "x = 1\n"})
        reader = LibraryReader()
        result = reader.read(path, "demo/missing.py")
        self.assertEqual(result.status, ResearchStatus.FAILED)
        self.assertTrue(result.warnings)


# ---------------------------------------------------------------------------
# Optional tooling
# ---------------------------------------------------------------------------


class ToolingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = __import__("tempfile").TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_the_support_matrix_states_the_licence_and_the_representation(self):
        capabilities = tooling_capabilities()
        names = {tool["name"] for tool in capabilities["tools"]}
        self.assertIn("python-dis", names)
        self.assertIn("java-decompiler", names)
        for tool in capabilities["tools"]:
            self.assertTrue(tool["license"])
            self.assertTrue(tool["representation"])
        self.assertIn("never decompiled", capabilities["nativeBinaryReconstruction"])

    def test_a_missing_java_decompiler_is_a_capability_diagnostic(self):
        decompiler = JavaDecompiler(executable=None)
        capabilities = decompiler.capabilities()
        self.assertFalse(capabilities["supported"])
        self.assertIn("no allowlisted Java decompiler", capabilities["diagnostic"])
        jar = self.root / "demo.jar"
        jar.write_bytes(b"PK\x03\x04")
        result = decompiler.decompile(jar)
        self.assertEqual(result.status, ResearchStatus.UNSUPPORTED)
        self.assertTrue(result.warnings)

    def test_a_decompiler_that_is_not_allowlisted_is_refused(self):
        tool = self.root / "cfr.jar"
        tool.write_text("not a real decompiler")
        decompiler = JavaDecompiler(executable=tool,
                                    allowed_tools=("procyon.jar",))
        self.assertFalse(decompiler.capabilities()["supported"])
        result = decompiler.decompile(self.root / "demo.jar")
        self.assertEqual(result.status, ResearchStatus.UNSUPPORTED)

    def test_a_bytecode_file_of_another_version_is_unsupported(self):
        reader = PythonBytecodeReader()
        path = self.root / "module.pyc"
        path.write_bytes(b"\x00\x00\x00\x00" + b"\x00" * 32)
        result = reader.read(path)
        self.assertEqual(result.status, ResearchStatus.UNSUPPORTED)
        self.assertTrue(any("not supported" in warning
                            for warning in result.warnings))

    def test_a_native_binary_is_never_decompiled(self):
        reader = PythonBytecodeReader()
        for suffix in NATIVE_BINARY_SUFFIXES:
            with self.subTest(suffix=suffix):
                path = self.root / f"module{suffix}"
                path.write_bytes(b"\x7fELF")
                result = reader.read(path)
                self.assertEqual(result.status, ResearchStatus.UNSUPPORTED)
                self.assertTrue(any("native binaries" in warning
                                    for warning in result.warnings))

    def test_the_current_bytecode_version_is_read_as_a_disassembly(self):
        import importlib.util
        import marshal

        reader = PythonBytecodeReader()
        code = compile("def demo():\n    return 1\n", "demo.py", "exec")
        # The CPython header is magic(4) + flags(4) + mtime(4) + size(4).
        header = importlib.util.MAGIC_NUMBER + (0).to_bytes(4, "little") \
            + (0).to_bytes(4, "little") + (0).to_bytes(4, "little")
        payload = header + marshal.dumps(code)
        path = self.root / "demo.pyc"
        path.write_bytes(payload)
        result = reader.read(path)
        self.assertEqual(result.status, ResearchStatus.COMPLETE)
        self.assertEqual(result.excerpts[0]["representation"], "disassembly")
        self.assertIn("demo", result.excerpts[0]["text"])

    def test_an_allowlisted_decompiler_produces_a_bounded_reconstruction(self):
        """The invocation contract of the optional decompiler.

        The tool is a stub: it proves the fixed argument vector, the
        read-only input, the disposable work directory and the
        provenance of the result, not the quality of a real
        decompiler.
        """

        tool = self.root / "stub-decompiler.py"
        tool.write_text(
            "import pathlib, sys\n"
            "source, flag, output = sys.argv[1:]\n"
            "assert flag == '--outputdir'\n"
            "assert pathlib.Path(source).read_bytes() == b'PK\\x03\\x04'\n"
            "(pathlib.Path(output) / 'Demo.java').write_text(\n"
            "    'public class Demo { public int value() { return 1; } }\\n')\n",
            encoding="utf-8",
        )
        jar = self.root / "demo.jar"
        jar.write_bytes(b"PK\x03\x04")
        decompiler = JavaDecompiler(executable=tool,
                                    allowed_tools=(tool.name,))
        self.assertTrue(decompiler.capabilities()["supported"])
        run = subprocess.run
        workdirs = []

        def run_python_fixture(argv, **kwargs):
            # Windows does not execute shebang scripts. Use this interpreter
            # at the process boundary while checking the adapter's real argv.
            workdir = Path(kwargs["cwd"])
            workdirs.append(workdir)
            source = workdir / "input.jar"
            self.assertEqual(argv, [str(tool), str(source), "--outputdir",
                                    str(workdir / "out")])
            self.assertFalse(source.stat().st_mode & stat.S_IWUSR)
            self.assertEqual(kwargs["timeout"], decompiler.timeout_seconds)
            return run([sys.executable, *argv], **kwargs)

        with patch("pi_platform.adapters.research.tooling.subprocess.run",
                   side_effect=run_python_fixture) as invoke:
            result = decompiler.decompile(jar)
        invoke.assert_called_once()
        self.assertFalse(workdirs[0].exists(), "disposable input must be removed")
        self.assertEqual(jar.read_bytes(), b"PK\x03\x04")
        self.assertEqual(result.status, ResearchStatus.COMPLETE)
        self.assertEqual(result.excerpts[0]["representation"], "decompiled")
        self.assertIn("public class Demo", result.excerpts[0]["text"])

    def test_failed_decompiler_removes_its_read_only_input(self):
        tool = self.root / "stub-decompiler"
        tool.touch()
        jar = self.root / "demo.jar"
        jar.write_bytes(b"PK\x03\x04")
        decompiler = JavaDecompiler(executable=tool, allowed_tools=(tool.name,))
        for failure in (OSError("cannot launch"),
                        subprocess.TimeoutExpired(str(tool), 30)):
            with self.subTest(failure=type(failure).__name__):
                workdirs = []

                def fail(argv, **kwargs):
                    workdir = Path(kwargs["cwd"])
                    workdirs.append(workdir)
                    self.assertFalse((workdir / "input.jar").stat().st_mode & stat.S_IWUSR)
                    raise failure

                with patch("pi_platform.adapters.research.tooling.subprocess.run",
                           side_effect=fail):
                    result = decompiler.decompile(jar)
                self.assertEqual(result.status, ResearchStatus.FAILED)
                self.assertFalse(workdirs[0].exists())
                self.assertEqual(jar.read_bytes(), b"PK\x03\x04")

    def test_the_optional_node_parser_is_declared_as_an_extra(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("node = [", text)
        self.assertIn("tree-sitter-javascript", text)
        self.assertIn("tree-sitter-typescript", text)


if __name__ == "__main__":
    unittest.main()
