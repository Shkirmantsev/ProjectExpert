import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import skill_router
import sync_skills
ROUTER = ROOT / "scripts" / "skill_router.py"
SESSIONS = ROOT / "scripts" / "session_state.py"

CORE_SKILL_NAMES = [
    "project-safety",
    "session-checkpoint",
    "skill-router",
    "verification",
]
OPENSPEC_SKILL_NAMES = [
    "openspec-apply-change",
    "openspec-archive-change",
    "openspec-explore",
    "openspec-propose",
    "openspec-sync-specs",
    "openspec-update-change",
]


def run_json(script: pathlib.Path, *args: str, check: bool = True):
    result = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(
            f"command failed ({result.returncode}): {result.stderr or result.stdout}"
        )
    payload = json.loads(result.stdout) if result.stdout.strip() else None
    return result, payload


class SkillRouterTests(unittest.TestCase):
    def route(self, task: str, profile: str = "balanced"):
        return skill_router.build_plan(task, profile)

    def test_explicit_optional_skill_name_wins_without_loading_unrelated_skills(self):
        plan = self.route("Use the humanizer skill on this product announcement")
        names = [item["name"] for item in plan["required_skills"]]
        self.assertIn("humanizer", names)
        self.assertNotIn("graphify", names)
        self.assertLessEqual(len(plan["required_skills"]), 5)

    def test_alias_resolves_duplicate_grill_skill_to_one_canonical_skill(self):
        plan = self.route("Please use grill me to stress-test this product plan")
        names = [item["name"] for item in plan["required_skills"]]
        self.assertEqual(names.count("grilling"), 1)
        self.assertNotIn("grill-me", names)

    def test_bug_fix_routes_debugging_and_verification_but_not_every_workflow(self):
        plan = self.route(
            "Fix an intermittent Python session restore bug and add a regression test"
        )
        names = [item["name"] for item in plan["required_skills"]]
        self.assertIn("systematic-debugging", names)
        self.assertIn("verification", names)
        self.assertNotIn("obsidian-cli", names)
        self.assertNotIn("last30days", names)

    def test_local_small_profile_has_a_strict_activation_cap_and_simple_contract(self):
        plan = self.route(
            "Investigate, fix, refactor, review and verify a flaky Python migration",
            profile="local-small",
        )
        self.assertLessEqual(len(plan["required_skills"]), 4)
        self.assertEqual(plan["execution_contract"]["max_steps"], 8)
        self.assertTrue(plan["execution_contract"]["require_verification"])

    def test_equivalent_request_is_serialized_deterministically(self):
        first = self.route("Review this code change for regressions")
        second = self.route("Review this code change for regressions")
        self.assertEqual(first, second)

    def test_ordinary_search_does_not_activate_graphify(self):
        plan = self.route("Find the exact definition of configure_opencode in this repo")
        names = [item["name"] for item in plan["required_skills"]]
        self.assertNotIn("graphify", names)

    def test_maven_analysis_routes_without_capturing_gradle_only_work(self):
        maven = self.route(
            "Which transitive dependencies does com.example.Widget pull in this Maven project?"
        )
        gradle = self.route("Resolve the Gradle dependency graph for this Java service")
        self.assertIn(
            "java-maven-jar-analysis",
            [item["name"] for item in maven["required_skills"]],
        )
        self.assertNotIn(
            "java-maven-jar-analysis",
            [item["name"] for item in gradle["required_skills"]],
        )

    def test_hermes_delegation_keeps_transitive_context_dependencies_under_cap(self):
        plan = self.route(
            "Delegate to Hermes with a bounded context pack", profile="local-small"
        )
        names = [item["name"] for item in plan["required_skills"]]
        self.assertEqual(
            set(names),
            {"hermes-delegation", "delegation", "harness-project-access", "context-builder"},
        )
        self.assertLessEqual(len(names), 4)

    def test_small_core_and_openspec_integration_are_directly_discoverable(self):
        exposed = sorted(
            p.parent.name
            for p in (ROOT / ".agents" / "skills").glob("*/SKILL.md")
        )
        self.assertTrue(
            set(CORE_SKILL_NAMES + OPENSPEC_SKILL_NAMES).issubset(exposed)
        )
        self.assertEqual(
            [path.name for path in sync_skills.exposed_skills()], CORE_SKILL_NAMES
        )
        library = ROOT / ".agents" / "skills" / "catalog"
        self.assertGreaterEqual(len(list(library.glob("*/SKILL.md"))), 39)

    def test_local_sync_copies_core_and_preserves_openspec_owned_skills(self):
        with tempfile.TemporaryDirectory() as raw:
            fixture = pathlib.Path(raw)
            source = fixture / ".agents" / "skills"
            catalog = source / "catalog"
            claude = fixture / ".claude" / "skills"
            for name in CORE_SKILL_NAMES:
                skill = source / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(f"source {name}\n")
            optional = catalog / "optional"
            optional.mkdir(parents=True)
            (optional / "SKILL.md").write_text("optional\n")
            source_openspec = source / "openspec-propose"
            source_openspec.mkdir()
            (source_openspec / "SKILL.md").write_text("codex generated\n")
            claude_openspec = claude / "openspec-propose"
            claude_openspec.mkdir(parents=True)
            (claude_openspec / "SKILL.md").write_text("claude generated\n")
            (claude_openspec / "owner-marker").write_text("openspec\n")
            stale_catalog = claude / "optional"
            stale_catalog.mkdir()
            (stale_catalog / "SKILL.md").write_text("stale\n")

            with (
                mock.patch.object(sync_skills, "SOURCE", source),
                mock.patch.object(sync_skills, "CATALOG", catalog),
                mock.patch.object(sync_skills, "CLAUDE", claude),
                mock.patch.object(sync_skills, "OPENCODE", fixture / ".opencode" / "skills"),
            ):
                sync_skills.local()

            self.assertEqual(
                sorted(path.parent.name for path in claude.glob("*/SKILL.md")),
                sorted(CORE_SKILL_NAMES + ["openspec-propose"]),
            )
            self.assertEqual(
                (claude_openspec / "SKILL.md").read_text(), "claude generated\n"
            )
            self.assertTrue((claude_openspec / "owner-marker").is_file())
            self.assertFalse(stale_catalog.exists())


