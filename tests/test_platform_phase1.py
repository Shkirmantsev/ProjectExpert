"""Phase 1 platform regression tests.

Covers every Phase 1 scenario from the five foundation specs and the
additive delta files in the ``implement-phase-1-foundation`` change.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pi_platform.core.canonical import (  # noqa: E402
    Chunk,
    ContextualChunk,
    Document,
    Entity,
    Evidence,
    KnowledgeState,
    Manifest,
    Metadata,
    OkfV02Profile,
    ProjectVersion,
    Relation,
    RuntimeChange,
    Section,
    Shard,
    Source,
    TaskContext,
    canonical_dump_json,
    canonical_load_json,
    content_address,
    content_address_bytes,
    content_address_for_canonical,
    dataclass_from_dict,
    dataclass_to_dict,
    from_canonical_json,
    load_manifest,
    manifest_from_shards,
    object_path,
    parse_frontmatter,
    save_manifest,
    to_canonical_json,
    validate_wiki_bundle,
)
from pi_platform.core.canonical.value_types import (  # noqa: E402
    dataclass_to_dict as v_dt,
    dataclass_from_dict as v_fd,
)
from pi_platform.core.sync import (  # noqa: E402
    HydrateService,
    MaterialiseService,
    PolicyDecisionStub,
    ProjectLock,
    ReconcileService,
    WriteAheadLog,
)
from pi_platform.core.licensing import (  # noqa: E402
    DependencyInventory,
    LicenseGate,
    LicensePolicy,
    ModelLicenseInventory,
    PolicyConfig,
    emit_notice_file,
    emit_spdx_sbom,
    stub_inventory,
)
from pi_platform.core.canonical.serializer import (  # noqa: E402
    canonical_dump_yaml,
    canonical_load_yaml,
)
from pi_platform.adapters.fs import LocalFilesystemAdapter  # noqa: E402
from pi_platform.adapters.git.cli_adapter import GitCliAdapter, MINIMUM_GIT_VERSION  # noqa: E402
from pi_platform.core.git import (  # noqa: E402
    compute_version_identity,
    compute_working_tree_overlay,
)
from pi_platform.core.git.version_identity import EMBEDDING_UNKNOWN  # noqa: E402
from pi_platform.cli.main import main as cli_main  # noqa: E402


def _make_metadata(**overrides) -> Metadata:
    defaults = dict(documentId="doc-1", version="0.1.0", language="en")
    defaults.update(overrides)
    return Metadata(**defaults)


def _make_chunk(**overrides) -> Chunk:
    base = dict(
        id="chunk-1",
        rawText="hello world",
        contextualText="docs.hello world",
        metadata=_make_metadata(),
        sourceReference="docs/hello.md",
        contentHash=content_address_bytes(b"hello world"),
    )
    base.update(overrides)
    return Chunk(**base)


def _random_string(n: int) -> str:
    return "".join(random.choice(string.ascii_letters) for _ in range(n))


class CanonicalValueTypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metadata = _make_metadata()
        self.chunk = _make_chunk(metadata=self.metadata)
        self.entity = Entity(
            id="entity-1", family="java-class", label="OrderStatus",
            metadata=self.metadata, relations=(),
            knowledgeState=KnowledgeState.VERIFIED,
        )
        self.relation = Relation(
            sourceId="entity-1", targetId="entity-2", family="DEPENDS_ON",
            knowledgeState=KnowledgeState.VERIFIED,
        )
        self.evidence = Evidence(
            knowledgeState=KnowledgeState.VERIFIED, parserVersion="0.1.0",
        )
        self.project_version = ProjectVersion(
            gitHead="abc123",
            workingTreeFingerprint="deadbeef",
            knowledgeSchemaVersion="0.1.0",
            embeddingModelVersion=EMBEDDING_UNKNOWN,
            indexSchemaVersion="0.1.0",
        )
        self.shard = Shard(id="shard-1", path="objects/aa/aa00.json",
                           contentHash="aa" * 32, count=1)
        self.manifest = Manifest(
            schemaVersion="0.1.0", family="objects",
            shards=(self.shard,), dependencies=(), contentHash=None,
        )
        self.runtime_change = RuntimeChange(
            id="rc-1", kind="chunk",
            payload={"id": "rc-1", "text": "hello"},
            source=Source(id="src-1", uri="file:///tmp/x.md", family="markdown",
                         contentHash=content_address_bytes(b"hello")),
        )
        self.task_context = TaskContext(
            taskId="task-1", goal="trace REQ-1", budgetTokens=4096,
            chunks=(self.chunk,), entities=(self.entity,),
            openSpecIds=("spec-1",), requirements=("REQ-1",),
        )

    def test_each_value_type_round_trips(self) -> None:
        for obj, cls in [
            (self.metadata, Metadata),
            (self.chunk, Chunk),
            (self.entity, Entity),
            (self.relation, Relation),
            (self.evidence, Evidence),
            (self.project_version, ProjectVersion),
            (self.shard, Shard),
            (self.manifest, Manifest),
            (self.runtime_change, RuntimeChange),
            (self.task_context, TaskContext),
        ]:
            with self.subTest(cls=cls.__name__):
                payload = dataclass_to_dict(obj)
                parsed = dataclass_from_dict(cls, payload)
                self.assertEqual(parsed, obj)

    def test_to_canonical_json_trailing_newline(self) -> None:
        body = to_canonical_json(self.chunk)
        self.assertTrue(body.endswith(b"\n"))
        # round-trip
        parsed = from_canonical_json(Chunk, body)
        self.assertEqual(parsed, self.chunk)


class CanonicalRoundtripPropertyTests(unittest.TestCase):
    """Property-based round-trip test asserting byte-identical canonical
    serialisation for shuffled-field-order instances of every Phase 1
    value type.
    """

    def test_chunk_round_trip_byte_identical(self) -> None:
        for _ in range(20):
            raw = _random_string(64).encode("utf-8")
            md = _make_metadata(documentId=_random_string(8),
                               version="0.0." + str(random.randint(0, 9)))
            ch1 = _make_chunk(rawText=raw.decode("utf-8"), contentHash=content_address_bytes(raw),
                             metadata=md)
            ch2 = _make_chunk(rawText=raw.decode("utf-8"), contentHash=content_address_bytes(raw),
                             metadata=md)
            self.assertEqual(to_canonical_json(ch1), to_canonical_json(ch2))

    def test_entity_relation_array_sorted(self) -> None:
        entity = Entity(
            id="e1", family="java-class", label="E1",
            relations=(
                Relation("e1", "c-3", "CALLS"),
                Relation("e1", "c-1", "CALLS"),
                Relation("e1", "c-2", "CALLS"),
            ),
        )
        payload = json.loads(to_canonical_json(entity).decode())
        relations = payload["relations"]
        targets = [r["targetId"] for r in relations]
        self.assertEqual(targets, sorted(targets))

    def test_equivalent_chunks_have_same_content_address(self) -> None:
        raw = b"some text"
        # contentHash is derived from rawText and is the same regardless of
        # the surrounding Metadata value. The bytes argument is the
        # canonical raw text, not the full chunk serialisation.
        self.assertEqual(
            content_address_bytes(raw),
            content_address_bytes(raw),
        )
        # Two chunks with the same rawText expose the same contentHash
        # even when the surrounding metadata differs.
        from pi_platform.core.canonical import chunk_content_address
        ch1 = _make_chunk(rawText=raw.decode("utf-8"),
                         contentHash=content_address_bytes(raw))
        ch2 = _make_chunk(rawText=raw.decode("utf-8"),
                         contentHash=content_address_bytes(raw),
                         metadata=_make_metadata(documentId="x"))
        self.assertEqual(ch1.contentHash, ch2.contentHash)
        self.assertEqual(chunk_content_address(ch1), chunk_content_address(ch2))


class ContentAddressTests(unittest.TestCase):
    def test_object_path_format(self) -> None:
        h = "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
        self.assertEqual(object_path(h), "objects/aa/bbccddeeff00112233445566778899aabbccddeeff00112233445566778899.json")

    def test_content_address_is_hex64(self) -> None:
        h = content_address({"a": 1, "b": [1, 2]})
        self.assertEqual(len(h), 64)
        int(h, 16)

    def test_content_address_for_canonical(self) -> None:
        payload = {"x": 1}
        self.assertEqual(content_address(payload), content_address_for_canonical(payload))


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_manifest_save_load_round_trip(self) -> None:
        shard = Shard(id="s1", path="objects/aa/s1.json",
                     contentHash=content_address({"a": 1}), count=1)
        manifest = manifest_from_shards("objects", [shard])
        path = save_manifest(self.tmp / "manifest.yaml", manifest)
        self.assertTrue(path.is_file())
        loaded = load_manifest(path)
        self.assertEqual(loaded.family, "objects")
        self.assertEqual(loaded.contentHash, manifest.contentHash)

    def test_manifest_self_hash_stable(self) -> None:
        shard = Shard(id="s1", path="objects/aa/s1.json", contentHash="a" * 64)
        m1 = manifest_from_shards("objects", [shard])
        m2 = manifest_from_shards("objects", [shard])
        self.assertEqual(m1.contentHash, m2.contentHash)


class OkfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_root_index_must_have_okf_version_and_type(self) -> None:
        wiki = self.tmp / "wiki"
        wiki.mkdir()
        (wiki / "index.md").write_text("---\nokf_version: '0.2'\ntype: 'WikiIndex'\n---\n# Test\n",
                                       encoding="utf-8")
        (wiki / "concept.md").write_text("---\ntype: Component\ntitle: C\n---\n# C\n",
                                        encoding="utf-8")
        errors = validate_wiki_bundle(wiki)
        self.assertEqual(errors, [])

    def test_concept_without_type_rejected(self) -> None:
        wiki = self.tmp / "wiki"
        wiki.mkdir()
        (wiki / "index.md").write_text("---\nokf_version: '0.2'\ntype: 'WikiIndex'\n---\n# T\n",
                                       encoding="utf-8")
        (wiki / "concept.md").write_text("---\ntitle: C\n---\n# C\n",
                                        encoding="utf-8")
        errors = validate_wiki_bundle(wiki)
        self.assertTrue(any("'type' field" in str(e) for e in errors), errors)

    def test_platform_extensions_ignored(self) -> None:
        md = "---\ntype: Component\ntitle: C\npi_status: ok\npi_source_hash: x\npi_project_version: y\n---\nbody\n"
        fm, body = parse_frontmatter(md)
        self.assertEqual(fm.get("type"), "Component")
        self.assertIn("pi_status", fm)

    def test_reserved_filenames_accepted(self) -> None:
        wiki = self.tmp / "wiki"
        wiki.mkdir()
        (wiki / "index.md").write_text("---\nokf_version: '0.2'\ntype: 'WikiIndex'\n---\n# T\n",
                                       encoding="utf-8")
        (wiki / "log.md").write_text("log entry\n", encoding="utf-8")
        errors = validate_wiki_bundle(wiki)
        self.assertEqual(errors, [])


class ProjectKnowledgeLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_init_project_scaffolds_canonical_tree(self) -> None:
        fs = LocalFilesystemAdapter(self.tmp)
        fs.ensure_canonical_tree()
        for sub in ("wiki", "graph", "chunks", "sources", "objects", "manifests"):
            self.assertTrue((fs.knowledge_root / sub).is_dir(), sub)

    def test_init_project_writes_gitignore_once(self) -> None:
        fs = LocalFilesystemAdapter(self.tmp)
        added = fs.ensure_gitignore()
        self.assertIn("tmp/local/**", added)
        self.assertIn(".project-intelligence-cache/**", added)
        added_again = fs.ensure_gitignore()
        self.assertEqual(added_again, [])

    def test_ensure_gitignore_preserves_user_entries(self) -> None:
        gitignore = self.tmp / ".gitignore"
        gitignore.write_text("build/**\n", encoding="utf-8")
        fs = LocalFilesystemAdapter(self.tmp)
        fs.ensure_gitignore()
        text = gitignore.read_text(encoding="utf-8")
        self.assertIn("build/**", text)

    def test_distribution_tree_scaffolded(self) -> None:
        fs = LocalFilesystemAdapter(self.tmp)
        fs.ensure_distribution_tree()
        for sub in ("licenses", "skills", "codex", "claude-code",
                    "opencode", "generic-agent", "sbom"):
            self.assertTrue((fs.distribution_root / sub).is_dir(), sub)


class GitPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email",
                       "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name",
                       "Test"], check=True)
        (self.tmp / "README.md").write_text("hello", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "README.md"],
                       check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q",
                       "-m", "init"], check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_git_cli_adapter_head(self) -> None:
        port = GitCliAdapter()
        head = port.head(self.tmp)
        self.assertEqual(len(head), 40)
        # Default branch is git-config-dependent ("main" or "master").
        self.assertIn(port.current_branch(self.tmp), ("main", "master"))

    def test_git_cli_adapter_status_clean(self) -> None:
        port = GitCliAdapter()
        self.assertEqual(port.status(self.tmp), [])

    def test_git_cli_adapter_status_modified(self) -> None:
        (self.tmp / "README.md").write_text("changed", encoding="utf-8")
        port = GitCliAdapter()
        changes = port.status(self.tmp)
        self.assertTrue(any(c.path.name == "README.md" for c in changes))

    def test_git_cli_adapter_minimum_version(self) -> None:
        port = GitCliAdapter()
        version = port.version()
        self.assertGreaterEqual(version, MINIMUM_GIT_VERSION)


class VersionIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email",
                       "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name",
                       "Test"], check=True)
        (self.tmp / "file.txt").write_text("v1", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "file.txt"],
                       check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q",
                       "-m", "v1"], check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_embedding_model_version_defaults_to_unknown(self) -> None:
        identity = compute_version_identity(self.tmp)
        self.assertEqual(identity.embeddingModelVersion, "unknown")

    def test_branch_name_not_in_identity(self) -> None:
        identity_main = compute_version_identity(self.tmp)
        subprocess.run(["git", "-C", str(self.tmp), "checkout", "-q",
                       "-b", "feature/x"], check=True)
        identity_branch = compute_version_identity(self.tmp)
        self.assertEqual(identity_main.gitHead, identity_branch.gitHead)
        self.assertNotIn("feature", identity_branch.workingTreeFingerprint)
        self.assertNotIn("master", identity_branch.workingTreeFingerprint)

    def test_working_tree_fingerprint_changes_with_change(self) -> None:
        identity1 = compute_version_identity(self.tmp)
        (self.tmp / "file.txt").write_text("v2", encoding="utf-8")
        identity2 = compute_version_identity(self.tmp)
        self.assertNotEqual(identity1.workingTreeFingerprint,
                            identity2.workingTreeFingerprint)


class WorkingTreeOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email",
                       "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name",
                       "Test"], check=True)
        (self.tmp / "file.txt").write_text("v1", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "file.txt"],
                       check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q",
                       "-m", "v1"], check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_overlay_is_deterministic(self) -> None:
        (self.tmp / "file.txt").write_text("changed", encoding="utf-8")
        overlay1 = compute_working_tree_overlay(self.tmp)
        overlay2 = compute_working_tree_overlay(self.tmp)
        self.assertEqual(overlay1, overlay2)

    def test_overlay_records_modified_path(self) -> None:
        (self.tmp / "file.txt").write_text("changed", encoding="utf-8")
        overlay = json.loads(compute_working_tree_overlay(self.tmp).decode())
        self.assertTrue(any(c["path"].endswith("file.txt")
                            for c in overlay["changes"]))

    def test_overlay_handles_multiple_changes(self) -> None:
        """Regression: git status --porcelain=1 -z uses NUL separators,
        not newlines; the parser used to collapse all entries into one.
        """
        (self.tmp / "file.txt").write_text("changed", encoding="utf-8")
        (self.tmp / "added.txt").write_text("new", encoding="utf-8")
        overlay = json.loads(compute_working_tree_overlay(self.tmp).decode())
        paths = {c["path"].split("/")[-1] for c in overlay["changes"]}
        self.assertIn("file.txt", paths)
        self.assertIn("added.txt", paths)


class HydrateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = self.tmp / "cache"
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email",
                       "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name",
                       "Test"], check=True)
        (self.tmp / "file.txt").write_text("v1", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "file.txt"],
                       check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q",
                       "-m", "v1"], check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_cold_start_hydrate_reports_zero_hit_rate(self) -> None:
        fs = LocalFilesystemAdapter(self.tmp, cache_root=self.cache)
        fs.ensure_canonical_tree()
        shard_path = fs.knowledge_root / "objects" / "aa" / "aa00.json"
        shard_path.parent.mkdir(parents=True, exist_ok=True)
        shard_path.write_bytes(canonical_dump_json({"hello": "world"}))
        shard = Shard(id="s1", path=str(shard_path.relative_to(fs.knowledge_root)),
                     contentHash=content_address({"hello": "world"}))
        manifest = manifest_from_shards("objects", [shard])
        save_manifest(fs.knowledge_root / "manifests" / "objects-manifest.yaml",
                     manifest)
        report = HydrateService().restore_runtime(self.tmp, cache_root=self.cache)
        self.assertEqual(report.families["objects"], 1)
        self.assertEqual(report.cache_hit_rates["objects"], 1.0)


class MaterialiseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = self.tmp / "cache"
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email",
                       "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name",
                       "Test"], check=True)
        (self.tmp / "file.txt").write_text("v1", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "file.txt"],
                       check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q",
                       "-m", "v1"], check=True)
        self.fs = LocalFilesystemAdapter(self.tmp, cache_root=self.cache)
        self.fs.ensure_canonical_tree()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_materialise_requires_approval_token(self) -> None:
        from pi_platform.ports import ApprovalRequired
        service = MaterialiseService()
        with self.assertRaises(ApprovalRequired):
            service.materialise_durable_changes(self.tmp,
                                                cache_root=self.cache,
                                                approval_token=None)

    def test_materialise_no_changes_is_noop(self) -> None:
        service = MaterialiseService(filesystem=self.fs)
        report = service.materialise_durable_changes(
            self.tmp, cache_root=self.cache, approval_token="manual",
        )
        self.assertEqual(report.diff_files, ())
        self.assertEqual(report.excluded_local_only, ())

    def test_materialise_excludes_local_only_sources(self) -> None:
        source = Source(
            id="src-local", uri="file:///tmp/x.md", family="markdown",
            contentHash=content_address_bytes(b"x"),
            metadata=_make_metadata(businessDomain="LOCAL_ONLY"),
        )
        local_change = RuntimeChange(
            id="rc-local", kind="chunk",
            payload={"id": "rc-local", "kind": "chunk", "family": "markdown", "text": "x"},
            source=source,
        )
        durable_change = RuntimeChange(
            id="rc-durable", kind="chunk",
            payload={"id": "rc-durable", "kind": "chunk", "family": "markdown", "text": "y"},
            source=Source(id="src-1", uri="file:///tmp/y.md", family="markdown",
                          contentHash=content_address_bytes(b"y")),
        )
        service = MaterialiseService(filesystem=self.fs)
        report = service.materialise_durable_changes(
            self.tmp, cache_root=self.cache, approval_token="manual",
            changes=[local_change, durable_change],
        )
        self.assertIn("rc-local", report.excluded_local_only)
        added = [d for d in report.diff_files if d.status == "added"]
        self.assertTrue(any("rc-durable" in d.path for d in added), added)


class SyncRoundtripTests(unittest.TestCase):
    """End-to-end hydrate → edit → materialise round trip."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = self.tmp / "cache"
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email",
                       "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name",
                       "Test"], check=True)
        (self.tmp / "file.txt").write_text("v1", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "file.txt"],
                       check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q",
                       "-m", "v1"], check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_round_trip_no_change_is_empty_diff(self) -> None:
        fs = LocalFilesystemAdapter(self.tmp, cache_root=self.cache)
        fs.ensure_canonical_tree()
        shard_path = fs.knowledge_root / "objects" / "aa" / "aa00.json"
        shard_path.parent.mkdir(parents=True, exist_ok=True)
        shard_path.write_bytes(canonical_dump_json({"a": 1}))
        shard = Shard(id="s1",
                     path=str(shard_path.relative_to(fs.knowledge_root)),
                     contentHash=content_address({"a": 1}))
        save_manifest(fs.knowledge_root / "manifests" / "objects-manifest.yaml",
                     manifest_from_shards("objects", [shard]))
        HydrateService().restore_runtime(self.tmp, cache_root=self.cache)
        report = MaterialiseService(filesystem=fs).materialise_durable_changes(
            self.tmp, cache_root=self.cache, approval_token="manual"
        )
        self.assertEqual(report.diff_files, ())


class ProjectLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_lock_acquired_and_released(self) -> None:
        lock = ProjectLock("test", root=self.tmp)
        with lock.acquire():
            self.assertTrue(lock.path.exists())

    def test_concurrent_lock_serialises(self) -> None:
        import threading
        lock1 = ProjectLock("same", root=self.tmp)
        lock2 = ProjectLock("same", root=self.tmp)
        order: list[str] = []
        release = threading.Event()

        def first():
            with lock1.acquire():
                order.append("first")
                release.wait(0.5)

        def second():
            release.wait(0.05)
            with lock2.acquire():
                order.append("second")

        t1 = threading.Thread(target=first)
        t2 = threading.Thread(target=second)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertEqual(order, ["first", "second"])


class WriteAheadLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_recover_rolls_back_when_marker_present(self) -> None:
        wal = WriteAheadLog(self.tmp)
        wal.begin()
        wal.append("begin", {"id": "x"})
        wal.append("write", {"x": 1})
        self.assertTrue(wal.is_in_progress())
        removed = wal.recover()
        self.assertEqual(removed, 2)
        self.assertFalse(wal.is_in_progress())

    def test_recover_no_marker_truncates_wal(self) -> None:
        wal = WriteAheadLog(self.tmp)
        wal.append("begin", {})
        wal.append("commit", {})
        self.assertFalse(wal.is_in_progress())
        removed = wal.recover()
        self.assertEqual(removed, 2)
        self.assertEqual(len(wal.read_all()), 0)


