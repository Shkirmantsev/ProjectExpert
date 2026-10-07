"""Phase 2 behavior regressions; fixtures use actual source bytes."""

import dataclasses
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from pi_platform.core.canonical.value_types import *
from pi_platform.adapters.markdown.markdown_adapter import MarkdownAdapter
from pi_platform.adapters.html.html_adapter import HtmlAdapter
from pi_platform.adapters.ingest.chunkers import MarkdownChunker, HtmlChunker
from pi_platform.adapters.ingest.local_pipeline_driver import LocalPipelineDriver
from pi_platform.core.ingest.runtime_cache import InMemoryRuntimeCache
from pi_platform.core.ingest.local_source_inbox_scanner import LocalSourceInboxScanner
from pi_platform.ports.ingest.local_source_inbox_scanner import (
    LocalSourceInboxContext,
    SourcePromotionPolicy,
    PromotionDenied,
)
from pi_platform.ports.ingest.source_adapter import SourceAdapterError


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self, text, name="doc.md", family="markdown"):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return Source(name, str(p), family, hashlib.sha256(p.read_bytes()).hexdigest())


class SourceAdapterTests(Fixture):
    def test_markdown_keeps_body_and_hierarchy(self):
        s = self.source("# Title\nintro\n## A\nfirst body\n\nsecond body\n")
        r = MarkdownAdapter().parse(s)
        chunks = MarkdownChunker().chunk(r.document, r.sections)
        self.assertIn("first body", "\n".join(c.rawText for c in chunks))
        self.assertEqual(r.sections[1].parentId, r.sections[0].id)
        self.assertTrue(all(c.parentId in {x.id for x in r.sections} for c in chunks))

    def test_binary_and_missing_fail(self):
        s = self.source("abc\0def")
        with self.assertRaises(SourceAdapterError):
            MarkdownAdapter().parse(s)
        Path(s.uri).unlink()
        with self.assertRaises(SourceAdapterError):
            MarkdownAdapter().parse(s)

    def test_html_keeps_body_without_scripts(self):
        s = self.source(
            "<h1>A</h1><p>real text</p><script>secret()</script><h2>B</h2><p>more</p>",
            "x.html",
            "html",
        )
        r = HtmlAdapter().parse(s)
        body = "\n".join(c.rawText for c in HtmlChunker().chunk(r.document, r.sections))
        self.assertIn("real text", body)
        self.assertIn("more", body)
        self.assertNotIn("secret()", body)


class ChunkerTests(Fixture):
    def test_unicode_budget_and_stable_ids(self):
        from pi_platform.ports.ingest.chunker import ChunkerContext

        s = self.source("# A\n" + "é " * 5000)
        r = MarkdownAdapter().parse(s)
        ctx = ChunkerContext(max_chunk_bytes=512)
        cs = MarkdownChunker().chunk(r.document, r.sections, ctx)
        self.assertTrue(all(len(c.rawText.encode()) <= 512 for c in cs))
        self.assertEqual(cs, MarkdownChunker().chunk(r.document, r.sections, ctx))
        self.assertEqual(len({c.id for c in cs}), len(cs))


