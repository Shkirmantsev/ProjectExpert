import re
import unittest

from hermes_worker_mcp.native_context import instructions, native_session_id, validate_project_root


class NativeContextTests(unittest.TestCase):
    def test_absolute_root_required(self):
        with self.assertRaises(ValueError):
            validate_project_root("repo")
        with self.assertRaises(ValueError):
            validate_project_root("/")

    def test_allowed_roots_are_canonical_and_server_enforced(self):
        allowed = "/main/projects/repo"
        self.assertEqual(validate_project_root(allowed, (allowed,)), allowed)
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_project_root("/main/projects/other", (allowed,))
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_project_root(allowed + "/child", (allowed,))

    def test_context_is_native_not_bridge(self):
        text = instructions("/home/user/repo")
        self.assertIn("native remote Hermes Agent", text)
        self.assertIn("/home/user/repo", text)
        self.assertIn("YOUR OWN Hermes tools", text)
        self.assertNotIn("bridge_token", text.lower())

    def test_fresh_session_is_default(self):
        a = native_session_id("/a/b")
        b = native_session_id("/a/b")
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^claude-hermes-[0-9a-f]{10}-[0-9a-f]{12}$")

    def test_explicit_session_is_preserved_and_validated(self):
        self.assertEqual(native_session_id("/a/b", "existing.session-1"), "existing.session-1")
        with self.assertRaises(ValueError):
            native_session_id("/a/b", "invalid session id")
