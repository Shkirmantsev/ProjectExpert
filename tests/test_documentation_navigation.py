"""Keep documentation discoverable from the project entry point."""
from pathlib import Path
import re
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def local_links(path):
    text = re.sub(r'```.*?```', '', path.read_text(encoding="utf-8"), flags=re.S)
    for href in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
        if re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', href) or href.startswith('#'):
            continue
        yield (path.parent / unquote(href.split('#', 1)[0])).resolve()


class DocumentationNavigationTests(unittest.TestCase):
    def test_documentation_is_reachable_from_project_readme(self):
        pending = [ROOT / 'README.md']
        seen = set()
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            for target in local_links(path):
                if target.is_dir():
                    target = target / 'README.md'
                if target.is_file() and target.suffix == '.md' and target.is_relative_to(ROOT):
                    pending.append(target)
        missing = sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'docs').rglob('*.md') if p not in seen)
        self.assertEqual([], missing, 'Documentation pages need an incoming navigation link')

    def test_navigation_entry_points_have_valid_targets(self):
        for name in ('README.md', 'AGENTS.md', 'docs/README.md', 'docs/PROJECT_STRUCTURE.md',
                     'docs/conventions/README.md', 'openspec/README.md', '.ai/wiki/INDEX.md'):
            for target in local_links(ROOT / name):
                with self.subTest(source=name, target=target):
                    self.assertTrue(target.exists())