class PipelineDriverTests(Fixture):
    def test_five_stages_store_body_and_skip_parse_on_repeat(self):
        s = self.source("# A\nbody data")
        cache = InMemoryRuntimeCache()
        d = LocalPipelineDriver(cache=cache)
        first = d.run(s, self.root)
        self.assertTrue(first.ok, first.error_message)
        self.assertEqual(
            [x.stage for x in first.stages],
            ["parse", "chunk", "enrich", "emit", "store"],
        )
        with patch.object(
            MarkdownAdapter, "parse", side_effect=AssertionError("reparsed")
        ):
            second = d.run(s, self.root)
        self.assertTrue(second.ok, second.error_message)
        self.assertEqual(second.cache_hit_count, first.chunk_count)
        self.assertEqual(second.cache_miss_count, 0)
        self.assertTrue(any(b"body data" in v for v in cache._store.values()))

    def test_permanent_continues_configuration_stops(self):
        d = LocalPipelineDriver()
        bad = self.source("\0", "bad.md")
        good = self.source("fine", "good.md")
        reports = d.run_many((bad, good), self.root)
        self.assertEqual(len(reports), 2)
        self.assertFalse(reports[0].ok)
        self.assertTrue(reports[1].ok)
        unknown = dataclasses.replace(bad, family="absent")
        self.assertEqual(len(d.run_many((unknown, good), self.root)), 1)

    def test_unexpected_exception_is_internal_error(self):
        """Regression: programming bugs (KeyError, AttributeError, ...)
        must NOT masquerade as ``permanent`` source errors. The pipeline
        must categorise them as ``internal_error`` so the operator can
        distinguish "the source is bad" from "the code has a regression"
        without having to dig through tracebacks.
        """

        from pi_platform.ports.ingest.pipeline_driver import StageErrorCategory
        d = LocalPipelineDriver()
        s = self.source("body", "good.md")
        with patch.object(MarkdownAdapter, "parse",
                           side_effect=KeyError("simulated programming bug")):
            report = d.run(s, self.root)
        self.assertFalse(report.ok)
        failing_stages = [o for o in report.stages if o.error_category]
        self.assertTrue(failing_stages,
                        "at least one stage should have an error_category")
        for outcome in failing_stages:
            self.assertEqual(outcome.error_category,
                             StageErrorCategory.INTERNAL.value,
                             f"unexpected exception must surface as "
                             f"internal_error, got {outcome.error_category!r}: "
                             f"{outcome.error_message!r}")


class LocalSourceInboxScannerTests(Fixture):
    def test_policy_relative_glob_and_serialization(self):
        self.source("x", "customer/a.md")
        self.source("y", "other.md")
        scanner = LocalSourceInboxScanner()
        r = scanner.scan(
            LocalSourceInboxContext(
                self.root, override_map={"customer/**": SourcePromotionPolicy.SNAPSHOT}
            )
        )
        self.assertEqual(len(r.registered_sources), 2)
        a = r.registered_sources[0]
        self.assertEqual(a.metadata.policy, "SNAPSHOT")
        self.assertEqual(
            from_canonical_json(Source, to_canonical_json(a)).metadata.policy,
            "SNAPSHOT",
        )

    def test_pom_and_local_only(self):
        s = self.source("<project/>", "pom.xml")
        r = LocalSourceInboxScanner().scan(LocalSourceInboxContext(self.root))
        self.assertEqual(r.registered_sources[0].family, "maven_pom")
        report = LocalPipelineDriver().run(r.registered_sources[0], self.root)
        self.assertEqual(report.knowledge_state, KnowledgeState.UNKNOWN)
        with self.assertRaises(PromotionDenied):
            LocalSourceInboxScanner().promote(
                r.registered_sources[0],
                SourcePromotionPolicy.LOCAL_ONLY,
                self.root / "snapshots",
            )


class LocalSourceInboxScannerSpecTests(LocalSourceInboxScannerTests):
    def test_deleted_and_oversized(self):
        s = self.source("abcdef")
        scanner = LocalSourceInboxScanner()
        ctx = LocalSourceInboxContext(self.root)
        first = scanner.scan(ctx)
        Path(s.uri).unlink()
        second = scanner.scan(ctx)
        self.assertEqual(second.deleted_source_ids, (first.registered_sources[0].id,))
        self.source("too long")
        self.assertEqual(
            len(
                scanner.scan(
                    LocalSourceInboxContext(self.root, extra={"max_source_bytes": 2})
                ).registered_sources
            ),
            0,
        )


from pi_platform.adapters.java.parser_subprocess import TreeSitterJavaSubprocess
from pi_platform.adapters.java.java_structured_adapter import (
    JavaStructuredAdapter,
    JavaStructuredChunker,
)
from pi_platform.adapters.java.maven_adapter import MavenAdapter
from pi_platform.adapters.java.gradle_adapter import GradleAdapter
from pi_platform.adapters.java.jar_adapter import JarAdapter
from pi_platform.adapters.openspec.openspec_change_adapter import (
    OpenSpecChangeAdapter,
    OpenSpecChunker,
)
from pi_platform.ports.ingest.java_parser import (
    JavaParseRequest,
    JavaParserMissing,
    JavaParserTimeout,
    JavaParserVersionMismatch,
    JavaParserCorruptOutput,
)
from pi_platform.ports.ingest.pipeline_driver import (
    StageError,
    StageErrorCategory,
    CancellationToken,
)
from pi_platform.ports.ingest.source_adapter import SourceAdapterRegistry
from pi_platform.adapters.ingest.layered_context_enricher import LayeredContextEnricher
from pi_platform.ports.ingest.context_enricher import (
    EnricherContext,
    DomainRule,
    EnricherError,
)


