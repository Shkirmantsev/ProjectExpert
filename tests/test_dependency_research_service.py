"""Tests for the shared dependency research service and its adapters.

The suite is fixture-driven: every lock, manifest and archive is
written into a temporary project, so the assertions are about real
bytes and never about a recorded expectation.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from pi_platform.adapters.research.java_ecosystem import JavaEcosystemAdapter
from pi_platform.adapters.research.lock_ingest import (
    NodeLockAdapter,
    NodeManifestAdapter,
    PythonLockAdapter,
)
from pi_platform.adapters.research.node_ecosystem import NodeEcosystemAdapter
from pi_platform.adapters.research.node_locks import (
    SUPPORTED_NPM_LOCK_VERSIONS,
    SUPPORTED_PNPM_LOCK_VERSIONS,
    SUPPORTED_YARN_BERRY_VERSIONS,
)
from pi_platform.adapters.research.node_sources import parser_status
from pi_platform.adapters.research.python_ecosystem import PythonEcosystemAdapter
from pi_platform.adapters.research.python_locks import (
    SUPPORTED_POETRY_LOCK_VERSIONS,
    SUPPORTED_UV_LOCK_VERSIONS,
)
from pi_platform.core.canonical.content_address import content_address_bytes
from pi_platform.core.canonical.value_types import Source
from pi_platform.core.research.policy import AcquisitionPolicy, ResearchLimits
from pi_platform.core.research.records import (
    Completeness,
    InvalidResearchRequest,
    ResearchDenied,
    ResearchStatus,
    ResearchUnsupported,
    StaleResearchCursor,
)
from pi_platform.core.research.service import DependencyResearchService
from pi_platform.ports.ingest.source_adapter import SourceContentFamily
from pi_platform.ports.research.dependency_research import (
    DependencyAcquireRequest,
    DependencyTreeRequest,
)

ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _imported_modules(path: Path) -> set[str]:
    """Return the top-level modules a Python file imports."""

    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


class ProjectFixture(unittest.TestCase):
    """A disposable project directory."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir(parents=True)

    def source(self, path: Path, family: SourceContentFamily) -> Source:
        raw = path.read_bytes()
        return Source(
            content_address_bytes(raw),
            str(path),
            family.value,
            content_address_bytes(raw),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

UV_LOCK = """\
version = 1
revision = 1
requires-python = ">=3.11"

[[package]]
name = "requests"
version = "2.32.3"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "certifi" },
    { name = "urllib3", marker = "python_version >= '3.9'" },
]

[[package]]
name = "certifi"
version = "2024.8.30"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "urllib3"
version = "2.2.3"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "demo"
version = "0.1.0"
source = { editable = "." }
dependencies = [
    { name = "requests" },
]
"""

UV_LOCK_EXTRAS = """\
version = 1
revision = 1

[[package]]
name = "demo"
version = "0.1.0"
source = { editable = "." }

[package.optional-dependencies]
cli = [{ name = "click" }]

[[package]]
name = "click"
version = "8.1.7"
source = { registry = "https://pypi.org/simple" }
"""

POETRY_LOCK = """\
[[package]]
name = "requests"
version = "2.32.3"
description = "HTTP for humans"
category = "main"
optional = false
python-versions = ">=3.7"

[package.dependencies]
certifi = ">=2017.4.17"

[package.extras]
socks = ["PySocks (>=1.5.6,!=1.5.7)"]

[[package]]
name = "pytest"
version = "8.3.3"
description = "testing"
category = "dev"
optional = false
python-versions = ">=3.8"

[metadata]
lock-version = "2.0"
python-versions = "^3.11"
content-hash = "abc"
"""

NPM_LOCK_V3 = {
    "name": "root-app",
    "version": "1.0.0",
    "lockfileVersion": 3,
    "requires": True,
    "packages": {
        "": {
            "name": "root-app",
            "version": "1.0.0",
            "dependencies": {"lodash": "^4.17.21", "aliased": "npm:real-pkg@^1.0.0"},
            "devDependencies": {"typescript": "^5.0.0"},
            "optionalDependencies": {"fsevents": "^2.3.0"},
        },
        "node_modules/lodash": {"version": "4.17.21", "integrity": "sha512-a"},
        "node_modules/aliased": {"name": "real-pkg", "version": "1.2.0"},
        "node_modules/typescript": {"version": "5.3.3", "dev": True},
        "node_modules/fsevents": {"version": "2.3.3", "optional": True},
        "node_modules/left-pad": {"version": "1.3.0"},
        "node_modules/a/node_modules/left-pad": {"version": "2.0.0"},
        "node_modules/a": {"version": "1.0.0", "dependencies": {"left-pad": "^2.0.0"}},
    },
}

NPM_LOCK_V1 = {
    "name": "legacy-app",
    "version": "0.1.0",
    "lockfileVersion": 1,
    "dependencies": {
        "lodash": {
            "version": "4.17.20",
            "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.20.tgz",
            "integrity": "sha512-b",
        },
    },
}

PNPM_LOCK_V9 = """\
lockfileVersion: '9.0'

settings:
  autoInstallPeers: true

importers:
  .:
    dependencies:
      lodash:
        specifier: ^4.17.21
        version: 4.17.21

packages:

  lodash@4.17.21:
    resolution: {integrity: sha512-c}

snapshots:

  lodash@4.17.21: {}
"""

YARN_CLASSIC_LOCK = """\
# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.
# yarn lockfile v1


lodash@^4.17.21:
  version "4.17.21"
  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz#abc"
  integrity sha512-d
"""


# ---------------------------------------------------------------------------
# Limits, policy and cursors
# ---------------------------------------------------------------------------


class ResearchLimitsTests(unittest.TestCase):
    def test_negative_and_unbounded_requests_are_rejected(self):
        for kwargs in ({"max_nodes": -1}, {"max_depth": -5},
                       {"max_code_bytes": -1}, {"timeout_seconds": 0},
                       {"timeout_seconds": -1.0}):
            with self.subTest(**kwargs):
                with self.assertRaises(InvalidResearchRequest):
                    ResearchLimits(**kwargs)

    def test_a_request_above_the_hard_maximum_is_clamped(self):
        limits = ResearchLimits(max_nodes=10_000, max_depth=1_000,
                                max_symbol_hits=10_000, max_code_lines=10_000,
                                max_code_bytes=10_000_000, timeout_seconds=10_000)
        self.assertEqual(limits.max_nodes, ResearchLimits.HARD_MAX_NODES)
        self.assertEqual(limits.max_depth, ResearchLimits.HARD_MAX_DEPTH)
        self.assertEqual(limits.max_symbol_hits, ResearchLimits.HARD_MAX_SYMBOL_HITS)
        self.assertEqual(limits.max_code_lines, ResearchLimits.HARD_MAX_CODE_LINES)
        self.assertEqual(limits.max_code_bytes, ResearchLimits.HARD_MAX_CODE_BYTES)
        self.assertEqual(limits.timeout_seconds,
                         ResearchLimits.HARD_MAX_TIMEOUT_SECONDS)

    def test_the_effective_limits_are_reported(self):
        limits = ResearchLimits(max_nodes=7)
        self.assertEqual(limits.as_dict()["maxNodes"], 7)
        self.assertIn("maxNodes=7", limits.fingerprint)

    def test_the_acquisition_policy_is_bounded(self):
        policy = AcquisitionPolicy(allowed_sources=("pypi",))
        self.assertTrue(policy.allows("pypi"))
        self.assertFalse(policy.allows("npm"))
        with self.assertRaises(InvalidResearchRequest):
            AcquisitionPolicy(max_members=0)
        clamped = AcquisitionPolicy(max_expanded_bytes=10 ** 12,
                                    timeout_seconds=10_000)
        self.assertEqual(clamped.max_expanded_bytes,
                         AcquisitionPolicy.HARD_MAX_EXPANDED_BYTES)
        self.assertEqual(clamped.timeout_seconds,
                         AcquisitionPolicy.HARD_MAX_TIMEOUT_SECONDS)


class ResearchServiceContractTests(ProjectFixture):
    def service(self, **kwargs) -> DependencyResearchService:
        return DependencyResearchService(
            project_root=self.root,
            adapters=[PythonEcosystemAdapter(), NodeEcosystemAdapter(),
                      JavaEcosystemAdapter()],
            **kwargs,
        )

    def test_an_unsupported_ecosystem_is_reported(self):
        with self.assertRaises(ResearchUnsupported):
            self.service().tree(DependencyTreeRequest(ecosystem="rust"))

    def test_a_project_without_dependencies_is_unavailable_not_empty_success(self):
        result = self.service().tree(DependencyTreeRequest(ecosystem="python"))
        self.assertEqual(result.status, ResearchStatus.UNAVAILABLE)
        self.assertEqual(result.completeness, Completeness.NONE)
        self.assertTrue(any("no supported lock file" in warning
                            for warning in result.warnings))

    def test_the_result_carries_the_effective_limits_and_the_scope(self):
        write(self.root / "uv.lock", UV_LOCK)
        result = self.service().tree(DependencyTreeRequest(
            ecosystem="python", limits=ResearchLimits(max_nodes=3)))
        self.assertEqual(result.limits["maxNodes"], 3)
        self.assertEqual(result.scope["ecosystem"], "python")
        self.assertIn("project", result.scope)

    def test_a_cursor_is_bound_to_the_snapshot_the_query_and_the_policy(self):
        write(self.root / "uv.lock", UV_LOCK)
        service = self.service()
        truncated = service.tree(DependencyTreeRequest(
            ecosystem="python", limits=ResearchLimits(max_nodes=2)))
        self.assertTrue(truncated.truncated)
        self.assertTrue(truncated.cursor)
        # Another policy is a different traversal.
        with self.assertRaises(StaleResearchCursor):
            service.tree(DependencyTreeRequest(
                ecosystem="python", limits=ResearchLimits(max_nodes=2, max_depth=3),
                cursor=truncated.cursor))
        # Another query is a different traversal.
        with self.assertRaises(StaleResearchCursor):
            service.tree(DependencyTreeRequest(
                ecosystem="python", limits=ResearchLimits(max_nodes=2),
                package="requests", cursor=truncated.cursor))
        # A changed project is a different snapshot.
        write(self.root / "uv.lock", UV_LOCK.replace("2.32.3", "2.32.4"))
        with self.assertRaises(StaleResearchCursor):
            service.tree(DependencyTreeRequest(
                ecosystem="python", limits=ResearchLimits(max_nodes=2),
                cursor=truncated.cursor))

    def test_a_cursor_from_another_project_is_rejected(self):
        write(self.root / "uv.lock", UV_LOCK)
        service = self.service()
        truncated = service.tree(DependencyTreeRequest(
            ecosystem="python", limits=ResearchLimits(max_nodes=2)))
        other_root = Path(self.temp.name) / "other"
        other_root.mkdir()
        write(other_root / "uv.lock", UV_LOCK)
        other = DependencyResearchService(
            project_root=other_root, adapters=[PythonEcosystemAdapter()])
        with self.assertRaises(StaleResearchCursor):
            other.tree(DependencyTreeRequest(
                ecosystem="python", limits=ResearchLimits(max_nodes=2),
                cursor=truncated.cursor))

    def test_a_truncated_traversal_can_be_continued(self):
        write(self.root / "uv.lock", UV_LOCK)
        service = self.service()
        first = service.tree(DependencyTreeRequest(
            ecosystem="python", limits=ResearchLimits(max_nodes=2)))
        self.assertTrue(first.truncated)
        self.assertEqual(len(first.nodes), 2)
        second = service.tree(DependencyTreeRequest(
            ecosystem="python", limits=ResearchLimits(max_nodes=2),
            cursor=first.cursor))
        self.assertEqual(second.snapshot_id, first.snapshot_id)
        self.assertFalse(set(node.instance_id for node in first.nodes)
                         & set(node.instance_id for node in second.nodes))

    def test_a_malformed_cursor_is_rejected(self):
        write(self.root / "uv.lock", UV_LOCK)
        with self.assertRaises(InvalidResearchRequest):
            self.service().tree(DependencyTreeRequest(
                ecosystem="python", cursor="not-a-cursor"))

    def test_acquisition_without_an_acquirer_is_unsupported(self):
        service = self.service(acquisition_policy=AcquisitionPolicy(
            allowed_sources=("pypi",)))
        with self.assertRaises(ResearchUnsupported):
            service.acquire(DependencyAcquireRequest(
                ecosystem="python", name="requests", version="2.32.3",
                source_id="pypi"))

    def test_acquisition_outside_the_policy_is_denied(self):
        service = self.service(acquisition_policy=AcquisitionPolicy(
            allowed_sources=("pypi",)))
        with self.assertRaises(ResearchDenied):
            service.acquire(DependencyAcquireRequest(
                ecosystem="python", name="requests", version="2.32.3",
                source_id="npm"))

    def test_the_capabilities_describe_what_can_be_researched(self):
        capabilities = self.service().capabilities()
        self.assertIn("python", capabilities["ecosystems"])
        self.assertIn("node", capabilities["ecosystems"])
        self.assertIn("java", capabilities["ecosystems"])
        self.assertFalse(capabilities["acquisition"]["enabled"])


# ---------------------------------------------------------------------------
# Graph semantics
# ---------------------------------------------------------------------------


class DependencyGraphTests(ProjectFixture):
    def build(self, lock_text: str, **kwargs) -> DependencyResearchService:
        write(self.root / "uv.lock", lock_text)
        return DependencyResearchService(
            project_root=self.root, adapters=[PythonEcosystemAdapter()], **kwargs)

    def test_a_transitive_path_is_reported_with_its_why_path(self):
        result = self.build(UV_LOCK).tree(DependencyTreeRequest(ecosystem="python"))
        names = {node.package.name for node in result.nodes}
        self.assertIn("urllib3", names)
        why = result.detail["whyPaths"]
        target = next(node for node in result.nodes
                      if node.package.name == "urllib3")
        self.assertGreaterEqual(len(why[target.instance_id]), 3)

    def test_a_cycle_is_visited_once(self):
        cyclic = """\
version = 1
revision = 1

[[package]]
name = "a"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [{ name = "b" }]

[[package]]
name = "b"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [{ name = "a" }]
"""
        result = self.build(cyclic).tree(DependencyTreeRequest(ecosystem="python"))
        names = sorted(node.package.name for node in result.nodes)
        self.assertEqual(names, ["a", "b"])

    def test_the_depth_limit_truncates_and_says_so(self):
        result = self.build(UV_LOCK).tree(DependencyTreeRequest(
            ecosystem="python", limits=ResearchLimits(max_depth=1)))
        self.assertTrue(result.truncated)
        self.assertTrue(any("depth limit" in warning for warning in result.warnings))

    def test_the_node_limit_truncates_and_says_so(self):
        result = self.build(UV_LOCK).tree(DependencyTreeRequest(
            ecosystem="python", limits=ResearchLimits(max_nodes=2)))
        self.assertTrue(result.truncated)
        self.assertTrue(any("node limit" in warning for warning in result.warnings))
        self.assertEqual(result.status, ResearchStatus.PARTIAL)

    def test_two_versions_of_one_package_stay_distinct(self):
        two_versions = """\
version = 1
revision = 1

[[package]]
name = "demo"
version = "0.1.0"
source = { editable = "." }
dependencies = [{ name = "left-pad" }]

[[package]]
name = "left-pad"
version = "1.3.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "left-pad"
version = "2.0.0"
source = { registry = "https://pypi.org/simple" }
"""
        result = self.build(two_versions).tree(
            DependencyTreeRequest(ecosystem="python"))
        versions = sorted(node.package.resolved_version for node in result.nodes
                          if node.package.name == "left-pad")
        self.assertEqual(versions, ["1.3.0", "2.0.0"])

    def test_a_package_can_be_requested_by_name(self):
        result = self.build(UV_LOCK).tree(
            DependencyTreeRequest(ecosystem="python", package="requests"))
        names = {node.package.name for node in result.nodes}
        self.assertEqual(names, {"requests", "certifi", "urllib3"})


# ---------------------------------------------------------------------------
# Python ecosystem
# ---------------------------------------------------------------------------


class PythonEcosystemTests(ProjectFixture):
    def service(self, **kwargs) -> DependencyResearchService:
        return DependencyResearchService(
            project_root=self.root, adapters=[PythonEcosystemAdapter()], **kwargs)

    def test_the_uv_lock_projects_the_resolved_closure(self):
        write(self.root / "uv.lock", UV_LOCK)
        result = self.service().tree(DependencyTreeRequest(ecosystem="python"))
        by_name = {node.package.name: node for node in result.nodes}
        self.assertEqual(by_name["requests"].package.resolved_version, "2.32.3")
        self.assertEqual(by_name["demo"].package.source_kind, "editable")
        self.assertEqual(by_name["demo"].workspace, ".")
        marker = next(edge for edge in result.edges
                      if edge.condition and "python_version" in edge.condition)
        self.assertIsNotNone(marker.target_id)

    def test_the_poetry_lock_projects_groups_and_extras(self):
        write(self.root / "poetry.lock", POETRY_LOCK)
        result = self.service().tree(DependencyTreeRequest(ecosystem="python"))
        by_name = {node.package.name: node for node in result.nodes}
        self.assertEqual(by_name["pytest"].package.scope, "dev")
        self.assertEqual(by_name["requests"].package.resolved_version, "2.32.3")
        extra = next(edge for edge in result.edges
                     if edge.condition and edge.condition.startswith("extra="))
        self.assertIn("extra=socks", extra.condition)

    def test_the_uv_optional_dependencies_become_optional_edges(self):
        write(self.root / "uv.lock", UV_LOCK_EXTRAS)
        result = self.service().tree(DependencyTreeRequest(ecosystem="python"))
        optional = [edge for edge in result.edges if edge.kind == "optional"]
        self.assertTrue(optional)
        self.assertTrue(any("cli" in (edge.condition or "") for edge in optional))

    def test_an_unknown_lock_version_is_an_explicit_diagnostic(self):
        write(self.root / "uv.lock", "version = 99\nrevision = 1\n")
        result = self.service().tree(DependencyTreeRequest(ecosystem="python"))
        self.assertEqual(result.status, ResearchStatus.UNAVAILABLE)
        self.assertTrue(any("unsupported lock format" in warning
                            for warning in result.warnings))

    def test_an_unknown_poetry_lock_version_is_an_explicit_diagnostic(self):
        write(self.root / "poetry.lock", "[metadata]\nlock-version = \"9.9\"\n")
        result = self.service().tree(DependencyTreeRequest(ecosystem="python"))
        self.assertTrue(any("unsupported lock format" in warning
                            for warning in result.warnings))

    def test_the_declared_constraint_and_the_resolved_version_are_separate_facts(self):
        write(self.root / "uv.lock", UV_LOCK)
        write(self.root / "pyproject.toml",
              '[project]\nname = "demo"\nversion = "0.1.0"\n'
              'dependencies = ["requests>=2.31", "missing-package"]\n')
        result = self.service().tree(DependencyTreeRequest(ecosystem="python"))
        by_name = {node.package.name: node for node in result.nodes}
        requests = by_name["requests"].package
        self.assertEqual(requests.declared_constraint, ">=2.31")
        self.assertEqual(requests.resolved_version, "2.32.3")
        # A package the lock does not know stays unresolved.
        missing = by_name["missing-package"].package
        self.assertIsNone(missing.resolved_version)

    def test_a_pin_that_the_lock_contradicts_is_reported(self):
        write(self.root / "uv.lock", UV_LOCK)
        write(self.root / "pyproject.toml",
              '[project]\nname = "demo"\ndependencies = ["requests==2.0.0"]\n')
        result = self.service().tree(DependencyTreeRequest(ecosystem="python"))
        self.assertTrue(any("differs from the locked version" in warning
                            for warning in result.warnings))

    def test_the_installed_metadata_is_read_only_when_it_is_selected(self):
        write(self.root / "uv.lock", UV_LOCK)
        environment = Path(self.temp.name) / "site-packages"
        dist_info = environment / "requests-2.32.3.dist-info"
        write(dist_info / "METADATA",
              "Metadata-Version: 2.1\nName: requests\nVersion: 2.32.3\n"
              "Requires-Dist: certifi\n")
        without = self.service().tree(DependencyTreeRequest(ecosystem="python"))
        self.assertFalse(any(item.revision == "2.32.3"
                             for item in without.evidence))
        with_environment = DependencyResearchService(
            project_root=self.root,
            adapters=[PythonEcosystemAdapter(installed_roots=[environment])],
        ).tree(DependencyTreeRequest(ecosystem="python"))
        self.assertTrue(any(item.revision == "2.32.3"
                            for item in with_environment.evidence))

    def test_an_installed_version_that_differs_from_the_lock_is_reported(self):
        write(self.root / "uv.lock", UV_LOCK)
        environment = Path(self.temp.name) / "site-packages"
        write(environment / "requests-2.30.0.dist-info" / "METADATA",
              "Metadata-Version: 2.1\nName: requests\nVersion: 2.30.0\n")
        result = DependencyResearchService(
            project_root=self.root,
            adapters=[PythonEcosystemAdapter(installed_roots=[environment])],
        ).tree(DependencyTreeRequest(ecosystem="python"))
        self.assertTrue(any("differs from the locked version" in warning
                            for warning in result.warnings))

    def test_the_adapter_never_imports_installs_or_reaches_the_network(self):
        forbidden = {"subprocess", "urllib", "urllib.request", "http.client",
                     "socket", "requests", "httpx", "importlib.metadata",
                     "importlib.util"}
        for module in ("pi_platform/adapters/research/python_ecosystem.py",
                       "pi_platform/adapters/research/python_locks.py"):
            imported = _imported_modules(ROOT / module)
            self.assertEqual(imported & forbidden, set(),
                             f"{module} must not import {sorted(forbidden)}")

    def test_the_supported_lock_formats_are_documented(self):
        self.assertIn(1, SUPPORTED_UV_LOCK_VERSIONS)
        self.assertIn("2.0", SUPPORTED_POETRY_LOCK_VERSIONS)
        capabilities = PythonEcosystemAdapter().capabilities()
        self.assertEqual(capabilities["locks"], ["uv.lock", "poetry.lock"])
        self.assertFalse(capabilities["network"])
        self.assertFalse(capabilities["executesDependencyCode"])


# ---------------------------------------------------------------------------
# Node ecosystem
# ---------------------------------------------------------------------------


class NodeEcosystemTests(ProjectFixture):
    def service(self, **kwargs) -> DependencyResearchService:
        return DependencyResearchService(
            project_root=self.root, adapters=[NodeEcosystemAdapter()], **kwargs)

    def test_the_npm_lock_projects_every_dependency_kind(self):
        write(self.root / "package.json", json.dumps({
            "name": "root-app", "version": "1.0.0",
            "dependencies": {"lodash": "^4.17.21", "aliased": "npm:real-pkg@^1.0.0"},
            "devDependencies": {"typescript": "^5.0.0"},
            "optionalDependencies": {"fsevents": "^2.3.0"},
        }))
        write(self.root / "package-lock.json", json.dumps(NPM_LOCK_V3))
        result = self.service().tree(DependencyTreeRequest(ecosystem="node"))
        by_name = {node.package.name: node for node in result.nodes}
        self.assertEqual(by_name["lodash"].package.resolved_version, "4.17.21")
        self.assertEqual(by_name["typescript"].package.resolved_version, "5.3.3")
        self.assertEqual(by_name["fsevents"].package.resolved_version, "2.3.3")
        # The alias keeps both identities.
        aliased = by_name["real-pkg"]
        self.assertEqual(aliased.alias, "aliased")
        kinds = {edge.kind for edge in result.edges}
        self.assertIn("dev", kinds)
        self.assertIn("optional", kinds)

    def test_a_nested_version_wins_over_the_top_level_one(self):
        write(self.root / "package.json", json.dumps({"name": "root-app"}))
        write(self.root / "package-lock.json", json.dumps(NPM_LOCK_V3))
        result = self.service().tree(DependencyTreeRequest(ecosystem="node"))
        by_id = {node.instance_id: node for node in result.nodes}
        nested = next(edge for edge in result.edges
                      if by_id[edge.source_id].package.name == "a")
        target = by_id[nested.target_id]
        self.assertEqual(target.package.resolved_version, "2.0.0")

    def test_two_versions_of_one_package_stay_distinct(self):
        write(self.root / "package.json", json.dumps({"name": "root-app"}))
        write(self.root / "package-lock.json", json.dumps(NPM_LOCK_V3))
        result = self.service().tree(DependencyTreeRequest(ecosystem="node"))
        versions = sorted(node.package.resolved_version for node in result.nodes
                          if node.package.name == "left-pad")
        self.assertEqual(versions, ["1.3.0", "2.0.0"])

    def test_the_npm_lockfile_version_1_is_supported(self):
        write(self.root / "package.json", json.dumps({"name": "legacy-app"}))
        write(self.root / "package-lock.json", json.dumps(NPM_LOCK_V1))
        result = self.service().tree(DependencyTreeRequest(ecosystem="node"))
        by_name = {node.package.name: node for node in result.nodes}
        self.assertEqual(by_name["lodash"].package.resolved_version, "4.17.20")

    def test_the_pnpm_lock_is_supported(self):
        write(self.root / "package.json", json.dumps({"name": "pnpm-app"}))
        write(self.root / "pnpm-lock.yaml", PNPM_LOCK_V9)
        result = self.service().tree(DependencyTreeRequest(ecosystem="node"))
        by_name = {node.package.name: node for node in result.nodes}
        self.assertEqual(by_name["lodash"].package.resolved_version, "4.17.21")

    def test_the_yarn_classic_lock_is_supported(self):
        write(self.root / "package.json", json.dumps({"name": "yarn-app"}))
        write(self.root / "yarn.lock", YARN_CLASSIC_LOCK)
        result = self.service().tree(DependencyTreeRequest(ecosystem="node"))
        by_name = {node.package.name: node for node in result.nodes}
        self.assertEqual(by_name["lodash"].package.resolved_version, "4.17.21")

    def test_an_unsupported_lock_version_is_an_explicit_diagnostic(self):
        write(self.root / "package.json", json.dumps({"name": "app"}))
        write(self.root / "package-lock.json",
              json.dumps({"lockfileVersion": 99, "packages": {}}))
        result = self.service().tree(DependencyTreeRequest(ecosystem="node"))
        self.assertTrue(any("unsupported lock format" in warning
                            for warning in result.warnings))
        self.assertEqual(result.status, ResearchStatus.PARTIAL)
        self.assertEqual(result.completeness, Completeness.PARTIAL)
        self.assertFalse(result.ok is True and result.completeness
                         is Completeness.COMPLETE)

    def test_a_workspace_package_is_its_own_importer(self):
        write(self.root / "package.json", json.dumps({
            "name": "root-app", "workspaces": ["packages/*"]}))
        write(self.root / "package-lock.json", json.dumps(NPM_LOCK_V3))
        write(self.root / "packages/app/package.json",
              json.dumps({"name": "@demo/app", "version": "0.1.0",
                          "dependencies": {"left-pad": "^1.3.0"}}))
        result = self.service().tree(DependencyTreeRequest(ecosystem="node"))
        workspaces = [node for node in result.nodes
                      if node.package.source_kind == "workspace"]
        self.assertIn("@demo/app", {node.package.name for node in workspaces})

    @unittest.skipUnless(parser_status()["available"],
                         "the tree-sitter Node grammars are not installed")
    def test_the_static_parser_reports_symbols_imports_and_reexports(self):
        write(self.root / "package.json", json.dumps({"name": "root-app"}))
        write(self.root / "src/index.ts",
              'import { helper } from "./helper";\n'
              'export * from "./helper";\n'
              'export function main(): string { return helper(); }\n'
              'export class Runner { run(): void {} }\n'
              'export const VERSION = "1.0.0";\n')
        write(self.root / "src/helper.ts",
              'export function helper(): string { return "ok"; }\n')
        result = self.service().search(
            __import__("pi_platform.ports.research.dependency_research",
                       fromlist=["DependencySearchRequest"])
            .DependencySearchRequest(ecosystem="node", package_ref="root-app",
                                     query="main"))
        names = {excerpt["name"] for excerpt in result.excerpts}
        self.assertIn("main", names)

    @unittest.skipUnless(parser_status()["available"],
                         "the tree-sitter Node grammars are not installed")
    def test_a_source_file_is_reported_once_per_manifest(self):
        write(self.root / "package.json", json.dumps({"name": "root-app"}))
        write(self.root / "packages/app/package.json",
              json.dumps({"name": "@demo/app", "version": "0.1.0"}))
        write(self.root / "packages/app/src/index.ts",
              'export function onlyOnce(): void {}\n')
        result = self.service().search(
            __import__("pi_platform.ports.research.dependency_research",
                       fromlist=["DependencySearchRequest"])
            .DependencySearchRequest(ecosystem="node", package_ref="",
                                     query="onlyOnce"))
        self.assertEqual(len(result.excerpts), 1)

    def test_the_parser_licence_and_footprint_are_documented(self):
        capabilities = NodeEcosystemAdapter().capabilities()
        self.assertEqual(capabilities["parser"]["parser"], "tree-sitter")
        self.assertEqual(capabilities["parser"]["license"], "MIT")
        self.assertIn("tree-sitter-javascript", capabilities["parser"]["grammars"])
        self.assertIn("tree-sitter-typescript", capabilities["parser"]["grammars"])
        self.assertFalse(capabilities["network"])

    def test_the_supported_lock_versions_are_documented(self):
        self.assertEqual(SUPPORTED_NPM_LOCK_VERSIONS, frozenset({1, 2, 3}))
        self.assertEqual(SUPPORTED_PNPM_LOCK_VERSIONS, frozenset({"6.0", "9.0"}))
        self.assertIn(8, SUPPORTED_YARN_BERRY_VERSIONS)


# ---------------------------------------------------------------------------
# Java ecosystem
# ---------------------------------------------------------------------------


class JavaEcosystemTests(ProjectFixture):
    POM = """\
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>demo</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>com.google.guava</groupId>
      <artifactId>guava</artifactId>
      <version>33.2.1-jre</version>
    </dependency>
  </dependencies>
</project>
"""

    def test_the_pom_declarations_are_unresolved(self):
        write(self.root / "pom.xml", self.POM)
        result = DependencyResearchService(
            project_root=self.root, adapters=[JavaEcosystemAdapter()]
        ).tree(DependencyTreeRequest(ecosystem="java"))
        by_name = {node.package.name: node for node in result.nodes}
        guava = by_name["com.google.guava:guava"].package
        self.assertEqual(guava.declared_constraint, "33.2.1-jre")
        self.assertIsNone(guava.resolved_version)
        self.assertTrue(any("transitive closure is not resolved" in warning
                            for warning in result.warnings))

    def test_an_explicitly_selected_local_repository_supplies_the_installed_version(self):
        write(self.root / "pom.xml", self.POM)
        repository = Path(self.temp.name) / "m2"
        write(repository / "com/google/guava/guava/33.2.1-jre/guava-33.2.1-jre.pom",
              "<project/>")
        result = DependencyResearchService(
            project_root=self.root,
            adapters=[JavaEcosystemAdapter(installed_roots=[repository])],
        ).tree(DependencyTreeRequest(ecosystem="java"))
        by_name = {node.package.name: node for node in result.nodes}
        guava = by_name["com.google.guava:guava"].package
        self.assertEqual(guava.resolved_version, "33.2.1-jre")
        self.assertEqual(guava.source_kind, "installed")

    def test_the_adapter_never_runs_a_build_tool(self):
        imported = _imported_modules(
            ROOT / "pi_platform/adapters/research/java_ecosystem.py")
        self.assertNotIn("subprocess", imported)
        self.assertNotIn("shutil", imported)


# ---------------------------------------------------------------------------
# Wiring into the existing ingestion
# ---------------------------------------------------------------------------


class ResearchIngestionWiringTests(ProjectFixture):
    def test_the_lock_files_are_discovered_and_classified_as_configuration(self):
        from pi_platform.core.ingest.repository_source_discovery import (
            classify_source_family,
        )
        for name in ("uv.lock", "poetry.lock", "package-lock.json",
                     "pnpm-lock.yaml", "yarn.lock"):
            with self.subTest(name=name):
                self.assertEqual(classify_source_family(name), "configuration")

    def test_the_broad_exclusions_are_kept(self):
        from pi_platform.core.ingest.repository_source_discovery import (
            DEFAULT_EXCLUDE_PATTERNS,
        )
        for pattern in ("node_modules/**", ".venv/**", "venv/**"):
            self.assertIn(pattern, DEFAULT_EXCLUDE_PATTERNS)

    def test_the_new_families_are_registered_in_the_pipeline(self):
        from pi_platform.adapters.ingest.local_pipeline_driver import (
            _default_parser_registry,
        )
        registry = _default_parser_registry()
        for family in (SourceContentFamily.PYTHON_LOCK,
                       SourceContentFamily.NODE_MANIFEST,
                       SourceContentFamily.NODE_LOCK):
            self.assertTrue(registry.has(family), family)

    def test_the_lock_evidence_becomes_searchable_dependencies(self):
        lock = write(self.root / "uv.lock", UV_LOCK)
        parsed = PythonLockAdapter().parse(
            self.source(lock, SourceContentFamily.PYTHON_LOCK))
        labels = {entity.label for entity in parsed.entities}
        self.assertIn("requests", labels)
        self.assertIn("certifi", labels)
        self.assertTrue(parsed.relations)
        self.assertTrue(any(relation.family == "DEPENDS_ON"
                            for relation in parsed.relations))

    def test_the_node_manifest_and_lock_become_searchable_dependencies(self):
        manifest = write(self.root / "package.json",
                         json.dumps({"name": "app", "dependencies": {"lodash": "^4"}}))
        parsed = NodeManifestAdapter().parse(
            self.source(manifest, SourceContentFamily.NODE_MANIFEST))
        self.assertIn("lodash", {entity.label for entity in parsed.entities})
        lock = write(self.root / "package-lock.json", json.dumps(NPM_LOCK_V3))
        parsed = NodeLockAdapter().parse(
            self.source(lock, SourceContentFamily.NODE_LOCK))
        versions = {entity.label: entity.metadata.extensions.get("version")
                    for entity in parsed.entities}
        self.assertEqual(versions.get("lodash"), "4.17.21")

    def test_an_unsupported_lock_version_does_not_break_the_ingestion(self):
        lock = write(self.root / "package-lock.json",
                     json.dumps({"lockfileVersion": 99, "packages": {}}))
        from pi_platform.ports.ingest.source_adapter import SourceAdapterError
        with self.assertRaises(SourceAdapterError):
            NodeLockAdapter().parse(
                self.source(lock, SourceContentFamily.NODE_LOCK))

    def test_an_unchanged_artifact_reuses_the_cached_parse_result(self):
        from pi_platform.core.ingest.repository_source_discovery import (
            RepositorySourceDiscovery,
        )
        write(self.root / "uv.lock", UV_LOCK)
        write(self.root / "README.md", "# demo\n")
        discovery = RepositorySourceDiscovery()
        first = discovery.discover(self.root)
        merged, unchanged, modified = discovery.incremental_reuse(
            previous_inventory=first, new_inventory=first)
        unchanged_paths = {entry.path for entry in unchanged}
        self.assertIn("uv.lock", unchanged_paths)
        self.assertEqual(merged.entries, first.entries)


if __name__ == "__main__":
    unittest.main()
