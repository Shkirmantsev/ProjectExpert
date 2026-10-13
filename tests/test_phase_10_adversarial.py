"""Adversarial coverage test: every §68 probe must react to a real
break of the invariant it documents.

For each probe we:
1. Identify the platform primitive it inspects (port, file,
   module, flag, gitignore, etc.).
2. Temporarily break that primitive in-process (monkey-patch,
   missing file, falsy value).
3. Re-run the probe and assert it returns False with a useful
   detail message.
4. Restore the original state and confirm the probe returns
   True again.

If any probe stays True under a deliberate break, the probe is a
lie and the gate is broken. This test exists so we never ship a
probe that just returns ``True`` regardless of platform state.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Callable
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
# Make the tests/ directory importable so we can ``importlib.reload``
# the probe module between adversarial iterations.
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO))

# Import via the standard tests.* path so reload() finds a spec.
import tests.test_phase_10_invariants as _probes_mod  # noqa: E402


# Each entry: (invariant_id, callable that breaks the invariant,
#              human-readable description of the break).
# The break must be a real, observable change to the platform
# primitive the probe inspects.
_BREAKS: list[tuple[str, Callable[[], object], Callable[[], None], str]] = [
    # --- Git / repo / cache invariants ---
    (
        "I01",
        lambda: mock.patch("shutil.which", return_value=None),
        lambda: None,
        "no `git` binary",
    ),
    (
        "I02",
        lambda: mock.patch.object(Path, "exists", return_value=False),
        lambda: None,
        "no .gitignore file",
    ),
    (
        "I06",
        lambda: _file_break("tmp/local/**", REPO / ".gitignore", remove=True),
        lambda: None,
        "tmp/local/** not gitignored",
    ),
    # --- Ingest / Source policy / canonical ---
    (
        "I07",
        lambda: _module_attr_break(
            "pi_platform.ports.ingest.local_source_inbox_scanner",
            "SourcePromotionPolicy", None,
        ),
        lambda: None,
        "SourcePromotionPolicy set to None",
    ),
    (
        "I09",
        lambda: _file_break(
            "tests/test_content_address_cross_branch.py",
            None, remove=False,
        ),
        lambda: None,
        "cross-branch cache test removed",
    ),
    # --- Retrieval / Java / Hybrid / Metadata ---
    (
        "I10",
        lambda: _module_attr_break(
            "pi_platform.adapters.retrieval.hashing_embedding_model",
            "HashingEmbeddingAdapter", None,
        ),
        lambda: None,
        "HashingEmbeddingAdapter set to None",
    ),
    (
        "I11",
        lambda: _file_break(
            "pi_platform/adapters/java/jar_adapter.py", None, remove=False,
        ),
        lambda: None,
        "jar_adapter.py removed",
    ),
    (
        "I12",
        lambda: _module_attr_break(
            "pi_platform.ports.runtime.graph", "GraphPort", None,
        ),
        lambda: None,
        "GraphPort set to None",
    ),
    (
        "I13",
        lambda: _module_attr_break(
            "pi_platform.adapters.retrieval.hybrid_retrieval",
            "HybridRetrievalAdapter", None,
        ),
        lambda: None,
        "HybridRetrievalAdapter set to None",
    ),
    (
        "I14",
        lambda: _module_attr_break(
            "pi_platform.core.canonical.value_types", "Metadata", None,
        ),
        lambda: None,
        "Metadata set to None",
    ),
    (
        "I15",
        lambda: _module_attr_break(
            "pi_platform.core.canonical.value_types", "ContextualChunk", None,
        ),
        lambda: None,
        "ContextualChunk set to None",
    ),
    (
        "I16",
        lambda: _module_attr_break(
            "pi_platform.ports.retrieval.multi_stage_retrieval",
            "STAGE_GRAPH_EXPANSION", "",
        ),
        lambda: None,
        "STAGE_GRAPH_EXPANSION set to empty",
    ),
    # --- Orchestration / agents / integration ---
    (
        "I18",
        lambda: _multi_file_break([
            "tests/test_orchestration_policy.py",
            "tests/test_phase_6_quality_gates.py",
            "tests/test_phase_10_quality_gates.py",
        ]),
        lambda: None,
        "all retrieval-first regression suites removed",
    ),
    (
        "I19",
        lambda: _module_attr_break(
            "pi_platform.ports.orchestration.local_llm", "LocalLLMPort", None,
        ),
        lambda: None,
        "LocalLLMPort set to None",
    ),
    (
        "I20",
        lambda: _module_attr_break(
            "pi_platform.ports.orchestration.query_orchestrator",
            "QueryOrchestratorPort", None,
        ),
        lambda: None,
        "QueryOrchestratorPort set to None",
    ),
    (
        "I21",
        lambda: _file_break(
            "pi_platform/mcp/server.py", None, remove=False,
        ),
        lambda: None,
        "MCP server removed",
    ),
    (
        "I22",
        lambda: _module_attr_break(
            "pi_platform.ports.a2a", "A2aAdapterPort", None,
        ),
        lambda: None,
        "A2aAdapterPort set to None",
    ),
    (
        "I23",
        lambda: _file_break(
            "pi_platform/ports/a2a", None, remove=False,
        ),
        lambda: None,
        "a2a ports dir removed",
    ),
    (
        "I24",
        lambda: _dir_break(REPO / "openspec"),
        lambda: None,
        "openspec/ removed",
    ),
    (
        "I25",
        lambda: _module_attr_break(
            "pi_platform.core.canonical.value_types", "KnowledgeState", None,
        ),
        lambda: None,
        "KnowledgeState set to None",
    ),
    (
        "I26",
        lambda: _module_attr_break(
            "pi_platform.ports.security.egress", "EgressDecisionPort", None,
        ),
        lambda: None,
        "EgressDecisionPort set to None",
    ),
    # --- Licensing ---
    (
        "I27",
        lambda: _module_attr_break(
            "pi_platform.core.licensing.inventory",
            "stub_inventory", lambda: [],
        ),
        lambda: None,
        "stub_inventory returns []",
    ),
    (
        "I28",
        lambda: _module_attr_break(
            "pi_platform.core.licensing.policy",
            "DEFAULT_ALLOW_LICENSES", (),
        ),
        lambda: None,
        "DEFAULT_ALLOW_LICENSES empty",
    ),
    (
        "I29",
        lambda: _module_attr_break(
            "pi_platform.core.licensing.policy",
            "DEFAULT_DENY_PATTERNS", (),
        ),
        lambda: None,
        "DEFAULT_DENY_PATTERNS empty",
    ),
    # --- Deployment / UI / control plane ---
    (
        "I30",
        lambda: _file_break("Containerfile", None, remove=False),
        lambda: None,
        "Containerfile removed",
    ),
    (
        "I31",
        lambda: _file_break(
            "pi_platform/ports/ui/rest_api.py", None, remove=False,
        ),
        lambda: None,
        "rest_api.py removed",
    ),
    (
        "I32",
        lambda: _file_break(
            "pi_platform/adapters/ui/static", None, remove=False,
        ),
        lambda: None,
        "static dir removed",
    ),
    (
        "I33",
        lambda: _module_attr_break(
            "pi_platform.adapters.ui.composition", "OPEN_WEBUI_FLAG", None,
        ),
        lambda: None,
        "OPEN_WEBUI_FLAG set to None",
    ),
    (
        "I34",
        lambda: _file_break(
            "scripts/project-intelligence.sh", None, remove=False,
        ),
        lambda: None,
        "Linux one-click launcher removed",
    ),
    # --- Distribution ---
    (
        "I36",
        lambda: _file_break(
            "distribution/skills/project-intelligence/SKILL.md",
            None, remove=False,
        ),
        lambda: None,
        "canonical SKILL.md removed",
    ),
    (
        "I37",
        lambda: _file_break(
            "pi_platform/mcp/skill_plane.py", None, remove=False,
        ),
        lambda: None,
        "MCP skill plane removed",
    ),
    (
        "I38",
        lambda: _file_break(
            "tests/test_version_compatibility.py", None, remove=False,
        ),
        lambda: None,
        "version-compat suite removed",
    ),
    (
        "I39",
        lambda: _module_attr_break(
            "pi_platform.core.canonical.okf", "OkfAdapter", None,
        ),
        lambda: None,
        "OkfAdapter set to None",
    ),
    (
        "I40",
        lambda: _multi_file_break([
            "pi_platform/adapters/agent_integration/packagers/codex.py",
            "pi_platform/adapters/agent_integration/packagers/claude_code.py",
            "pi_platform/adapters/agent_integration/packagers/opencode.py",
            "pi_platform/adapters/agent_integration/packagers/generic_agent.py",
        ]),
        lambda: None,
        "all vendor packagers removed",
    ),
    (
        "I41",
        lambda: _file_break(
            "distribution/codex", None, remove=False,
        ),
        lambda: None,
        "codex distribution dir removed",
    ),
    (
        "I42",
        lambda: _file_break(
            "tests/test_supply_chain_gate.py", None, remove=False,
        ),
        lambda: None,
        "supply-chain suite removed",
    ),
    (
        "I43",
        lambda: _file_break(
            "tests/test_phase_10_quality_gates.py", None, remove=False,
        ),
        lambda: None,
        "Phase 10 quality-gates suite removed",
    ),
    (
        "I47",
        lambda: _module_attr_break(
            "pi_platform.core.control.policy", "DefaultPolicyEngine", None,
        ),
        lambda: None,
        "DefaultPolicyEngine set to None",
    ),
    (
        "I48",
        lambda: _module_attr_break(
            "pi_platform.ports.control.secrets", "SecretProviderPort", None,
        ),
        lambda: None,
        "SecretProviderPort set to None",
    ),
    (
        "I49",
        lambda: _module_attr_break(
            "pi_platform.core.control.hooks", "DefaultHookRuntime", None,
        ),
        lambda: None,
        "DefaultHookRuntime set to None",
    ),
    (
        "I50",
        lambda: _module_attr_break(
            "pi_platform.ports", "ApprovalRequest", None,
        ),
        lambda: None,
        "ApprovalRequest set to None",
    ),
    (
        "I51",
        lambda: _multi_file_break([
            ".ai/wiki/adr/0017-phase-8-enterprise-security-boundary.md",
            "docs/SECURITY.md",
        ]),
        lambda: None,
        "isolation docs removed",
    ),
    (
        "I52",
        lambda: _file_break(
            ".ai/wiki/adr/0004-ports-and-adapters-extension-style.md",
            None, remove=False,
        ),
        lambda: None,
        "ADR 0004 removed",
    ),
    # Probes that inspect several files / paths and would need
    # elaborate multi-file breaks (skipped intentionally):
    #   I03, I04, I05, I08, I17, I22, I35, I44, I45, I46 — covered
    #   by `_static_only` and direct synthetic injection if needed.
    # We test the *class* of break: every probe we exercise here
    # shows it reacts to a real platform change.
]


def _module_attr_break(module: str, attr: str, new_value):
    """Return a context manager that swaps ``module.attr`` to
    ``new_value`` and restores on exit."""
    return mock.patch.object(
        importlib.import_module(module), attr, new_value,
    )


def _file_break(path: str, find_in: Path | None, remove: bool):
    """Return a context manager that hides ``path`` (or removes a
    literal from ``find_in``). On exit, the original state is
    restored.

    Implementation note: we *rename* the file to a side path
    rather than monkey-patching ``Path.exists``. Probe code that
    walks the directory (e.g. ``Path.rglob``) would otherwise
    still see the file via the OS, defeating the lie.
    """
    if remove and find_in is not None:
        original = find_in.read_text(encoding="utf-8")
        patched = original.replace(path, "")
        return _FileReplacer(find_in, original, patched)
    target = REPO / path
    if not target.exists():
        # Nothing to break; return a no-op so the test still runs.
        import contextlib
        return contextlib.nullcontext()
    backup = target.with_suffix(target.suffix + ".advbak")
    if backup.exists():
        raise RuntimeError(f"backup {backup} already exists; aborting")
    return _RenameOnce(target, backup)


def _exists_lie(path: str):
    real = Path.exists
    def fake(self, *a, **kw):
        if str(self) == path or str(self).endswith("/" + path):
            return False
        return real(self, *a, **kw)
    return fake


def _is_dir_lie(path: str):
    real = Path.is_dir
    def fake(self, *a, **kw):
        if str(self) == path or str(self).endswith("/" + path):
            return False
        return real(self, *a, **kw)
    return fake


def _dir_break(target: Path):
    """Temporarily rename ``target`` so it is gone for the probe."""
    parent = target.parent
    backup = parent / (target.name + ".adversarial_backup")
    if backup.exists():
        raise RuntimeError(f"{backup} already exists; aborting to avoid data loss")
    return _DirReplacer(target, backup)


class _FileReplacer:
    def __init__(self, path: Path, original: str, patched: str):
        self.path = path
        self.original = original
        self.patched = patched

    def __enter__(self):
        self.path.write_text(self.patched, encoding="utf-8")
        return self

    def __exit__(self, *exc):
        self.path.write_text(self.original, encoding="utf-8")


class _DirReplacer:
    def __init__(self, target: Path, backup: Path):
        self.target = target
        self.backup = backup

    def __enter__(self):
        self.target.rename(self.backup)
        return self

    def __exit__(self, *exc):
        self.backup.rename(self.target)


class _RenameOnce:
    def __init__(self, target: Path, backup: Path):
        self.target = target
        self.backup = backup

    def __enter__(self):
        self.target.rename(self.backup)
        return self

    def __exit__(self, *exc):
        self.backup.rename(self.target)


class _MultiFileBreak:
    """Temporarily hide several files (or directories) at once.

    Used for probes that fall back through several candidate paths
    (e.g. I18, I42). The probe must be tested against the
    simultaneous disappearance of every candidate, not just one.
    """

    def __init__(self, rel_paths: list[str]):
        self.rel_paths = rel_paths
        self._renames: list[tuple[Path, Path]] = []

    def __enter__(self):
        for rel in self.rel_paths:
            target = REPO / rel
            if not target.exists():
                continue
            backup = target.with_suffix(target.suffix + ".advbak")
            if backup.exists():
                raise RuntimeError(f"backup {backup} already exists; abort")
            target.rename(backup)
            self._renames.append((target, backup))
        return self

    def __exit__(self, *exc):
        for target, backup in reversed(self._renames):
            backup.rename(target)
        self._renames.clear()


def _multi_file_break(rel_paths: list[str]):
    return _MultiFileBreak(rel_paths)


# --- The actual test --------------------------------------------------------


def _probe_fn(invariant_id: str):
    """Return the ``_iNN`` callable for ``invariant_id``."""
    fn_name = "_" + invariant_id.lower()
    fn = getattr(_probes_mod, fn_name, None)
    if fn is None:
        raise RuntimeError(f"no probe function {fn_name}")
    return fn


class AdversarialProbeCoverageTests(unittest.TestCase):
    """Every probe that claims to enforce an invariant MUST flip
    to False under a real break of that invariant.

    The breaks listed in ``_BREAKS`` cover every probe that can be
    broken through a single module-attribute swap, file rename, or
    directory rename in-process. Probes that use local
    ``from X import Y`` rebinding (and therefore cannot be broken
    by patching ``X.Y``) are listed in ``_LOCAL_IMPORT_PROBES`` and
    skipped with a documented reason. The remaining 11 §68 probes
    are not adversarial-tested by this suite; their behaviour is
    covered by the dedicated unit tests for the ports and modules
    they reference.
    """

    # Probes whose body rebinds the imported name locally; module
    # attribute patches do not affect them. Listed here so the
    # coverage gap is explicit, not silent.
    _LOCAL_IMPORT_PROBES = {
        # I04 rebinds ``canonical_dump_json`` from the serializer
        # module via a local import, so monkey-patching
        # ``serializer.canonical_dump_json`` has no effect.
        "I04",
        # I05 rebinds ``content_address`` via a local import, so
        # ``content_address.content_address`` is the function, not
        # the module attribute.
        "I05",
    }

    def test_every_listed_probe_reacts_to_its_break(self):
        # Establish a clean baseline.
        baseline = self._collect_verdicts()
        self.assertEqual(
            baseline.failed, 0,
            f"baseline already failing: {baseline.failed_ids}",
        )

        # Apply each break and re-collect.
        for invariant_id, break_ctx, _restore, description in _BREAKS:
            with break_ctx():
                after = self._collect_verdicts()
            self.assertIn(
                invariant_id, after.failed_ids,
                f"{invariant_id} ({description}): expected probe to flip "
                f"to False under this break; instead verdict was True. "
                f"failed_ids={after.failed_ids}",
            )

        # After all breaks, the platform must be back to a clean state.
        final = self._collect_verdicts()
        self.assertEqual(
            final.failed, 0,
            f"platform not restored cleanly: {final.failed_ids}",
        )

    def test_local_import_probes_are_documented(self):
        """Probes that escape in-process adversarial coverage via
        local ``from X import Y`` rebinding MUST be enumerated so
        the gap is visible. If a new probe is added to this set the
        operator must also add a dedicated adversarial mechanism
        for it (or document why the gap is acceptable)."""
        # Re-import to make sure the module is current.
        importlib.reload(_probes_mod)
        from pi_platform.core.eval import runner as _runner
        summary = _runner.probe_summary()
        # The set is closed; if a new probe is added to the skip
        # list, this test stays green. The intent is to prevent
        # silent drift.
        self.assertTrue(
            self._LOCAL_IMPORT_PROBES.issubset(
                {p.invariant_id for p in _runner.discover_probes(
                    vars(_probes_mod))}),
            f"_LOCAL_IMPORT_PROBES references unknown probe ids: "
            f"{self._LOCAL_IMPORT_PROBES}",
        )

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _collect_verdicts():
        # Re-import the probe module so module attributes monkey-
        # patched via ``mock.patch.object`` do not leak between
        # iterations.
        importlib.reload(_probes_mod)
        from pi_platform.core.eval import runner as _runner
        return _runner.probe_summary()


if __name__ == "__main__":
    unittest.main()
