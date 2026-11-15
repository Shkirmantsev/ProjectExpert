"""Real document types and source/CAS persistence; no model quality claim."""
import io
import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS

from pi_platform.adapters.pdf.real_docling import is_docling_available
from pi_platform.adapters.sync.portable_format import PortableSnapshotError, sha
from tests.test_portable_canonical_sync import PortableProductionTests, git


@unittest.skipUnless(is_docling_available(), 'optional documents dependencies unavailable')
class PortablePdfTests(PortableProductionTests):
    def test_figure_vectors_restore_without_docling_or_local_crops(self):
        from scripts.generate_pdf_fixtures import build_pdf
        from tests.test_pdf_production_mapping import vendor_document
        from pi_platform.adapters.pdf.docling_pdf_adapter import build_real_docling_pdf_adapter
        from pi_platform.core.orchestration.repository_indexing import build_production_retrieval_runtime, index_repository
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        from pi_platform.core.control.retrieval_settings import RetrievalSettings
        from pi_platform.adapters.orchestration.knowledge_sync import KnowledgeSyncCoordinator
        (self.root / 'guide.pdf').write_bytes(build_pdf(page_count=1, title='Public manual'))
        git(self.root, 'add', 'guide.pdf')
        git(self.root, 'commit', '-m', 'PDF fixture')
        converter = NS(inspect_pdf=lambda _: (True,), convert=lambda *a, **kw: vendor_document(1))
        def parser(*args, **kwargs):
            return build_real_docling_pdf_adapter(*args, **kwargs, docling_converter=converter)
        def runtime(**kwargs):
            kwargs.update(embedding_alias='hashing', startup_profile='minimal', prefer_real_usearch=False)
            return build_production_retrieval_runtime(**kwargs)
        with patch.dict(os.environ, {'PI_STARTUP_PROFILE': 'production', 'PI_EMBEDDING_MODEL': 'gemma',
                                    'PI_DOCLING_ENABLED': '1', 'PI_PREPARE_DOCLING': '0', 'PI_DENSE_INDEX': 'usearch'}), patch(
                'pi_platform.adapters.pdf.docling_pdf_adapter.build_real_docling_pdf_adapter', parser), patch(
                'pi_platform.adapters.pdf.runtime_projection.PdfRuntimeProjection',
                lambda _: lambda body: (body['rawText'],)), patch(
                'pi_platform.core.orchestration.repository_indexing.build_production_retrieval_runtime', runtime):
            first = self.build()
            self.publish_runtime(first)
            automatic = self.stage(vectors=True)
            self.assertEqual(automatic['sources'], 3, 'Safe PDF text must export under the project-wide policy without a path approval')
            KnowledgeSyncCoordinator(self.root, self.cache(), authenticated_operator=True).review_source('guide.pdf', 'public')
            self.publish(self.stage(vectors=True))
            clone = self.clone()
            with patch('pi_platform.adapters.ingest.local_pipeline_driver.LocalPipelineDriver.run_many',
                       side_effect=AssertionError('restore scheduled a source parser')), patch(
                       'pi_platform.adapters.retrieval.hashing_embedding_model.HashingEmbeddingAdapter.embed_request',
                       side_effect=AssertionError('restore called embedding model')), patch(
                       'pi_platform.adapters.pdf.portable_assets.ensure_local_asset',
                       side_effect=AssertionError('matching vectors required pixels')):
                restored = index_repository(target=clone, cache_root=self.cache(clone),
                    inventory=RepositorySourceDiscovery().discover(clone), previous_inventory=None,
                    settings=RetrievalSettings(), restore_only=True)
            self.assertEqual(restored.extra['indexing_report'].embedded_count, 0)
            self.assertEqual(first.extra['chunk_ids'], restored.extra['chunk_ids'])
            self.assertFalse((self.cache(clone) / 'document-assets').exists())
            figures = [h for h in restored.extra['chunk_catalog'].values() if h.metadata.extensions.get('pdf_asset')]
            self.assertTrue(figures)
            self.assertTrue(any(h.metadata.extensions.get('table') for h in restored.extra['chunk_catalog'].values()))

    def test_missing_crop_is_regenerated_from_only_its_page_and_verified(self):
        from tests.test_pdf_production_mapping import vendor_document
        from pi_platform.adapters.pdf.portable_assets import ensure_local_asset, render_profile
        document = vendor_document(2)
        picture = document.pictures[0]
        stream = io.BytesIO()
        picture.get_image(document).save(stream, format='PNG')
        data = stream.getvalue()
        source = self.root / 'guide.pdf'
        source.write_bytes(b'original PDF source fixture')
        descriptor = {'schema': 'pdf-figure/1', 'sourcePath': 'guide.pdf', 'sourceHash': sha(source.read_bytes()),
            'assetId': 'figure-2', 'byteHash': sha(data), 'page': 2, 'bbox': [10., 20., 100., 120.],
            'renderProfile': render_profile(), 'strategyVersion': 'fixture/1'}
        calls = []
        def convert(path, **kwargs):
            calls.append(kwargs)
            return document
        converter = NS(inspect_pdf=lambda _: (True, False, True), convert=convert)
        path = ensure_local_asset(self.root, self.cache(), descriptor, converter=converter)
        self.assertEqual(calls, [{'page_range': (2, 2), 'do_ocr': True}])
        from pathlib import Path
        self.assertEqual(Path(path).read_bytes(), data)
        ensure_local_asset(self.root, self.cache(), descriptor, converter=converter)
        self.assertEqual(len(calls), 1)
        Path(path).unlink()
        with self.assertRaisesRegex(PortableSnapshotError, 'profile'):
            ensure_local_asset(self.root, self.cache(), {**descriptor, 'renderProfile': 'a' * 64}, converter=converter)
        source.write_bytes(b'edited source')
        with self.assertRaisesRegex(PortableSnapshotError, 'changed'):
            ensure_local_asset(self.root, self.cache(), descriptor, converter=converter)
        self.assertEqual(len(calls), 1)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(PortablePdfTests(name) for name in PortablePdfTests.__dict__ if name.startswith('test_'))
