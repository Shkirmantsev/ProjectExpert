"""Phase 7 §59.16 Control Plane v0.8 panel registry tests.

Change Package I of the v0.8 refinement
(``improve-ingestion-retrieval-local-models``) extends the
existing Control Plane diagnostics with the six panels documented
in plan §32 (Ingestion, Chunking, Embeddings, Retrieval,
Accelerator, Evaluation). These tests assert:

* the panel set ships exactly six panels with the documented IDs;
* every descriptor passes the Phase 7 §59.16
  no-arbitrary-JavaScript validation;
* the registry serialisation stays byte-stable;
* registering twice is idempotent and does not raise.
"""

from __future__ import annotations

import json
import unittest

from pi_platform.core.control.diagnostics.v0_8_panels import (
    PANEL_IDS,
    V08_PANEL_VERSION,
    build_v0_8_panels,
    register_v0_8_panels,
    serialise_v0_8_panels,
)
from pi_platform.core.control.ui_extensions import DefaultUiExtensionRegistry
from pi_platform.ports.control.ui_extensions import (
    UiExtensionDescriptor,
    UiExtensionKind,
)


__all__ = ["V08ControlPlanePanelTests"]


class V08ControlPlanePanelTests(unittest.TestCase):

    def test_panel_set_has_six_panels(self) -> None:
        bundle = build_v0_8_panels()
        self.assertEqual(len(bundle.panels), 6)
        self.assertEqual(bundle.ids(), PANEL_IDS)

    def test_panel_ids_match_plan_section_32(self) -> None:
        # Plan §32 names the six panels Ingestion, Chunking,
        # Embeddings, Retrieval, Accelerator, Evaluation. The
        # registry prefixes them with ``ui.v0_8.`` so they coexist
        # with Phase 7 panels; this test pins the mapping.
        bundle = build_v0_8_panels()
        expected_ids = {
            "ui.v0_8.ingestion",
            "ui.v0_8.chunking",
            "ui.v0_8.embeddings",
            "ui.v0_8.retrieval",
            "ui.v0_8.accelerator",
            "ui.v0_8.evaluation",
        }
        self.assertEqual(set(bundle.ids()), expected_ids)

    def test_panel_kind_is_status_panel(self) -> None:
        bundle = build_v0_8_panels()
        for descriptor in bundle.panels:
            self.assertEqual(descriptor.kind, UiExtensionKind.STATUS_PANEL)

    def test_panel_routes_are_namespaced(self) -> None:
        bundle = build_v0_8_panels()
        for descriptor in bundle.panels:
            self.assertTrue(
                descriptor.route.startswith("/diagnostics/"),
                f"panel {descriptor.id!r} route not namespaced: "
                f"{descriptor.route!r}",
            )

    def test_panel_configuration_schema_is_read_only(self) -> None:
        bundle = build_v0_8_panels()
        for descriptor in bundle.panels:
            schema = json.loads(descriptor.configuration_schema)
            self.assertEqual(schema["additionalProperties"], False)
            self.assertTrue(
                schema["title"].startswith(
                    f"v0.8 panel schema {V08_PANEL_VERSION}",
                ),
                f"panel {descriptor.id!r} title: {schema['title']!r}",
            )
            for prop_name, prop in schema["properties"].items():
                self.assertTrue(
                    prop.get("readOnly", False),
                    f"panel {descriptor.id!r} field {prop_name!r} is not "
                    f"read-only",
                )

    def test_panel_schema_lists_documented_fields(self) -> None:
        bundle = build_v0_8_panels()
        expected = {
            "ui.v0_8.ingestion": {
                "pdfParser", "ocrMode", "pageBatchSize", "activeJobs",
            },
            "ui.v0_8.chunking": {
                "tokenizer", "targetTokens", "maxTokens", "chunkProfile",
            },
            "ui.v0_8.embeddings": {
                "activeModel", "modelRevision", "device", "dimension",
                "normalization", "indexCompatibility",
            },
            "ui.v0_8.retrieval": {
                "denseCandidates", "lexicalCandidates",
                "primaryPoolSize", "reservePoolSize",
                "rerankerProfile", "debugTrace",
            },
            "ui.v0_8.accelerator": {
                "health", "device", "memory", "fallbackState",
            },
            "ui.v0_8.evaluation": {
                "latestReport", "lastRunAt", "scope",
            },
        }
        for descriptor in bundle.panels:
            schema = json.loads(descriptor.configuration_schema)
            actual = set(schema["properties"].keys())
            self.assertEqual(
                actual, expected[descriptor.id],
                f"panel {descriptor.id!r} schema mismatch",
            )

    def test_register_succeeds_against_default_registry(self) -> None:
        registry = DefaultUiExtensionRegistry()
        bundle = register_v0_8_panels(registry)
        registered_ids = {d.id for d in registry.list()}
        self.assertEqual(registered_ids, set(bundle.ids()))

    def test_register_is_idempotent(self) -> None:
        registry = DefaultUiExtensionRegistry()
        register_v0_8_panels(registry)
        # Re-registering the same bundle must not raise and must
        # not change the set of registered descriptors.
        before = {d.id for d in registry.list()}
        register_v0_8_panels(registry)
        after = {d.id for d in registry.list()}
        self.assertEqual(before, after)

    def test_serialisation_is_byte_stable(self) -> None:
        registry = DefaultUiExtensionRegistry()
        register_v0_8_panels(registry)
        first = serialise_v0_8_panels(registry)
        second = serialise_v0_8_panels(registry)
        self.assertEqual(first, second)
        payload = json.loads(first)
        ids = [item["id"] for item in payload["items"]]
        # The registry sorts by descriptor id; assert both the
        # declared and sorted orders agree on the v0.8 prefix.
        self.assertEqual(ids, sorted(PANEL_IDS))
        for descriptor_id in ids:
            self.assertTrue(descriptor_id.startswith("ui.v0_8."))

    def test_panel_by_id_lookup(self) -> None:
        bundle = build_v0_8_panels()
        for descriptor in bundle.panels:
            self.assertIs(bundle.by_id(descriptor.id), descriptor)
        self.assertIsNone(bundle.by_id("ui.v0_8.unknown"))

    def test_descriptors_reject_javascript_payloads(self) -> None:
        # §59.16 keeps applying: the default registry must reject
        # any descriptor that smuggles JavaScript through the
        # configuration schema. Confirm the v0.8 panels are not
        # such a vehicle.
        from pi_platform.ports.control.ui_extensions import (
            InvalidUiExtensionDescriptorError,
        )
        registry = DefaultUiExtensionRegistry()
        with self.assertRaises(InvalidUiExtensionDescriptorError):
            registry.register(UiExtensionDescriptor(
                id="ui.v0_8.bad",
                kind=UiExtensionKind.STATUS_PANEL,
                title='<script>alert("xss")</script>',
            ))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()