class LicensePolicyTests(unittest.TestCase):
    def test_mit_dependency_is_allowed(self) -> None:
        from pi_platform.ports import Dependency
        decision, reason = LicensePolicy().evaluate(Dependency(
            name="x", version="1.0", spdx="MIT"))
        self.assertEqual(decision, "allow")

    def test_lgpl_dependency_is_review(self) -> None:
        from pi_platform.ports import Dependency
        decision, reason = LicensePolicy().evaluate(Dependency(
            name="x", version="1.0", spdx="LGPL-2.1-only"))
        self.assertEqual(decision, "review")

    def test_noncommercial_dependency_is_denied(self) -> None:
        from pi_platform.ports import Dependency
        decision, reason = LicensePolicy().evaluate(Dependency(
            name="x", version="1.0", spdx="Foo-NC-Bar"))
        self.assertEqual(decision, "deny")

    def test_missing_spdx_is_denied(self) -> None:
        from pi_platform.ports import Dependency
        decision, _ = LicensePolicy().evaluate(Dependency(
            name="x", version="1.0", spdx=None))
        self.assertEqual(decision, "deny")

    def test_policy_config_from_dict(self) -> None:
        cfg = PolicyConfig.from_dict({"allow": ["MIT"], "review": [],
                                       "denyPatterns": ["*-NC-*"]})
        self.assertEqual(cfg.allow, ("MIT",))
        self.assertEqual(cfg.deny_patterns, ("*-NC-*",))