class JavaStructuredAdapterTests(Fixture):
    def parser(self):
        import sys

        local = Path(__file__).resolve().parents[1] / "tmp/local/phase2/venv/bin/python"
        return TreeSitterJavaSubprocess(
            command=(
                str(local) if local.exists() else sys.executable,
                "-m",
                "pi_platform.adapters.java.parser_worker",
            ),
            required=True,
        )

    def test_required_missing_and_degraded(self):
        missing = TreeSitterJavaSubprocess(
            command=("/definitely/missing/parser",), required=True
        )
        request = JavaParseRequest("class A {}", Path("A.java"))
        with self.assertRaises(JavaParserMissing):
            missing.parse(request)
        optional = TreeSitterJavaSubprocess(command=("/definitely/missing/parser",))
        r = JavaStructuredAdapter(optional).parse(
            self.source("class A {}", "A.java", "java_source")
        )
        self.assertEqual(r.knowledge_state, KnowledgeState.ASSUMPTION)
        self.assertFalse(r.entities)
        self.assertIn("class A", r.sections[0].chunks[0].rawText)

    def test_real_classes_methods_calls_and_chunk_hierarchy(self):
        parser = self.parser()
        if not parser.is_available():
            self.skipTest("optional Java parser packages absent")
        source = self.source(
            "package demo; public class Foo extends BaseFoo implements Iface { public void bar() { baz(); } public void baz() {} class Inner {} }",
            "Foo.java",
            "java_source",
        )
        r = JavaStructuredAdapter(parser).parse(source)
        self.assertTrue(
            any(
                e.family == "JavaClass"
                and e.label == "Foo"
                and e.metadata.className == "demo.Foo"
                for e in r.entities
            )
        )
        self.assertEqual(
            {e.label for e in r.entities if e.family == "JavaMethod"}, {"bar", "baz"}
        )
        self.assertTrue(
            {"EXTENDS", "IMPLEMENTS", "CALLS", "PART_OF"}
            <= {x.family for x in r.relations}
        )
        self.assertTrue(
            all(
                e.sourceHash == source.contentHash
                and e.parserVersion == "tree-sitter-java-0.23.5"
                for e in r.evidence
            )
        )
        chunks = JavaStructuredChunker().chunk(r.document, r.sections)
        cls = next(c for c in chunks if c.metadata.section == "Foo")
        self.assertEqual(cls.parentId, r.document.id)
        methods = [c for c in chunks if c.metadata.section in ("bar", "baz")]
        self.assertTrue(
            all(c.parentId == cls.id and c.id in cls.childIds for c in methods)
        )

    def test_real_jpa_and_tests(self):
        parser = self.parser()
        if not parser.is_available():
            self.skipTest("optional Java parser packages absent")
        text = '@Entity @Table(name="orders") class Order { @OneToMany(mappedBy="order") List<OrderLine> lines; } class OrderServiceTest { @Test void createsOrder(){ new OrderService(); } @Test void failsOnNegativeAmount() {} }'
        r = JavaStructuredAdapter(parser).parse(
            self.source(text, "Order.java", "java_source")
        )
        self.assertTrue(
            any(
                e.family == "JPAEntity"
                and e.metadata.extensions["tableName"] == "orders"
                for e in r.entities
            )
        )
        self.assertEqual(sum(e.family == "Test" for e in r.entities), 2)
        self.assertIn("MAPPED_BY", {x.family for x in r.relations})
        self.assertIn("TESTED_BY", {x.family for x in r.relations})

    def test_timeout_version_and_corrupt_output(self):
        p = TreeSitterJavaSubprocess()
        request = JavaParseRequest("class A {}", Path("A.java"))
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("parser", 60)
        ):
            with self.assertRaises(JavaParserTimeout):
                p.parse(request)
        with patch(
            "subprocess.run",
            return_value=Mock(
                returncode=0,
                stdout=json.dumps(
                    {"parser_version": "wrong", "binding_version": "0.25.2"}
                ),
            ),
        ):
            with self.assertRaises(JavaParserVersionMismatch):
                p.parse(request)
        with patch(
            "subprocess.run", return_value=Mock(returncode=0, stdout="not-json")
        ):
            with self.assertRaises(JavaParserCorruptOutput):
                p.parse(request)

    def test_license_gate_before_registration(self):
        inventory = self.root / "inventory.json"
        inventory.write_text('{"dependencies":[]}')
        with self.assertRaises(JavaParserVersionMismatch):
            TreeSitterJavaSubprocess(inventory_path=inventory)

    def test_configuration_properties(self):
        r = JavaStructuredAdapter().parse(
            self.source(
                "server.port=8080\nspring.name=demo",
                "application.properties",
                "java_source",
            )
        )
        self.assertEqual([e.label for e in r.entities], ["server.port", "spring.name"])