class SessionStateTests(unittest.TestCase):
    session_id = "TEST-SKILL-RUNTIME"

    def setUp(self):
        self.state_home = ROOT / "tmp" / "local" / "test-session-state"
        self.legacy_root = ROOT / "tmp" / "local" / "test-legacy-sessions"
        self.session_file = self.state_home / "handoffs" / f"{self.session_id}.json"
        self.current_file = self.state_home / "CURRENT.md"
        self.fixture = ROOT / "tmp" / "local" / "session-state-fixture.txt"
        self.fixture.parent.mkdir(parents=True, exist_ok=True)
        self.fixture.write_text("v1\n", encoding="utf-8")
        shutil.rmtree(self.state_home, ignore_errors=True)
        shutil.rmtree(self.legacy_root, ignore_errors=True)
        self.environment = mock.patch.dict(
            os.environ,
            {
                "HARNESS_SESSION_STATE_HOME": str(self.state_home.relative_to(ROOT)),
                "HARNESS_SESSION_LEGACY_ROOT": str(self.legacy_root.relative_to(ROOT)),
            },
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        shutil.rmtree(self.state_home, ignore_errors=True)
        shutil.rmtree(self.legacy_root, ignore_errors=True)
        self.fixture.unlink(missing_ok=True)

    def test_lifecycle_updates_generated_current_handoff_and_resumes_without_id(self):
        run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "Keep handoff state current",
            "--acceptance",
            "fresh sessions recover the task",
            "--todo",
            "implement persistence",
            "--context",
            "openspec/changes/automatic-session-handoff",
            "--openspec-change",
            "automatic-session-handoff",
        )
        current = self.current_file.read_text(encoding="utf-8")
        self.assertIn(f"harness-session-id: {self.session_id}", current)
        self.assertIn("Keep handoff state current", current)
        self.assertIn("implement persistence", current)

        run_json(
            SESSIONS,
            "checkpoint",
            "--status",
            "executing",
            "--done",
            "implement persistence",
            "--todo",
            "run verification",
            "--file",
            str(self.fixture.relative_to(ROOT)),
            "--next-action",
            "Run focused tests",
        )
        current = self.current_file.read_text(encoding="utf-8")
        self.assertIn("- implement persistence", current)
        self.assertIn("- run verification", current)
        self.assertIn("Run focused tests", current)
        self.assertTrue(self.session_file.is_file())

        result, resumed = run_json(SESSIONS, "resume")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(resumed["session"]["id"], self.session_id)
        self.assertEqual(resumed["integrity"]["status"], "clean")

    def test_start_protects_an_incomplete_current_task(self):
        run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "First unfinished task",
        )
        result, payload = run_json(
            SESSIONS,
            "start",
            "--id",
            "SECOND-TEST-SESSION",
            "--goal",
            "Second task",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "active_session_exists")

    def test_verify_rejects_a_stale_or_manually_edited_current_view(self):
        run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "Detect split handoff state",
        )
        self.current_file.write_text(
            self.current_file.read_text(encoding="utf-8") + "manual edit\n",
            encoding="utf-8",
        )
        result, payload = run_json(SESSIONS, "verify", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "current_state_out_of_sync")

    def test_legacy_checkpoint_is_promoted_on_update(self):
        _, started = run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "Migrate old checkpoint",
        )
        shutil.rmtree(self.state_home)
        legacy_file = self.legacy_root / self.session_id / "state.json"
        legacy_file.parent.mkdir(parents=True)
        legacy_file.write_text(json.dumps(started), encoding="utf-8")

        run_json(SESSIONS, "resume", "--id", self.session_id)
        run_json(
            SESSIONS,
            "checkpoint",
            "--done",
            "legacy checkpoint promoted",
        )
        self.assertTrue(self.session_file.is_file())
        promoted = json.loads(self.session_file.read_text(encoding="utf-8"))
        self.assertEqual(promoted["progress"]["done"], ["legacy checkpoint promoted"])

    def test_checkpoint_round_trip_and_resume_hash_validation(self):
        _, started = run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "Prove resumable state",
            "--acceptance",
            "resume validates working files",
        )
        self.assertEqual(started["task"]["status"], "planning")

        _, checkpoint = run_json(
            SESSIONS,
            "checkpoint",
            "--id",
            self.session_id,
            "--status",
            "verifying",
            "--done",
            "router implemented",
            "--todo",
            "run tests",
            "--verified",
            "router unit tests passed",
            "--file",
            str(self.fixture.relative_to(ROOT)),
            "--next-action",
            "Run the focused unit test",
            "--steps-used",
            "3",
        )
        self.assertEqual(checkpoint["progress"]["done"], ["router implemented"])
        self.assertEqual(checkpoint["budgets"]["steps_used"], 3)

        result, resumed = run_json(SESSIONS, "resume", "--id", self.session_id)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(resumed["integrity"]["status"], "clean")
        self.assertNotIn("reasoning", json.dumps(resumed).lower())

        self.fixture.write_text("v2\n", encoding="utf-8")
        result, resumed = run_json(
            SESSIONS, "resume", "--id", self.session_id, check=False
        )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(resumed["integrity"]["status"], "drifted")

    def test_checkpoint_rejects_working_files_outside_project(self):
        run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "Reject escaped paths",
        )
        result, payload = run_json(
            SESSIONS,
            "checkpoint",
            "--id",
            self.session_id,
            "--file",
            "/etc/hosts",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "path_outside_project")

    def test_checkpoint_rejects_completion_that_skips_verification_and_review(self):
        run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "Enforce the goal state machine",
        )
        result, payload = run_json(
            SESSIONS,
            "checkpoint",
            "--id",
            self.session_id,
            "--status",
            "complete",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "invalid_transition")

    def test_no_progress_and_repeated_failure_counters_trigger_escalation(self):
        run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "Stop unproductive loops",
        )
        _, first = run_json(SESSIONS, "checkpoint", "--id", self.session_id)
        self.assertEqual(first["runtime"]["no_progress_windows"], 1)
        self.assertEqual(first["runtime"]["next_decision"], "reflect")
        _, second = run_json(SESSIONS, "checkpoint", "--id", self.session_id)
        self.assertEqual(second["runtime"]["no_progress_windows"], 2)
        self.assertEqual(second["runtime"]["next_decision"], "escalate")

        _, progressed = run_json(
            SESSIONS,
            "checkpoint",
            "--id",
            self.session_id,
            "--done",
            "new evidence collected",
            "--failure-fingerprint",
            "same-test-failure",
        )
        self.assertEqual(progressed["runtime"]["no_progress_windows"], 0)
        _, repeated = run_json(
            SESSIONS,
            "checkpoint",
            "--id",
            self.session_id,
            "--failure-fingerprint",
            "same-test-failure",
        )
        self.assertEqual(repeated["runtime"]["repeated_failure_count"], 2)
        self.assertEqual(repeated["runtime"]["next_decision"], "escalate")

    def test_completion_requires_recorded_verification_and_no_pending_checks(self):
        run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "Require evidence before completion",
        )
        run_json(
            SESSIONS,
            "checkpoint",
            "--id",
            self.session_id,
            "--status",
            "reviewing",
        )
        result, payload = run_json(
            SESSIONS,
            "checkpoint",
            "--id",
            self.session_id,
            "--status",
            "complete",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "verification_required")

        _, completed = run_json(
            SESSIONS,
            "checkpoint",
            "--id",
            self.session_id,
            "--status",
            "complete",
            "--verified",
            "focused tests passed",
        )
        self.assertEqual(completed["task"]["status"], "complete")
        self.assertEqual(completed["runtime"]["next_decision"], "stop")

    def test_completion_rejects_remaining_work_and_clear_removes_resolved_state(self):
        run_json(
            SESSIONS,
            "start",
            "--id",
            self.session_id,
            "--goal",
            "Complete only finished work",
            "--todo",
            "run final check",
        )
        run_json(
            SESSIONS,
            "checkpoint",
            "--status",
            "reviewing",
            "--verified",
            "focused tests passed",
            "--pending-verification",
            "full check",
        )
        result, payload = run_json(
            SESSIONS,
            "checkpoint",
            "--status",
            "complete",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "verification_required")

        result, payload = run_json(
            SESSIONS,
            "checkpoint",
            "--status",
            "complete",
            "--clear",
            "pending-verification",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["error"], "unfinished_work")

        _, completed = run_json(
            SESSIONS,
            "checkpoint",
            "--status",
            "complete",
            "--clear",
            "todo",
            "--clear",
            "pending-verification",
            "--clear",
            "next-action",
        )
        self.assertEqual(completed["task"]["status"], "complete")
        self.assertEqual(completed["progress"]["todo"], [])
        self.assertEqual(completed["verification"]["pending"], [])
        self.assertEqual(completed["runtime"]["no_progress_windows"], 0)
        self.assertEqual(completed["runtime"]["next_decision"], "stop")


if __name__ == "__main__":
    unittest.main()
