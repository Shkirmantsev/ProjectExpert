"""Regression proof for parser degradation, legacy text, Office and CPU caps."""
import codecs
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from pi_platform.adapters.html.html_adapter import HtmlAdapter
from pi_platform.adapters.java.java_structured_adapter import JavaStructuredAdapter
from pi_platform.adapters.java.parser_subprocess import TreeSitterJavaSubprocess
from pi_platform.adapters.office.office_adapter import OfficeAdapter
from pi_platform.adapters.ingest.local_pipeline_driver import LocalPipelineDriver
from pi_platform.adapters.runtime.host_resources import probe_cpu_capacity
from pi_platform.core.ingest.records import read_text_with_provenance
from pi_platform.core.canonical.value_types import Source, KnowledgeState
from pi_platform.core.orchestration.resource_budget import cpu_worker_budget, ResourceTokenPool
from pi_platform.ports.ingest.java_parser import JavaParserTimeout, JavaParserCorruptOutput
from pi_platform.ports.ingest.source_adapter import SourceAdapterError


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def source(self, raw, name="x.java", family="java_source"):
        path = self.root / name
        path.write_bytes(raw)
        return Source(name, str(path), family, hashlib.sha256(raw).hexdigest())

    def test_java_failure_preserves_searchable_text_without_ast_claims(self):
        source = self.source(b"class Sample { void hello() {} }")
        for error in (JavaParserTimeout("timeout"), JavaParserCorruptOutput("exit_code=-11")):
            parser = Mock(parser_version="test-1", required=False)
            parser.parse.side_effect = error
            parsed = JavaStructuredAdapter(parser).parse(source)
            self.assertEqual(parsed.knowledge_state, KnowledgeState.ASSUMPTION)
            self.assertFalse(parsed.entities)
            self.assertFalse(parsed.relations)
            chunk = parsed.sections[0].chunks[0]
            self.assertIn("void hello", chunk.rawText)
            self.assertFalse(chunk.metadata.extensions["structured"])
            self.assertTrue(chunk.metadata.extensions["degraded"])

    def test_native_exit_and_corrupt_output_become_text_fallback(self):
        source = self.source(b"class Safe {}")
        parser = TreeSitterJavaSubprocess()
        binding = next(iter(parser._binding_versions))
        import json
        version = json.dumps({"parser_version": parser.parser_version, "binding_version": binding})
        for result in (Mock(returncode=-11, stderr="crash", stdout=""),
                       Mock(returncode=0, stderr="", stdout="{bad")):
            with patch.object(parser, "_run", side_effect=[Mock(returncode=0, stdout=version), result]):
                parsed = JavaStructuredAdapter(parser).parse(source)
            self.assertEqual(parsed.parser_version, "java-text-fallback-1")
            self.assertFalse(parsed.entities)

    def test_bom_and_legacy_html_are_deterministic(self):
        source = self.source(b'<meta charset="windows-1252"><p>Gr\xfc\xdfe</p>', "manual.html", "html")
        parsed = HtmlAdapter().parse(source)
        chunk = parsed.sections[0].chunks[0]
        self.assertEqual(chunk.rawText, "Grüße")
        self.assertEqual(chunk.metadata.extensions["textDecoding"]["encoding"], "cp1252")
        source = self.source(codecs.BOM_UTF16_LE + "Grüße".encode("utf-16-le"), "manual.txt", "plain_text")
        self.assertEqual(read_text_with_provenance(source.uri)[0], "Grüße")

    def test_binary_is_not_legacy_text_and_replacements_are_explicit(self):
        for raw in (b"abc\x00binary", bytes(range(1, 30))):
            source = self.source(raw, "manual.html", "html")
            with self.assertRaises(SourceAdapterError):
                HtmlAdapter().parse(source)
        source = self.source(b"<p>legacy \x81 text</p>", "manual.html", "html")
        parsed = HtmlAdapter().parse(source)
        self.assertEqual(parsed.knowledge_state, KnowledgeState.ASSUMPTION)
        self.assertEqual(parsed.sections[0].chunks[0].metadata.extensions["textDecoding"]["replacementCount"], 1)

    def test_ooxml_routes_docx_and_pptx_without_binary_decode(self):
        for suffix, member in (("docx", "word/document.xml"), ("pptx", "ppt/slides/slide1.xml")):
            path = self.root / ("document." + suffix)
            with ZipFile(path, "w") as archive:
                archive.writestr(member, '<root><p><t>Office words</t></p></root>')
            source = Source(path.name, str(path), "office", "hash")
            report = LocalPipelineDriver().run(source, self.root)
            self.assertTrue(report.ok, report.error_message)
            parsed = OfficeAdapter().parse(source)
            self.assertIn("Office words", parsed.sections[0].chunks[0].rawText)
        source = self.source(b"legacy", "old.doc", "office")
        with self.assertRaisesRegex(SourceAdapterError, "capability unavailable"):
            OfficeAdapter().parse(source)

    def test_effective_cpu_caps_and_nested_costs(self):
        (self.root / "cpu.max").write_text("250000 100000")
        (self.root / "cpuset.cpus.effective").write_text("0-9")
        with patch("os.cpu_count", return_value=20), patch("os.sched_getaffinity", return_value=set(range(16))):
            capacity = probe_cpu_capacity(self.root)
        self.assertEqual(capacity, 2.5)
        self.assertEqual(cpu_worker_budget(capacity), 2)
        self.assertEqual(cpu_worker_budget(10, requested=99), 8)
        self.assertEqual(cpu_worker_budget(10, inner_threads=4), 2)
        self.assertEqual(cpu_worker_budget(2, inner_threads=8), 0)
        self.assertEqual(cpu_worker_budget(0.5), 1)
        self.assertEqual(cpu_worker_budget(10, memory_budget=100, worker_peak=60), 1)
        pool = ResourceTokenPool(2)
        with self.assertRaises(ValueError):
            with pool.acquire(3):
                pass

    def test_parallel_queue_is_bounded_and_reports_keep_source_order(self):
        import threading
        from types import SimpleNamespace
        active = 0
        peak = 0
        lock = threading.Lock()
        barrier = threading.Barrier(2)
        sources = [SimpleNamespace(id=str(i), family="plain_text") for i in range(6)]
        with patch("pi_platform.adapters.runtime.host_resources.parse_worker_budget", return_value=2):
            driver = LocalPipelineDriver(memory_probe=lambda: 1024,
                                         worker_peak_estimator=lambda source: 64)
        def run(source, project_root, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait(timeout=5)
            with lock:
                active -= 1
            return SimpleNamespace(source_id=source.id, error_category=None)
        driver.run = run
        cache = SimpleNamespace(source_buffer=lambda sid: None)
        reports = driver.run_many(sources, self.root, cache=cache)
        self.assertEqual([r.source_id for r in reports], [s.id for s in sources])
        self.assertEqual(peak, 2)

    def test_docling_local_assets_skip_remote_hub(self):
        import os
        from pi_platform.adapters.pdf.real_docling import _pinned_pdf_assets
        with patch.dict(os.environ, {"PI_DOCLING_ASSET_ROOT": str(self.root)}):
            with patch("pi_platform.adapters.pdf.assets.resolve_local_docling_assets", return_value=(self.root, None)) as local:
                self.assertEqual(_pinned_pdf_assets(do_ocr=False), (self.root, None))
                local.assert_called_once_with(self.root, do_ocr=False)


class MemoryAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_memory_probe_honors_host_and_tightest_cgroup_parent(self):
        from pi_platform.adapters.runtime.host_resources import probe_available_memory
        host = self.root / "meminfo"
        host.write_text("MemAvailable: 65536 kB\n")
        child = self.root / "child"
        child.mkdir()
        (self.root / "memory.max").write_text("10000000")
        (self.root / "memory.current").write_text("9000000")
        (child / "memory.max").write_text("50000000")
        (child / "memory.current").write_text("10000000")
        with patch("pi_platform.adapters.runtime.host_resources._cgroup_roots", return_value=(child, self.root)):
            self.assertEqual(probe_available_memory(self.root, meminfo_path=host), 1000000)
        (self.root / "memory.current").write_text("10000001")
        self.assertEqual(probe_available_memory(self.root, meminfo_path=host), 0)
        (self.root / "memory.max").write_text("max")
        (self.root / "memory.limit_in_bytes").write_text("9000000")
        (self.root / "memory.usage_in_bytes").write_text("8000000")
        self.assertEqual(probe_available_memory(self.root, meminfo_path=host), 1000000)

    def test_unknown_memory_is_distinct_from_exhausted_memory(self):
        from pi_platform.adapters.runtime.host_resources import probe_available_memory
        with patch("os.sysconf", side_effect=ValueError("unavailable")):
            self.assertIsNone(probe_available_memory(self.root, meminfo_path=self.root / "absent"))

    def test_source_estimates_include_buffer_amplification_unknown_archives_are_serial(self):
        from pi_platform.adapters.runtime.host_resources import estimate_source_worker_peak
        path = self.root / "x.java"
        path.write_bytes(b"a" * 100)
        source = Source("java", str(path), "java_source", "hash")
        self.assertEqual(estimate_source_worker_peak(source), 64 * 1024 * 1024 + 9600)
        self.assertIsNone(estimate_source_worker_peak(Source("jar", str(path), "jar", "hash")))
        path.unlink()
        self.assertIsNone(estimate_source_worker_peak(source))

    def test_memory_admission_reduces_four_cpu_workers_to_two(self):
        import threading
        from types import SimpleNamespace
        sources = [SimpleNamespace(id=str(i), family="plain_text") for i in range(6)]
        lock = threading.Lock()
        barrier = threading.Barrier(2)
        active = peak = 0
        with patch("pi_platform.adapters.runtime.host_resources.parse_worker_budget", return_value=4):
            driver = LocalPipelineDriver(memory_probe=lambda: 128,
                                         worker_peak_estimator=lambda source: 32)
        def run(source, project_root, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait(timeout=5)
            with lock:
                active -= 1
            return SimpleNamespace(source_id=source.id, error_category=None)
        driver.run = run
        reports = driver.run_many(sources, self.root, cache=SimpleNamespace(source_buffer=lambda sid: None))
        self.assertEqual([r.source_id for r in reports], [s.id for s in sources])
        self.assertEqual(peak, 2)
        self.assertEqual(driver.last_admission["cpu_worker_limit"], 4)
        self.assertEqual(driver.last_admission["peak_pending_workers"], 2)
        self.assertEqual(driver.last_admission["peak_reserved_bytes"], 64)
        self.assertGreater(driver.last_admission["memory_limited_sources"], 0)

    def test_unknown_or_oversized_sources_run_exclusively_on_coordinator(self):
        import threading
        from types import SimpleNamespace
        cases = ((None, 32), (32, None), (32, 100))
        for available, peak in cases:
            with self.subTest(available=available, peak=peak):
                with patch("pi_platform.adapters.runtime.host_resources.parse_worker_budget", return_value=4):
                    driver = LocalPipelineDriver(memory_probe=lambda: available,
                                                 worker_peak_estimator=lambda source: peak)
                ids = []
                def run(source, project_root, **kwargs):
                    ids.append(threading.get_ident())
                    return SimpleNamespace(error_category=None)
                driver.run = run
                sources = [SimpleNamespace(id=str(i), family="plain_text") for i in range(3)]
                driver.run_many(sources, self.root, cache=SimpleNamespace(source_buffer=lambda sid: None))
                self.assertEqual(ids, [threading.get_ident()] * 3)
                self.assertEqual(driver.last_admission["serialized_sources"], 3)
                self.assertEqual(driver.last_admission["peak_pending_workers"], 0)

    def test_shared_optional_model_context_disables_concurrency(self):
        from pi_platform.ports.ingest.context_enricher import EnricherContext
        driver = LocalPipelineDriver(enricher_context=EnricherContext(local_contextualizer=object()),
                                     parallel_safe_registry=True)
        self.assertFalse(driver._parallel_safe)


    def test_actual_default_adapters_match_serial_records_with_buffered_sqlite(self):
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import SqliteIngestionCache
        fixtures = (("a.md", "markdown", b"# Alpha\nShared paragraph"),
                    ("b.html", "html", b"<h1>Beta</h1><p>Manual text</p>"),
                    ("c.py", "python_source", b"def greet(name):\n    return name\n"),
                    ("d.txt", "plain_text", b"Plain source words"))
        sources = []
        for name, family, raw in fixtures:
            path = self.root / name
            path.write_bytes(raw)
            sources.append(Source(name, str(path), family, hashlib.sha256(raw).hexdigest()))
        outputs = []
        for count in (1, 4):
            cache = SqliteIngestionCache(self.root / f"cache-{count}.sqlite")
            self.addCleanup(cache.close)
            with patch("pi_platform.adapters.runtime.host_resources.parse_worker_budget", return_value=count):
                driver = LocalPipelineDriver(memory_probe=lambda: 1024 * 1024 * 1024)
            reports = driver.run_many(sources, self.root, cache=cache)
            self.assertTrue(all(report.ok for report in reports), reports)
            self.assertEqual([report.source_id for report in reports], [source.id for source in sources])
            outputs.append(list(cache.iter_records()))
        self.assertTrue(outputs[0])
        self.assertEqual(outputs[0], outputs[1])


class OfficeBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def document(self, path, xml):
        with ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", xml)
        return Source(path.name, str(path), "office", "hash")

    def test_xml_parser_rejects_doctype_across_encodings(self):
        for encoding in ("utf-8", "utf-16", "utf-32"):
            with self.subTest(encoding=encoding):
                xml = ('<?xml version="1.0" encoding="' + encoding + '"?>'
                       '<!DOCTYPE root [<!ENTITY x "expanded entity">]>'
                       '<root><p><t>&x;</t></p></root>')
                source = self.document(self.root / "untrusted.docx", xml.encode(encoding))
                with self.assertRaises(SourceAdapterError):
                    OfficeAdapter().parse(source)

    def test_utf16_text_remains_supported_without_document_type(self):
        source = self.document(self.root / "manual.docx",
            '<?xml version="1.0" encoding="utf-16"?><root><p><t>Grüße</t></p></root>'.encode("utf-16"))
        self.assertEqual(OfficeAdapter().parse(source).sections[0].chunks[0].rawText, "Grüße")

    def test_office_source_is_confined_and_symlinks_are_rejected(self):
        from pi_platform.ports.ingest.source_adapter import SourceAdapterContext
        project = self.root / "project"
        project.mkdir()
        source = self.document(self.root / "outside.docx", b"<root/>")
        with self.assertRaisesRegex(SourceAdapterError, "inside the project"):
            OfficeAdapter().parse(source, SourceAdapterContext(project))
        linked = project / "linked.docx"
        linked.symlink_to(source.uri)
        with self.assertRaises(SourceAdapterError):
            OfficeAdapter().parse(Source("linked", str(linked), "office", "hash"), SourceAdapterContext(project))
        inside = self.document(project / "inside.docx", b"<root/>")
        linked.unlink()
        linked.symlink_to(inside.uri)
        with self.assertRaisesRegex(SourceAdapterError, "symlink"):
            OfficeAdapter().parse(Source("linked", str(linked), "office", "hash"), SourceAdapterContext(project))

    def test_archive_size_guard_fails_before_reading_source(self):
        source = self.document(self.root / "large.docx", b"<root/>")
        adapter = OfficeAdapter()
        adapter.max_archive_bytes = 1
        with patch("pi_platform.adapters.fs.LocalFilesystemAdapter.read_source_bytes") as read:
            with self.assertRaisesRegex(SourceAdapterError, "archive exceeds"):
                adapter.parse(source)
            read.assert_not_called()


    def test_pptx_slide_relationship_order_controls_slide_labels(self):
        path = self.root / "reordered.pptx"
        with ZipFile(path, "w") as archive:
            archive.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="2" r:id="r2"/><p:sldId id="1" r:id="r1"/></p:sldIdLst></p:presentation>')
            archive.writestr("ppt/_rels/presentation.xml.rels", '<Relationships><Relationship Id="r1" Type="example/slide" Target="slides/slide1.xml"/><Relationship Id="r2" Type="example/slide" Target="/ppt/slides/slide2.xml"/></Relationships>')
            archive.writestr("ppt/slides/slide1.xml", '<root><p><t>Originally first</t></p></root>')
            archive.writestr("ppt/slides/slide2.xml", '<root><p><t>Moved to first</t></p></root>')
        result = OfficeAdapter().parse(Source("slides", str(path), "office", "hash"))
        self.assertEqual([section.heading for section in result.sections], ["Slide 1", "Slide 2"])
        chunks = [section.chunks[0] for section in result.sections]
        self.assertEqual([chunk.rawText for chunk in chunks], ["Moved to first", "Originally first"])
        self.assertTrue(all(chunk.metadata.extensions["presentationOrderKnown"] for chunk in chunks))

    def test_minimal_pptx_uses_neutral_part_labels_and_explicit_partial_state(self):
        path = self.root / "minimal.pptx"
        with ZipFile(path, "w") as archive:
            archive.writestr("ppt/slides/slide5.xml", '<root><p><t>Content</t></p></root>')
        result = OfficeAdapter().parse(Source("slides", str(path), "office", "hash"))
        self.assertEqual(result.knowledge_state, KnowledgeState.ASSUMPTION)
        self.assertIn("partial extraction", result.rationale)
        self.assertEqual(result.sections[0].heading, "Part ppt/slides/slide5.xml")
        self.assertNotIn("slideNumber", result.sections[0].chunks[0].metadata.extensions)

    def test_pptx_relationship_traversal_is_rejected(self):
        path = self.root / "traversal.pptx"
        with ZipFile(path, "w") as archive:
            archive.writestr("ppt/presentation.xml", '<root/>')
            archive.writestr("ppt/_rels/presentation.xml.rels", '<Relationships><Relationship Id="r1" Type="example/slide" Target="../../outside.xml"/></Relationships>')
        with self.assertRaisesRegex(SourceAdapterError, "inside ppt/slides"):
            OfficeAdapter().parse(Source("slides", str(path), "office", "hash"))


    def test_unsupported_office_formats_are_inventoried_then_fail_explicitly(self):
        from pi_platform.core.ingest.repository_source_discovery import (
            RepositorySourceDiscovery, SOURCE_FAMILY_DOCUMENTATION,
        )
        for extension in ("xlsx", "doc", "ppt", "xls"):
            (self.root / f"unsupported.{extension}").write_bytes(b"unsupported Office bytes")
        inventory = RepositorySourceDiscovery().discover(self.root)
        entries = {entry.path: entry for entry in inventory.entries}
        for extension in ("xlsx", "doc", "ppt", "xls"):
            name = f"unsupported.{extension}"
            self.assertIn(name, entries)
            self.assertEqual(entries[name].source_family, SOURCE_FAMILY_DOCUMENTATION)
            source = Source(name, str(self.root / name), "office", "hash")
            with self.assertRaisesRegex(SourceAdapterError, "Office capability unavailable"):
                OfficeAdapter().parse(source)


    def test_public_pipeline_key_matches_stored_completion_and_cache_reuse(self):
        path = self.root / "key.txt"
        path.write_text("Searchable unchanged source")
        source = Source("key", str(path), "plain_text", "stable-source-hash")
        driver = LocalPipelineDriver()
        key = driver.pipeline_key(source)
        self.assertIsNone(driver._cache.source_record(source.id))
        report = driver.run(source, self.root)
        self.assertTrue(report.ok, report.error_message)
        self.assertEqual(driver._cache.source_record(source.id)["key"], key)
        driver.parse_workers += 1
        self.assertEqual(driver.pipeline_key(source), key)
        with patch("pi_platform.adapters.fs.local_source_adapter.LocalSourceAdapter.parse",
                   side_effect=AssertionError("completed source must be reused")):
            reused = driver.run(source, self.root)
        self.assertTrue(reused.ok, reused.error_message)
        self.assertEqual(reused.chunk_count, report.chunk_count)
        self.assertTrue(all(stage.outcome == "skipped" for stage in reused.stages))