class MavenGradleAdapterTests(Fixture):
    def test_maven_namespace_properties_and_management(self):
        pom = '<project xmlns="http://maven.apache.org/POM/4.0.0"><artifactId>root</artifactId><properties><v>1.0</v></properties><modules><module>child</module></modules><dependencyManagement><dependencies><dependency><groupId>com.a</groupId><artifactId>b</artifactId><version>${v}</version></dependency></dependencies></dependencyManagement><dependencies><dependency><groupId>com.a</groupId><artifactId>b</artifactId></dependency><dependency><groupId>com.a</groupId><artifactId>c</artifactId><version>1.1</version></dependency><dependency><groupId>com.b</groupId><artifactId>d</artifactId><version>2.0</version></dependency></dependencies></project>'
        s = self.source(pom, "pom.xml", "maven_pom")
        r = MavenAdapter().parse(s)
        deps = [e for e in r.entities if e.family == "Dependency"]
        self.assertEqual(len(deps), 3)
        self.assertEqual(deps[0].metadata.extensions["version"], "1.0")
        self.assertTrue(
            all(e.knowledgeState == KnowledgeState.ASSUMPTION for e in deps)
        )
        with (
            patch("shutil.which", return_value=None),
            self.assertLogs("pi_platform.adapters.java.dependencies", level="WARNING"),
        ):
            self.assertEqual(len(MavenAdapter().resolve_tree(self.root)), 3)

    def test_gradle_both_dialects_and_spdx(self):
        for name, text in [
            (
                "build.gradle.kts",
                'implementation("com.a:b:1.0")\ntestImplementation("com.c:d:2.0")',
            ),
            (
                "build.gradle",
                "implementation 'com.a:b:1.0'\ntestImplementation group: 'com.c', name: 'd', version: '2.0'",
            ),
        ]:
            r = GradleAdapter().parse(self.source(text, name, "gradle_build"))
            deps = [e for e in r.entities if e.family == "Dependency"]
            self.assertEqual(len(deps), 2)
            self.assertEqual(deps[1].metadata.extensions["scope"], "test")

    def test_known_spdx_pass_through(self):
        inv = self.root / "inventory.json"
        inv.write_text(
            json.dumps(
                {"dependencies": [{"name": "com.a:b", "version": "1.0", "spdx": "MIT"}]}
            )
        )
        r = GradleAdapter(inv).parse(
            self.source('implementation("com.a:b:1.0")', "build.gradle", "gradle_build")
        )
        e = next(e for e in r.entities if e.family == "Dependency")
        self.assertEqual(e.metadata.extensions["spdx"], "MIT")
        self.assertEqual(e.knowledgeState, KnowledgeState.VERIFIED)

    def test_resolved_tree_keeps_transitive_edges(self):
        s = self.source(
            "<project><artifactId>x</artifactId></project>", "pom.xml", "maven_pom"
        )
        output = Mock(
            stdout="[INFO] +- com.a:b:jar:1.0:compile\n[INFO] |  \\- com.c:d:jar:2.0:compile\n"
        )
        with (
            patch("shutil.which", return_value="/mvn"),
            patch("subprocess.run", return_value=output),
        ):
            tree = MavenAdapter().resolve_tree(self.root)
        self.assertEqual(len(tree), 2)
        self.assertEqual(tree[1].sourceId, tree[0].targetId)

    def test_bad_xml_fails(self):
        with self.assertRaises(SourceAdapterError):
            MavenAdapter().parse(self.source("<broken", "pom.xml", "maven_pom"))


