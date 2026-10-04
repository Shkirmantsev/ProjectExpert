import importlib.util, pathlib, unittest, sys
from unittest import mock
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('hs', ROOT / 'scripts/hermes_host_setup.py')
hs = importlib.util.module_from_spec(spec); spec.loader.exec_module(hs)

class HostSetupTests(unittest.TestCase):
    def test_parent_chain(self):
        p = list(hs.parent_chain(pathlib.Path('/home/alice/projects/repo')))
        self.assertEqual(p, [pathlib.Path('/home/alice'), pathlib.Path('/home/alice/projects')])

    def test_no_workspace_symlink_created(self):
        text = (ROOT / 'scripts/hermes_host_setup.py').read_text()
        self.assertNotIn('ln", "-s', text)
        self.assertNotIn('sudo("ln", "-s"', text)

    def test_parent_chain_stops_at_filesystem_root(self):
        root = pathlib.Path.cwd().anchor
        self.assertEqual(list(hs.parent_chain(pathlib.Path(root))), [])

    def test_windows_host_setup_reports_unsupported_optional_adapter(self):
        with mock.patch.object(hs.os, "name", "nt"), self.assertRaisesRegex(SystemExit, "POSIX host"):
            hs.main()
