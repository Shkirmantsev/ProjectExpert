import json
import pathlib
import shutil
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lesson_candidate.py"
CANDIDATES = ROOT / "tmp" / "local" / "lesson-candidates"


def run_json(*args: str, check: bool = True):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    payload = json.loads(result.stdout) if result.stdout.strip() else None
    return result, payload


class LessonCandidateTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(CANDIDATES, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(CANDIDATES, ignore_errors=True)

    def propose(self):
        return run_json(
            "propose",
            "--failure-mode",
            "Router activated a graph skill for exact lookup",
            "--root-cause",
            "A generic keyword outweighed the explicit lookup intent",
            "--prevention",
            "Keep exact search ahead of graph retrieval",
            "--evidence",
            "tests/test_skill_runtime.py::test_ordinary_search_does_not_activate_graphify",
            "--scope",
            "project",
            "--confidence",
            "0.94",
        )[1]

    def test_proposal_is_content_addressed_and_never_auto_promoted(self):
        first = self.propose()
        second = self.propose()
        self.assertEqual(first, second)
        self.assertRegex(first["id"], r"^LESSON-[0-9A-F]{16}$")
        self.assertEqual(first["status"], "candidate")
        self.assertFalse(first["automatic_promotion"])
        self.assertEqual(len(list(CANDIDATES.glob("*.json"))), 1)
        self.assertNotIn("reasoning", json.dumps(first).lower())

    def test_validation_records_eval_but_still_requires_manual_promotion(self):
        candidate = self.propose()
        _, validated = run_json(
            "validate",
            "--id",
            candidate["id"],
            "--eval-ref",
            "tests/test_skill_runtime.py",
            "--reviewer",
            "independent-review",
            "--result",
            "passed",
        )
        self.assertEqual(validated["status"], "validated")
        self.assertEqual(validated["promotion"], "manual-review-required")

    def test_forbidden_authority_expansion_is_rejected(self):
        result, payload = run_json(
            "propose",
            "--failure-mode",
            "A command was denied",
            "--root-cause",
            "The safety policy worked",
            "--prevention",
            "Grant all tool permissions automatically",
            "--evidence",
            "task://unsafe",
            "--scope",
            "project",
            "--confidence",
            "0.9",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "forbidden_self_modification")


if __name__ == "__main__":
    unittest.main()