class JarAdapterTests(Fixture):
    def test_jar_coordinates_and_bytecode_public_api(self):
        import shutil, zipfile

        if not shutil.which("javac"):
            self.skipTest("JDK unavailable")
        java = self.root / "Foo.java"
        java.write_text(
            'package com.example; public class Foo { public String bar(int x) {return "x";} private void hidden() {} }'
        )
        subprocess.run(
            ["javac", "-d", str(self.root), str(java)], check=True, capture_output=True
        )
        jar = self.root / "example-1.2.3.jar"
        with zipfile.ZipFile(jar, "w") as z:
            z.write(self.root / "com/example/Foo.class", "com/example/Foo.class")
            z.writestr(
                "META-INF/MANIFEST.MF",
                "Implementation-Title: example\nImplementation-Version: 1.2.3\nImplementation-Vendor-Id: com.example\n",
            )
            z.writestr("config.properties", "x=y")
        s = Source("jar", str(jar), "jar", hashlib.sha256(jar.read_bytes()).hexdigest())
        r = JarAdapter().parse(s)
        dep = next(e for e in r.entities if e.family == "Dependency")
        self.assertEqual(dep.metadata.extensions["groupId"], "com.example")
        self.assertEqual(dep.metadata.extensions["version"], "1.2.3")
        self.assertTrue(
            any(e.family == "JavaClass" and e.label == "Foo" for e in r.entities)
        )
        self.assertTrue(
            any(e.family == "JavaMethod" and e.label == "bar" for e in r.entities)
        )
        self.assertFalse(any(e.label == "hidden" for e in r.entities))
        self.assertTrue(
            {"JavaPackage", "PublicApi", "Resource"} <= {e.family for e in r.entities}
        )
        self.assertTrue(LocalPipelineDriver().run(s, self.root).ok)

    def test_corrupt_jar_is_permanent(self):
        s = self.source("not zip", "x.jar", "jar")
        with self.assertRaises(SourceAdapterError):
            JarAdapter().parse(s)


class OpenSpecChangeAdapterTests(Fixture):
    def test_current_draft_archived_frontmatter_and_bodies(self):
        for prefix, status in [
            ("openspec/specs/cap", "active"),
            ("openspec/changes/demo/specs/cap", "draft"),
            ("openspec/changes/archive/2026-10-04-demo/specs/cap", "archived"),
        ]:
            text = "---\ncapability: example\nphase: 2\nkind: spec\npi_token: keep\n---\n# Example\n### Requirement: A\nMUST retain body.\n#### Scenario: A\nGiven body.\n## Phase 2 task coverage\npi_platform.ports.ingest.pipeline_driver\n"
            s = self.source(text, prefix + "/spec.md", "openspec")
            r = OpenSpecChangeAdapter().parse(s)
            spec = next(e for e in r.entities if e.family == "Specification")
            self.assertEqual(spec.metadata.extensions["capabilityId"], "example")
            self.assertEqual(spec.metadata.extensions["status"], status)
            self.assertEqual(spec.metadata.extensions["pi_token"], "keep")
            self.assertIn("SATISFIES", {x.family for x in r.relations})
            if status == "archived":
                self.assertFalse(any(e.family == "OpenSpecChange" for e in r.entities))
            cs = OpenSpecChunker().chunk(r.document, r.sections)
            self.assertIn("MUST retain body", cs[0].rawText)
            self.assertIn("Given body", cs[0].rawText)
        self.assertEqual(OpenSpecChangeAdapter().active_changes(self.root), ("demo",))


