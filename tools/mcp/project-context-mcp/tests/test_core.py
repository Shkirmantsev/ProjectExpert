from pathlib import Path
import tempfile, unittest
from project_context_mcp.core import build_index, get_document, search, validate, _wiki_fingerprint, _read_recorded_fingerprint, state_path

class CoreTest(unittest.TestCase):
    def test_sections_keep_numeric_order(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wiki = root / '.ai/wiki'
            wiki.mkdir(parents=True)
            (wiki / 'INDEX.md').write_text('---\nid: wiki.index\n---\n' + ''.join(
                f'# Section {i}\nvalue-{i}\n' for i in range(12)))
            build_index(root)
            content = get_document(root, 'wiki.index')['content']
            self.assertLess(content.index('value-9'), content.index('value-10'))

    def test_failed_rebuild_preserves_previous_index(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wiki = root / '.ai/wiki'
            wiki.mkdir(parents=True)
            page = '---\nid: wiki.index\n---\n# Index\nReservation locking.\n'
            (wiki / 'INDEX.md').write_text(page)
            build_index(root)
            (wiki / 'duplicate.md').write_text(page)
            with self.assertRaises(Exception):
                build_index(root)
            self.assertEqual('wiki.index', search(root, 'reservation')[0]['id'])

    def test_wiki_symlink_cannot_read_outside_project(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'project'
            wiki = root / '.ai/wiki'
            wiki.mkdir(parents=True)
            outside = Path(d) / 'private.md'
            outside.write_text('# Private\nprivate-canary\n')
            (wiki / 'leak.md').symlink_to(outside)
            self.assertEqual(0, build_index(root)['documents'])

    def test_markdown_index_search_and_get(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); wiki=root/'.ai/wiki'; wiki.mkdir(parents=True)
            (wiki/'INDEX.md').write_text('---\nid: wiki.index\ntitle: Index\nkind: index\nstatus: active\nsummary: nav\n---\n# Index\nReservation locking lives here.\n', encoding='utf-8')
            state=build_index(root); self.assertEqual(1,state['documents'])
            self.assertEqual('wiki.index', search(root,'reservation locking')[0]['id'])
            self.assertIn('Reservation', get_document(root,'wiki.index')['content'])
            self.assertTrue(validate(root)['ok'])

    def test_search_returns_top_k_distinct_documents(self):
        """Regression: ``top_k`` deduplication must happen BEFORE the
        final LIMIT, otherwise a small ``top_k`` request against a few
        documents with many chunks returns fewer than ``top_k``
        distinct documents.
        """

        with tempfile.TemporaryDirectory() as d:
            root = Path(d); wiki = root / '.ai/wiki'; wiki.mkdir(parents=True)
            # Single document with many chunks via multiple headings.
            (wiki / 'alpha.md').write_text(
                '---\nid: wiki.alpha\ntitle: Alpha\n---\n'
                + ''.join(f'# Section {n}\nreservation locking\n' for n in range(5)),
                encoding='utf-8',
            )
            for doc_id in ('bravo', 'charlie', 'delta'):
                (wiki / f'{doc_id}.md').write_text(
                    f'---\nid: wiki.{doc_id}\ntitle: {doc_id.title()}\n---\n'
                    f'# {doc_id.title()}\nreservation locking\n',
                    encoding='utf-8',
                )
            build_index(root)
            hits = search(root, 'reservation', top_k=4)
            self.assertGreaterEqual(len(hits), 4,
                f'top_k=4 must yield >=4 hits, got {len(hits)}: {hits!r}')
            self.assertEqual(len(hits), len({h['id'] for h in hits}),
                f'hits must all be distinct documents: {hits!r}')

    def test_wiki_edit_triggers_index_rebuild(self):
        """Regression: a wiki content change must invalidate the
        cached ``knowledge.db``; ``kb_search`` MUST NOT return hits
        from the previous version.
        """

        with tempfile.TemporaryDirectory() as d:
            root = Path(d); wiki = root / '.ai/wiki'; wiki.mkdir(parents=True)
            (wiki / 'INDEX.md').write_text(
                '---\nid: wiki.index\n---\n# Index\noldtoken locking.\n',
                encoding='utf-8',
            )
            build_index(root)
            self.assertEqual('wiki.index', search(root, 'oldtoken')[0]['id'])
            # Mutate the wiki: add a new token that only appears after
            # the rebuild.
            (wiki / 'OTHER.md').write_text(
                '---\nid: wiki.other\n---\n# Other\nnewtoken here.\n',
                encoding='utf-8',
            )
            # ``search`` triggers ``ensure_index`` which MUST detect the
            # fingerprint mismatch and rebuild.
            hits = search(root, 'newtoken')
            self.assertEqual('wiki.other', hits[0]['id'],
                f'newtoken must surface wiki.other after rebuild: {hits!r}')

    def test_fingerprint_recorded_after_build(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); wiki = root / '.ai/wiki'; wiki.mkdir(parents=True)
            (wiki / 'INDEX.md').write_text(
                '---\nid: wiki.index\n---\n# Index\nReservation locking.\n',
                encoding='utf-8',
            )
            state = build_index(root)
            recorded = _read_recorded_fingerprint(root)
            self.assertIsNotNone(recorded)
            self.assertEqual(recorded, state['wiki_fingerprint'])

if __name__=='__main__': unittest.main()
