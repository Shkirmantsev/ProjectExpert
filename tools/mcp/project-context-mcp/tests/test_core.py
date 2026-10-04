from pathlib import Path
import tempfile, unittest
from project_context_mcp.core import build_index, get_document, search, validate

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
if __name__=='__main__': unittest.main()