class ContextEnricherTests(Fixture):
    def chunks(self):
        s = self.source("# A\n<!-- requirement: REQ-123 -->\nbody", "psb/packing/a.md")
        r = MarkdownAdapter().parse(s)
        return MarkdownChunker().chunk(r.document, r.sections)

    def test_deterministic_domain_and_roundtrip(self):
        cs = self.chunks()
        e = LayeredContextEnricher()
        rule = DomainRule(
            "*/psb/packing/**",
            {
                "businessDomain": "PACKING",
                "system": "erp",
                "candidateEntities": ["Order"],
            },
        )
        ctx = EnricherContext(domain_rules=(rule,))
        enriched, reports = e.enrich(cs, ctx)
        c = enriched[0]
        self.assertEqual(c.chunk.metadata.requirementId, "REQ-123")
        self.assertEqual(c.chunk.metadata.businessDomain, "PACKING")
        self.assertEqual(c.chunk.provenance.knowledgeState, KnowledgeState.ASSUMPTION)
        self.assertIn("section: A", c.contextPrefix)
        self.assertEqual(
            to_canonical_json(c), to_canonical_json(e.enrich(cs, ctx)[0][0])
        )
        self.assertEqual(c, from_canonical_json(ContextualChunk, to_canonical_json(c)))

    def test_optional_llm_requires_binding_and_policy(self):
        cs = self.chunks()
        with self.assertRaises(EnricherError):
            LayeredContextEnricher().enrich(
                cs, EnricherContext(enable_optional_llm=True)
            )
        cs = tuple(
            dataclasses.replace(
                c, metadata=dataclasses.replace(c.metadata, policy="LOCAL_ONLY")
            )
            for c in cs
        )
        llm = lambda text, max_tokens: {
            "requirementId": "invented",
            "entities": ["guess"],
            "contextPrefix": "suggested",
        }
        out, _ = LayeredContextEnricher().enrich(
            cs,
            EnricherContext(
                enable_optional_llm=True,
                extra={"local_llm": llm, "allow_local_llm": True},
            ),
        )
        self.assertEqual(out[0].chunk.metadata.requirementId, "REQ-123")
        self.assertEqual(
            out[0].chunk.metadata.extensions["pi_assumption"]["entities"], ["guess"]
        )
        self.assertEqual(
            out[0].chunk.provenance.knowledgeState, KnowledgeState.ASSUMPTION
        )


class ContentAddressedProcessingTests(Fixture):
    def test_source_change_invalidates_old_bodies(self):
        cache = InMemoryRuntimeCache()
        d = LocalPipelineDriver(cache=cache)
        s = self.source("# A\nold body")
        r = d.run(s, self.root)
        self.assertTrue(r.ok)
        old = cache.source_record(s.id)["addresses"]
        changed = self.source("# A\nnew body")
        self.assertTrue(d.run(changed, self.root).ok)
        self.assertTrue(all(key not in cache._store for key in old))

    def test_deletion_marks_records_stale(self):
        cache = InMemoryRuntimeCache()
        scan = LocalSourceInboxScanner(cache)
        s = self.source("# A\nbody")
        ctx = LocalSourceInboxContext(self.root)
        source = scan.scan(ctx).registered_sources[0]
        self.assertTrue(LocalPipelineDriver(cache=cache).run(source, self.root).ok)
        keys = cache.source_record(source.id)["addresses"]
        Path(s.uri).unlink()
        scan.scan(ctx)
        self.assertTrue(any(b'"stale"' in cache._store[key] for key in keys))


class GitAdapterTests(Fixture):
    def test_existing_cli_port_and_tracked_inbox_filter(self):
        from pi_platform.adapters.git.cli_adapter import GitCliAdapter

        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "config",
                "user.email",
                "test@example.invalid",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Test"], check=True
        )
        self.source("tracked", "a.md")
        subprocess.run(["git", "-C", str(self.root), "add", "a.md"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-qm", "fixture"], check=True
        )
        self.source("untracked", "b.md")
        r = LocalSourceInboxScanner().scan(LocalSourceInboxContext(self.root))
        self.assertEqual([Path(s.uri).name for s in r.registered_sources], ["b.md"])
        self.assertTrue(GitCliAdapter().head(self.root))


class DriverFailureTests(Fixture):
    def test_transient_retries_and_required_parser_stops(self):
        source = self.source("text")
        parser = MarkdownAdapter()
        original = parser.parse
        calls = []

        def fail_then_parse(*args):
            calls.append(1)
            if len(calls) < 4:
                raise StageError(StageErrorCategory.TRANSIENT, "lock timeout")
            return original(*args)

        parser.parse = fail_then_parse
        registry = SourceAdapterRegistry()
        registry.register(parser)
        d = LocalPipelineDriver(parser_registry=registry, retry_delay=0)
        report = d.run(source, self.root)
        self.assertTrue(report.ok, report.error_message)
        self.assertEqual(report.stages[0].attempts, 4)
        missing = JavaStructuredAdapter(
            TreeSitterJavaSubprocess(command=("/missing/java-parser",), required=True)
        )
        registry.register(missing)
        java = self.source("class Foo {}", "Foo.java", "java_source")
        reports = d.run_many((java, source), self.root)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].error_category, "configuration_error")

    def test_cancel_flushes_and_stops(self):
        class Token(CancellationToken):
            value = False

            def cancel(self):
                self.value = True

            def is_cancelled(self):
                return self.value

        from pi_platform.ports.ingest.chunker import ChunkerRegistry

        token = Token()
        chunker = MarkdownChunker()
        original = chunker.chunk

        def cancel_after_chunk(*args):
            chunks = original(*args)
            token.cancel()
            return chunks

        chunker.chunk = cancel_after_chunk
        registry = ChunkerRegistry()
        registry.register(chunker)
        cache = InMemoryRuntimeCache()
        d = LocalPipelineDriver(chunker_registry=registry, cache=cache)
        reports = d.run_many(
            (self.source("body"), self.source("next", "next.md")),
            self.root,
            cancellation=token,
        )
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].error_category, "cancelled")
        self.assertTrue(any(b"body" in v for v in cache._store.values()))