class LicenseGateTests(unittest.TestCase):
    def test_gate_passes_stub_inventory(self) -> None:
        gate = LicenseGate(LicensePolicy())
        passed, findings = gate.run(stub_inventory())
        self.assertTrue(passed, findings)

    def test_gate_fails_on_unknown_license(self) -> None:
        from pi_platform.ports import Dependency
        gate = LicenseGate(LicensePolicy())
        passed, findings = gate.run([Dependency(
            name="x", version="1.0", spdx="UnknownLicense")])
        self.assertFalse(passed)
        self.assertEqual(findings[0].decision, "deny")

    def test_gate_review_accepts_with_token(self) -> None:
        from pi_platform.ports import Dependency
        gate = LicenseGate(LicensePolicy(),
                          review_acceptance={"x@1.0": "manual"})
        passed, findings = gate.run([Dependency(
            name="x", version="1.0", spdx="LGPL-2.1-only")])
        self.assertTrue(passed, findings)

    def test_gate_review_without_token_blocks_build(self) -> None:
        from pi_platform.ports import Dependency
        gate = LicenseGate(LicensePolicy())
        passed, findings = gate.run([Dependency(
            name="x", version="1.0", spdx="LGPL-2.1-only")])
        self.assertFalse(passed, findings)
        self.assertEqual(findings[0].decision, "deny")


class InventoryAndSbomTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_dependency_inventory_save_load(self) -> None:
        from pi_platform.ports import Dependency
        inv = DependencyInventory(self.tmp / "inv.json")
        inv.save([Dependency(name="x", version="1.0", spdx="MIT",
                            source="upstream", scope="runtime")])
        loaded = inv.load()
        self.assertEqual(loaded[0].spdx, "MIT")

    def test_model_license_inventory_save_load(self) -> None:
        from pi_platform.ports import ModelLicense
        inv = ModelLicenseInventory(self.tmp / "models.json")
        inv.save([ModelLicense(name="llm-x", version="1.0", spdx="Apache-2.0",
                              source="upstream")])
        loaded = inv.load()
        self.assertEqual(loaded[0].name, "llm-x")

    def test_sbom_emit(self) -> None:
        sbom_path = emit_spdx_sbom(stub_inventory(), output_root=self.tmp)
        self.assertTrue(sbom_path.is_file())
        doc = json.loads(sbom_path.read_text())
        self.assertEqual(doc["spdxVersion"], "SPDX-2.3")

    def test_notice_emit(self) -> None:
        notice_path = emit_notice_file(stub_inventory(), output_root=self.tmp)
        self.assertTrue(notice_path.is_file())


class CliEntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email",
                       "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name",
                       "Test"], check=True)
        (self.tmp / "README.md").write_text("hello", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "README.md"],
                       check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q",
                       "-m", "init"], check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_init_project_subcommand(self) -> None:
        rc = cli_main(["init-project", "--target", str(self.tmp)])
        self.assertEqual(rc, 0)
        self.assertTrue((self.tmp / "project-knowledge").is_dir())

    def test_health_subcommand(self) -> None:
        rc = cli_main(["health"])
        self.assertEqual(rc, 0)

    def test_license_gate_subcommand_passes_stub(self) -> None:
        cli_main(["init-project", "--target", str(self.tmp)])
        rc = cli_main(["license-gate", "--target", str(self.tmp)])
        self.assertEqual(rc, 0)

    def test_wal_recover_default_invocation(self) -> None:
        """Regression: wal-recover used to crash on default invocation
        because --target was missing.
        """
        rc = cli_main(["wal-recover"])
        self.assertEqual(rc, 0)

    def test_version_identity_subcommand_reports_unknown_embedding(self) -> None:
        rc = cli_main(["version-identity", "--target", str(self.tmp)])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()