class CliIngestionTests(Fixture):
    def test_cli_actual_ingestion_and_repeat(self):
        import sys

        self.source("# A\nactual cli body", "tmp/local/source/doc.md")
        command = [
            sys.executable,
            "-m",
            "pi_platform.cli",
            "ingest-sources",
            "--target",
            str(self.root),
        ]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        report = json.loads(first.stdout)["reports"][0]
        self.assertEqual(report["knowledge_state"], "unknown")
        self.assertTrue(
            (self.root / "tmp/local/pi-platform-ingest/ingestion.json").exists()
        )
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["reports"], [])

    def test_unknown_dependency_blocks_next_license_gate(self):
        import sys

        self.source(
            'implementation("com.unknown:lib:1.0")',
            "tmp/local/source/build.gradle",
            "gradle_build",
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pi_platform.cli",
                "ingest-sources",
                "--target",
                str(self.root),
            ],
            capture_output=True,
            check=True,
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pi_platform.cli",
                "license-gate",
                "--target",
                str(self.root),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("com.unknown:lib", result.stdout)


class StructuralStrategiesTests(Fixture):
    def test_requirements_messages_tables_architecture(self):
        from pi_platform.adapters.ingest.chunkers import (
            RequirementIdChunker,
            ProtocolMessageChunker,
            TableChunker,
            ArchitectureUnitChunker,
        )
        from pi_platform.ports.ingest.chunker import ChunkerContext

        source = self.source("# Root\nREQ-001 First\nREQ-002 Second\n## Child\nbody")
        r = MarkdownAdapter().parse(source)
        requirements = RequirementIdChunker().chunk(
            r.document, r.sections, ChunkerContext(extra={"min_chunk_bytes": 0})
        )
        self.assertTrue(any(c.rawText.startswith("REQ-001") for c in requirements))
        self.assertTrue(any(c.rawText.startswith("REQ-002") for c in requirements))
        source = self.source("message A {}\nmessage B {}", "protocol.txt", "plain_text")
        from pi_platform.adapters.fs.local_source_adapter import LocalSourceAdapter

        r = LocalSourceAdapter().parse(source)
        self.assertEqual(len(ProtocolMessageChunker().chunk(r.document, r.sections)), 2)
        source = self.source(
            "a,b\n" + "\n".join("value,value" for _ in range(100)),
            "table.txt",
            "plain_text",
        )
        r = LocalSourceAdapter().parse(source)
        cs = TableChunker().chunk(
            r.document, r.sections, ChunkerContext(max_chunk_bytes=100)
        )
        self.assertTrue(
            all(
                c.rawText.startswith("a,b\n") and len(c.rawText.encode()) <= 100
                for c in cs
            )
        )
        source = self.source("# Component\nroot\n## Module\nchild")
        r = MarkdownAdapter().parse(source)
        cs = ArchitectureUnitChunker().chunk(r.document, r.sections)
        self.assertEqual(cs[1].parentId, cs[0].id)
        self.assertIn(cs[1].id, cs[0].childIds)

    def test_phase1_metadata_bytes_unchanged_without_extensions(self):
        m = Metadata("doc", "1", "text")
        body = json.loads(to_canonical_json(m))
        self.assertNotIn("policy", body)
        self.assertNotIn("extensions", body)


class SourceJarPreferenceTests(Fixture):
    parser = JavaStructuredAdapterTests.parser

    def test_sibling_source_jar_hash_and_preferred_class(self):
        import zipfile

        parser = self.parser()
        if not parser.is_available():
            self.skipTest("optional Java parser packages absent")
        binary = self.root / "example.jar"
        sources = self.root / "example-sources.jar"
        with zipfile.ZipFile(binary, "w") as z:
            z.writestr("META-INF/MANIFEST.MF", "Implementation-Title: example\n")
        with zipfile.ZipFile(sources, "w") as z:
            z.writestr(
                "demo/Foo.java",
                "package demo; public class Foo { public void bar() {} }",
            )
        source = Source(
            "jar", str(binary), "jar", hashlib.sha256(binary.read_bytes()).hexdigest()
        )
        r = JarAdapter(parser).parse(source)
        cls = next(
            e for e in r.entities if e.family == "JavaClass" and e.label == "Foo"
        )
        self.assertEqual(
            cls.metadata.extensions["pi_evidence"]["sourceHash"],
            hashlib.sha256(sources.read_bytes()).hexdigest(),
        )
        self.assertIn("example-sources.jar!/demo/Foo.java", cls.metadata.sourcePath)
        self.assertEqual(
            to_canonical_json(r.entities),
            to_canonical_json(JarAdapter(parser).parse(source).entities),
        )


class OpenSpecDirectoryTests(Fixture):
    def test_change_directory_emits_one_change_and_spec_per_folder(self):
        for cap in ("one", "two"):
            self.source(
                "# Spec\n### Requirement: A\nMUST work.\n",
                f"openspec/changes/demo/specs/{cap}/spec.md",
                "openspec",
            )
        s = Source(
            "demo",
            str(self.root / "openspec/changes/demo"),
            "openspec",
            "directory-hash",
        )
        r = OpenSpecChangeAdapter().parse(s)
        self.assertEqual(sum(e.family == "OpenSpecChange" for e in r.entities), 1)
        self.assertEqual(sum(e.family == "Specification" for e in r.entities), 2)


class PolicyRefreshTests(Fixture):
    def test_unchanged_source_with_changed_policy_is_reingested(self):
        self.source("# A\nbody")
        cache = InMemoryRuntimeCache()
        scanner = LocalSourceInboxScanner(cache)
        first = scanner.scan(LocalSourceInboxContext(self.root))
        driver = LocalPipelineDriver(cache=cache)
        self.assertEqual(
            driver.run(first.registered_sources[0], self.root).knowledge_state,
            KnowledgeState.UNKNOWN,
        )
        self.assertFalse(
            scanner.scan(LocalSourceInboxContext(self.root)).registered_sources
        )
        changed = scanner.scan(
            LocalSourceInboxContext(
                self.root, default_policy=SourcePromotionPolicy.REFERENCE
            )
        )
        self.assertEqual(len(changed.registered_sources), 1)
        self.assertEqual(
            driver.run(changed.registered_sources[0], self.root).knowledge_state,
            KnowledgeState.ASSUMPTION,
        )

    def test_reference_promotes_metadata_only_snapshot_preserved_after_deletion(self):
        self.source("private body")
        scanner = LocalSourceInboxScanner()
        snapshot = self.root / "canonical"
        source = scanner.scan(
            LocalSourceInboxContext(
                self.root, default_policy=SourcePromotionPolicy.REFERENCE
            )
        ).registered_sources[0]
        scanner.promote(source, SourcePromotionPolicy.REFERENCE, snapshot)
        self.assertFalse((snapshot / source.id / "source").exists())
        source = dataclasses.replace(
            source, metadata=dataclasses.replace(source.metadata, policy="SNAPSHOT")
        )
        scanner.promote(source, SourcePromotionPolicy.SNAPSHOT, snapshot)
        Path(source.uri).unlink()
        self.assertEqual((snapshot / source.id / "source").read_text(), "private body")


if __name__ == "__main__":
    unittest.main()
