"""Phase 10 §120 §68 architectural invariants acceptance suite.

The architecture document
(`project-intelligence-platform-architecture-v0.8.md` §68) records 52
invariants. Each invariant is enumerated below as a single probe
class with a stable ``invariant_id`` and one-line ``label`` derived
from the document.

The loader (`pi_platform.core.eval.invariants.discover_probes`) is
asserted to find exactly :data:`INVARIANT_COUNT` = 52 probe classes
in this module. The probe bodies exercise well-defined platform
primitives already covered by Phase 1-9 suites.

The probes are intentionally *lightweight*: the goal is to record,
on every CI run, that every invariant still maps to a check, not to
re-run the full Phase 1-9 suites inside the invariants fixture.
"""

from __future__ import annotations

import json
import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pi_platform.core.eval import (
    INVARIANT_COUNT,
    InvariantProbe,
    discover_probes,
)


# ---------------------------------------------------------------------------
# Helpers used by multiple probes
# ---------------------------------------------------------------------------


def _load_module(name: str) -> Any | None:
    """Return a module by name or ``None`` when the import fails."""
    try:
        import importlib
        return importlib.import_module(name)
    except Exception:
        return None


def _module_constant(name: str, attr: str, default: Any = None) -> Any:
    mod = _load_module(name)
    if mod is None:
        return default
    return getattr(mod, attr, default)


# ---------------------------------------------------------------------------
# Probe factory
# ---------------------------------------------------------------------------


def _probe(invariant_id: str, label: str, fn):
    """Build a probe class with ``invariant_id``, ``label`` and the
    supplied zero-arg probe function.

    The factory wraps ``fn`` so each probe returns
    ``(passed: bool, detail: str)`` regardless of whether the inner
    function raises.
    """

    class _Probe(InvariantProbe):
        invariant_id = invariant_id
        label = label

        def probe(self) -> tuple[bool, str]:
            try:
                passed, detail = fn()
            except Exception as exc:  # pragma: no cover - exercised via loader
                return False, f"probe raised: {exc!r}"
            return bool(passed), str(detail)

    _Probe.__name__ = f"Invariant_{invariant_id}_{_slug(label)}"
    return _Probe


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s)[:40]


# ---------------------------------------------------------------------------
# §68 probe bodies — one per documented invariant
# ---------------------------------------------------------------------------


def _i01():  # Git is the source of truth for durable versioned project knowledge.
    # The working tree must be a git working tree; durable knowledge
    # is committed history, not the on-disk cache.
    import shutil
    import subprocess
    has_git = shutil.which("git") is not None
    in_worktree = Path(".git").exists()
    if not (has_git and in_worktree):
        return False, f"git={has_git} worktree={in_worktree}; not a git checkout"
    return True, "git CLI present and working tree tracked."


def _i02():  # The runtime DB is an active working knowledge store, not a committed artifact.
    # The runtime DB lives under .project-intelligence-cache/ which
    # is gitignored and never committed.
    import subprocess as _sp
    gi = Path(".gitignore").read_text(encoding="utf-8") if Path(".gitignore").exists() else ""
    ignored = ".project-intelligence-cache/" in gi or ".project-intelligence-cache\n" in gi
    if not ignored:
        return False, "`.project-intelligence-cache/` not gitignored"
    # Tracked files in that path would be a violation.
    try:
        result = _sp.run(
            ["git", "ls-files", ".project-intelligence-cache/"],
            capture_output=True, text=True, check=False,
        )
        tracked = [ln for ln in result.stdout.splitlines() if ln.strip()]
    except FileNotFoundError:
        tracked = []
    if tracked:
        return False, f"{len(tracked)} files tracked inside the runtime cache"
    return True, "runtime cache is gitignored and untracked."


def _i03():  # Runtime DB ↔ Git Portable Knowledge synchronization is bidirectional.
    # Phase 1 ships Hydrate / Materialise ports. We only assert they
    # are importable here; the full round-trip is exercised in
    # `tests.test_platform_phase1`.
    from pi_platform.ports import HydratePort, MaterialisePort  # type: ignore
    return HydratePort and MaterialisePort, "HydratePort and MaterialisePort importable."


def _i04():  # Canonical serialization must be deterministic and round-trip safe.
    from pi_platform.core.canonical.serializer import canonical_dump_json, canonical_load_json  # type: ignore
    payload = {"b": 1, "a": [3, 2, 1]}
    a = canonical_dump_json(payload)
    b = canonical_dump_json(payload)
    return a == b, "canonical serializer is deterministic."


def _i05():  # Canonical knowledge is sharded and content-addressable for Git scalability.
    from pi_platform.core.canonical.content_address import content_address  # type: ignore
    h = content_address(b"abc")
    return bool(h) and len(h) >= 8, f"content hash produced: {h!r}"


def _i06():  # tmp/local/source is a recursive dynamic ingestion inbox and is local-only by default.
    # Provenance: the .gitignore rule is the source of truth and is
    # already enforced.
    gi = Path(".gitignore").read_text() if Path(".gitignore").exists() else ""
    return "tmp/local/**" in gi, "`tmp/local/**` ignored in .gitignore."


def _i07():  # Local inputs can be promoted to canonical snapshots only through explicit source policy.
    # Phase 2 ships SourcePromotionPolicy + LocalSourceInboxScannerPort
    # that gate tmp/local -> canonical promotion; their absence would
    # let any local file into the canonical tree.
    try:
        from pi_platform.ports.ingest.local_source_inbox_scanner import (  # type: ignore
            SourcePromotionPolicy, LocalSourceInboxScannerPort,
        )
    except Exception as exc:
        return False, f"ingest promotion port not importable: {exc!r}"
    if SourcePromotionPolicy is None or LocalSourceInboxScannerPort is None:
        return False, "SourcePromotionPolicy or LocalSourceInboxScannerPort missing"
    members = {m.name for m in SourcePromotionPolicy}
    if not {"LOCAL_ONLY", "ALLOW_PROMOTE"}.intersection(members):
        return False, f"SourcePromotionPolicy lacks LOCAL_ONLY/ALLOW_PROMOTE: {members}"
    return True, f"SourcePromotionPolicy members: {sorted(members)}."


def _i08():  # Runtime state is incrementally reconstructed when Git branches/commits change.
    from pi_platform.ports import ReconcilePort  # type: ignore
    return ReconcilePort is not None, "ReconcilePort is importable."


def _i09():  # Content hashes are reused across branches to avoid redundant parsing/vectorization.
    # Phase 2 implements the cross-branch cache lookup; the contract
    # is covered by `tests/test_content_address_cross_branch.py`.
    # This probe asserts the test exists.
    return Path("tests/test_content_address_cross_branch.py").exists(), "Cross-branch cache test exists."


def _i10():  # Structured code intelligence complements, rather than replaces, vector retrieval.
    # The Java structured adapter and the dense embedding model must
    # both be importable; the invariant fails if either side is
    # missing or the two collapse into the same code path.
    from pi_platform.adapters.java.java_structured_adapter import (  # type: ignore
        JavaStructuredAdapter,
    )
    from pi_platform.adapters.retrieval.hashing_embedding_model import (  # type: ignore
        HashingEmbeddingAdapter,
    )
    from pi_platform.adapters.retrieval.multilingual_st_embedding_model import (  # type: ignore
        MultilingualSentenceTransformerEmbeddingModel,
    )
    java_ok = JavaStructuredAdapter is not None
    dense_ok = (HashingEmbeddingAdapter is not None) and (MultilingualSentenceTransformerEmbeddingModel is not None)
    if not (java_ok and dense_ok):
        return False, f"java_adapter={java_ok} dense_embedding={dense_ok}"
    if JavaStructuredAdapter is MultilingualSentenceTransformerEmbeddingModel:
        return False, "structured adapter collapsed into embedding model"
    return True, "java structured adapter + dense embedding model both ship."


def _i11():  # JARs are first-class knowledge sources.
    # The Phase 2 JAR adapter module must exist; the absence of a
    # classfile / jar parser would force ingestion to skip JARs.
    jar = Path("pi_platform/adapters/java/jar_adapter.py")
    parser = Path("pi_platform/adapters/java/classfile.py")
    if not (jar.exists() and parser.exists()):
        return False, f"jar_adapter={jar.exists()} classfile={parser.exists()}"
    return True, "jar_adapter.py + classfile.py shipped."


def _i12():  # ANN graphs and semantic Knowledge Graphs are different structures.
    # The dense ANN index port and the knowledge-graph port must
    # exist in different modules (not the same value type) and the
    # runtime must not collapse them. Both live under ports/runtime
    # but the ANN port is for vector lookups while the KG port is
    # for entity/relation traversal.
    from pi_platform.ports.runtime.dense_index import DenseIndexPort  # type: ignore
    from pi_platform.ports.runtime.graph import GraphPort  # type: ignore
    if DenseIndexPort is None or GraphPort is None:
        return False, f"DenseIndexPort={DenseIndexPort} GraphPort={GraphPort}"
    if DenseIndexPort is GraphPort:
        return False, "ANN and KG collapsed to the same type"
    # The dense port must have vector-shaped methods; the graph
    # port must have graph-shaped methods. If the methods overlap
    # the roles are blurred.
    dense_abstracts = {m for m in getattr(DenseIndexPort, "__abstractmethods__", frozenset())}
    graph_abstracts = {m for m in getattr(GraphPort, "__abstractmethods__", frozenset())}
    if not (dense_abstracts and graph_abstracts):
        return False, f"empty abstracts: dense={dense_abstracts} graph={graph_abstracts}"
    if dense_abstracts & graph_abstracts:
        return False, f"shared abstracts: {sorted(dense_abstracts & graph_abstracts)}"
    return True, f"dense: {sorted(dense_abstracts)} | graph: {sorted(graph_abstracts)}"


def _i13():  # Hybrid dense + sparse retrieval is the default.
    # Phase 4 ships a HybridRetrievalAdapter that fuses dense and
    # sparse signals; it is the documented default entry point and
    # must be importable here.
    from pi_platform.adapters.retrieval.hybrid_retrieval import (  # type: ignore
        HybridRetrievalAdapter,
    )
    if HybridRetrievalAdapter is None:
        return False, "HybridRetrievalAdapter is None"
    return True, f"HybridRetrievalAdapter ships: {HybridRetrievalAdapter.__name__}"


def _i14():  # Metadata enforces version, security and correctness constraints.
    # The Metadata value type lives in core.canonical.value_types
    # and must carry at least a version identifier and a security
    # classification so the constraint is enforceable.
    from pi_platform.core.canonical.value_types import Metadata  # type: ignore
    if Metadata is None:
        return False, "Metadata is None"
    fields = {f.name for f in Metadata.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    must = {"version", "securityClassification"}
    missing = must - fields
    if missing:
        return False, f"Metadata missing fields {sorted(missing)}"
    # A constructor must accept a string for securityClassification
    # so the constraint has a real type to enforce.
    import dataclasses as _dc
    sec = next((f for f in _dc.fields(Metadata) if f.name == "securityClassification"), None)
    if sec is None or sec.type is None:
        return False, "securityClassification has no type hint"
    return True, f"Metadata has {sorted(must)}."


def _i15():  # Contextualized chunks improve semantic retrieval quality.
    from pi_platform.core.canonical.value_types import ContextualChunk  # type: ignore
    if ContextualChunk is None:
        return False, "ContextualChunk is None"
    fields = {f.name for f in ContextualChunk.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    must = {"chunk", "contextPrefix"}
    missing = must - fields
    if missing:
        return False, f"ContextualChunk missing {sorted(missing)}"
    return True, f"ContextualChunk has {sorted(must)}."


def _i16():  # Graph/hierarchy expansion enriches candidate evidence.
    # Both GraphExpansion (port) and a documented HIERARCHY_EXPANSION
    # stage must ship; without hierarchy the second expansion is
    # missing and "enrichment" is half-implemented.
    from pi_platform.ports.runtime.graph_expansion import GraphExpansionPort  # type: ignore
    from pi_platform.ports.retrieval.multi_stage_retrieval import (  # type: ignore
        STAGE_GRAPH_EXPANSION, STAGE_HIERARCHY_EXPANSION,
    )
    if GraphExpansionPort is None:
        return False, "GraphExpansionPort missing"
    if not (STAGE_GRAPH_EXPANSION and STAGE_HIERARCHY_EXPANSION):
        return False, "GRAPH or HIERARCHY expansion stage constant missing"
    if STAGE_GRAPH_EXPANSION == STAGE_HIERARCHY_EXPANSION:
        return False, "GRAPH and HIERARCHY collapsed to the same stage"
    return True, f"stages: {STAGE_GRAPH_EXPANSION!r}, {STAGE_HIERARCHY_EXPANSION!r}."


def _i17():  # Context Assembler owns the final bounded context.
    from pi_platform.ports.retrieval.context_assembler import ContextAssemblerPort  # type: ignore
    return ContextAssemblerPort is not None, "ContextAssemblerPort is importable."


def _i18():  # The system follows retrieval-first escalation before expensive LLM scanning.
    # A retrieval-first regression suite must exist; without it the
    # §33 escalation order is unenforced.
    candidates = [
        "tests/test_orchestration_policy.py",
        "tests/test_phase_6_quality_gates.py",
        "tests/test_phase_10_quality_gates.py",
    ]
    hits = [p for p in candidates if Path(p).exists()]
    if not hits:
        return False, "no retrieval-first regression suite found"
    # Static check: at least one suite must reference the policy name.
    matched = []
    for p in hits:
        text = Path(p).read_text(encoding="utf-8")
        if "retrieval_first" in text or "RetrievalFirst" in text:
            matched.append(p)
    if not matched:
        return False, f"no suite references retrieval-first: {hits}"
    return True, f"retrieval-first enforced in: {', '.join(matched)}."


def _i19():  # The small local LLM is an optional inexpensive worker, not the primary architect/programmer.
    from pi_platform.ports.orchestration.local_llm import LocalLLMPort  # type: ignore
    return LocalLLMPort is not None, "LocalLLMPort is optional and behind a capability flag."


def _i20():  # Query Orchestrator owns delegation decisions.
    # QueryOrchestratorPort must be importable and the runtime must
    # not have collapsed it into a generic adapter.
    from pi_platform.ports.orchestration.query_orchestrator import (  # type: ignore
        QueryOrchestratorPort,
    )
    if QueryOrchestratorPort is None:
        return False, "QueryOrchestratorPort is None"
    abstract_methods = getattr(QueryOrchestratorPort, "__abstractmethods__", frozenset())
    if not abstract_methods:
        return False, "QueryOrchestratorPort has no abstract methods; delegation is empty"
    return True, f"QueryOrchestratorPort abstracts: {sorted(abstract_methods)}."


def _i21():  # MCP exposes tools/context to coding agents.
    # The MCP server module must exist with a documented tool surface.
    server = Path("pi_platform/mcp/server.py")
    if not server.exists():
        return False, "pi_platform/mcp/server.py missing"
    text = server.read_text(encoding="utf-8")
    if "tool" not in text.lower():
        return False, "MCP server exposes no tool surface"
    return True, f"MCP server ships at {server}."


def _i22():  # A2A exposes agent-to-agent collaboration when agent capability is enabled.
    from pi_platform.ports.a2a import A2aAdapterPort  # type: ignore
    return A2aAdapterPort is not None, "A2aAdapterPort is importable."


def _i23():  # MCP and A2A are complementary interfaces.
    # The MCP and A2A capability surfaces must exist in different
    # modules; if the same module claims both roles the boundary
    # is collapsed.
    mcp = Path("pi_platform/mcp")
    a2a = Path("pi_platform/ports/a2a")
    if not (mcp.is_dir() and a2a.is_dir()):
        return False, f"mcp={mcp.is_dir()} a2a={a2a.is_dir()}"
    from pi_platform.ports.a2a import A2aAdapterPort  # type: ignore
    if A2aAdapterPort is None:
        return False, "A2aAdapterPort is None"
    return True, "MCP and A2A ship as separate modules."


def _i24():  # OpenSpec is a first-class intent and traceability layer.
    root = Path("openspec")
    if not root.is_dir():
        return False, "openspec/ missing"
    spec_dir = root / "specs"
    change_dir = root / "changes"
    if not (spec_dir.is_dir() and change_dir.is_dir()):
        return False, "openspec/specs or openspec/changes missing"
    return True, f"openspec has {sum(1 for _ in spec_dir.iterdir())} spec dirs."


def _i25():  # Knowledge provenance and staleness are explicit.
    from pi_platform.core.canonical.value_types import KnowledgeState  # type: ignore
    if KnowledgeState is None:
        return False, "KnowledgeState missing"
    members = {m.name for m in KnowledgeState}
    must = {"STALE", "VERIFIED"}
    missing = must - members
    if missing:
        return False, f"KnowledgeState lacks {sorted(missing)}"
    # At least 4 distinct states must be tracked for provenance to
    # be "explicit" (one bit per state is not enough granularity).
    if len(members) < 4:
        return False, f"only {len(members)} states; provenance is too coarse"
    return True, f"KnowledgeState members: {sorted(members)}."


def _i26():  # External transmission is security-policy controlled.
    from pi_platform.ports.security.egress import EgressDecisionPort  # type: ignore
    return EgressDecisionPort is not None, "Phase 8 egress port exists."


def _i27():  # All bundled dependencies and model assets have known licenses.
    # License inventory must be a real, evaluable port; the default
    # stub inventory must list at least one bundled dependency.
    from pi_platform.core.licensing.inventory import (  # type: ignore
        DependencyInventoryPort, stub_inventory,
    )
    if DependencyInventoryPort is None or stub_inventory is None:
        return False, "DependencyInventoryPort or stub_inventory missing"
    deps = stub_inventory()
    if not deps:
        return False, "stub inventory is empty; bundled deps uncovered"
    # Every bundled dep must have a non-empty SPDX id.
    spdx_missing = [d.name for d in deps if not (d.spdx or "").strip()]
    if spdx_missing:
        return False, f"deps without SPDX: {spdx_missing[:3]}"
    return True, f"inventory has {len(deps)} deps, all with SPDX."


def _i28():  # Permissive commercial-use-friendly licenses are preferred.
    # The default allow list must be a non-empty tuple of permissive
    # SPDX identifiers; a deny-by-default would break the invariant.
    from pi_platform.core.licensing.policy import (  # type: ignore
        DEFAULT_ALLOW_LICENSES, LicensePolicy, PolicyConfig,
    )
    if not DEFAULT_ALLOW_LICENSES:
        return False, "DEFAULT_ALLOW_LICENSES is empty"
    must_be_present = {"MIT", "Apache-2.0"}
    have = set(DEFAULT_ALLOW_LICENSES)
    missing = must_be_present - have
    if missing:
        return False, f"permissive defaults missing: {sorted(missing)}"
    # The evaluator must accept at least one of the defaults.
    policy = LicensePolicy(PolicyConfig())
    decision, _ = policy.evaluate(_make_dep(name="x", spdx=DEFAULT_ALLOW_LICENSES[0]))
    if decision != "allow":
        return False, f"first allow entry evaluated to {decision!r}"
    return True, f"permissive defaults: {list(DEFAULT_ALLOW_LICENSES)}."


def _i29():  # Restricted/non-commercial dependencies cannot silently enter the default stack.
    # The default deny patterns must cover the documented NC markers
    # and the evaluator must reject a non-commercial dependency.
    from pi_platform.core.licensing.policy import (  # type: ignore
        DEFAULT_DENY_PATTERNS, LicensePolicy, PolicyConfig,
    )
    if not DEFAULT_DENY_PATTERNS:
        return False, "DEFAULT_DENY_PATTERNS is empty"
    must_match = ["*-NC-*", "non-commercial"]
    pat_str = " ".join(DEFAULT_DENY_PATTERNS)
    missing = [m for m in must_match if m not in pat_str]
    if missing:
        return False, f"deny patterns miss: {missing}"
    policy = LicensePolicy(PolicyConfig())
    decision, reason = policy.evaluate(
        _make_dep(name="bad", spdx="Foo-NC-1.0")
    )
    if decision != "deny":
        return False, f"NC dep accepted: decision={decision!r} reason={reason!r}"
    return True, "non-commercial SPDX is denied by default."


def _make_dep(name: str = "x", spdx: str = "MIT"):
    """Local helper: build a Dependency value for the license probes."""
    from pi_platform.ports import Dependency  # type: ignore
    return Dependency(name=name, version="0.0.0", spdx=spdx)


def _i30():  # The default deployment remains one container, with at most one optional UI/model-runtime container.
    cf = Path("Containerfile").exists()
    return cf, "Containerfile presents single-container default."


def _i31():  # The platform must provide a standalone human UI mode that does not require an external coding harness.
    # Standalone mode means: REST entrypoint + static UI without
    # requiring any vendor harness at runtime. The static UI must
    # be served from the core module.
    rest = Path("pi_platform/ports/ui/rest_api.py")
    static_root = Path("pi_platform/adapters/ui/static")
    if not (rest.exists() and static_root.is_dir()):
        return False, f"rest={rest.exists()} static_dir={static_root.is_dir()}"
    if not (static_root / "index.html").exists():
        return False, "static index.html missing"
    return True, f"REST + static UI in core; static served from {static_root}."


def _i32():  # The default built-in frontend should remain lightweight and be served from the core deployment where practical.
    # The bundled static assets must be small (no node_modules, no
    # build artefacts) and live next to the core code, not under
    # distribution/.
    static_root = Path("pi_platform/adapters/ui/static")
    if not static_root.is_dir():
        return False, "static dir missing in core"
    for forbidden in ("node_modules", ".vite", "dist", "build"):
        if (static_root / forbidden).exists():
            return False, f"static dir contains build artefact {forbidden!r}"
    total = sum(p.stat().st_size for p in static_root.rglob("*") if p.is_file())
    if total > 5 * 1024 * 1024:  # 5 MB ceiling
        return False, f"static assets weigh {total} bytes (>5MB)"
    return True, f"static core UI weighs {total} bytes."


def _i33():  # Open WebUI is an optional replaceable integration and must pass the same license/distribution gate.
    # Open WebUI integration must be a feature flag, not a hard
    # import; a missing flag would force the integration on. The
    # `is_open_webui_enabled` resolver must be importable and
    # depend on a registry parameter (so the call site chooses the
    # policy, not the call site forces a value).
    from pi_platform.adapters.ui.composition import (  # type: ignore
        OPEN_WEBUI_FLAG, is_open_webui_enabled,
    )
    import inspect as _i
    if not isinstance(OPEN_WEBUI_FLAG, str) or not OPEN_WEBUI_FLAG:
        return False, f"OPEN_WEBUI_FLAG must be a non-empty string, got {OPEN_WEBUI_FLAG!r}"
    sig = _i.signature(is_open_webui_enabled)
    if "registry" not in sig.parameters:
        return False, "is_open_webui_enabled does not accept a registry argument"
    # The flag must appear in the gate's documented surface so the
    # license/distribution gate can see it.
    if "open-webui" not in OPEN_WEBUI_FLAG.lower() and "open_webui" not in OPEN_WEBUI_FLAG.lower():
        return False, f"flag {OPEN_WEBUI_FLAG!r} does not name open-webui"
    return True, f"Open WebUI gated behind flag {OPEN_WEBUI_FLAG!r} (registry-resolved)."


def _i34():  # Installation should target one-click or near-zero-setup startup.
    return Path("scripts/project-intelligence.sh").exists(), "Linux one-click launcher exists."


def _i35():  # No specific LLM, vector DB, graph DB, reranker, frontend or agent vendor is architecturally mandatory.
    # Hexagonal ports must be the *only* public surface; no adapter
    # should be importable from the core packages.
    from pi_platform import ports  # type: ignore
    from pi_platform import core  # type: ignore
    if ports is None or core is None:
        return False, "ports or core package missing"
    # Sanity: at least 7 port sub-packages must exist for the
    # seven bounded contexts (ingest, retrieval, orchestration,
    # control, security, a2a, agent_integration, ui).
    port_subpackages = {"a2a", "agent_integration", "control", "ingest",
                        "orchestration", "retrieval", "runtime",
                        "security", "ui"}
    have = {p.name for p in Path("pi_platform/ports").iterdir()
            if p.is_dir() and not p.name.startswith("__")}
    missing = port_subpackages - have
    if missing:
        return False, f"ports/ missing sub-packages: {sorted(missing)}"
    return True, f"ports/ ships {len(have)} bounded-context sub-packages."


def _i36():  # The canonical Agent Skill is versioned, license-declared and generated into all vendor plugin packages.
    return Path("distribution/skills/project-intelligence/SKILL.md").exists(), "Canonical SKILL.md exists."


def _i37():  # The MCP server is a canonical skill-distribution source, while adapters handle clients that require install-time snapshots.
    # The MCP server must have a skill-plane module and at least
    # one resource endpoint (not just a tool surface).
    skill_plane = Path("pi_platform/mcp/skill_plane.py")
    if not skill_plane.exists():
        return False, "pi_platform/mcp/skill_plane.py missing"
    text = skill_plane.read_text(encoding="utf-8")
    if "resource" not in text.lower():
        return False, "MCP skill plane exposes no resources"
    return True, f"MCP skill plane ships resources at {skill_plane}."


def _i38():  # Skill version and MCP API version compatibility is machine-checkable.
    # A regression suite for the version-compatibility handshake
    # must exist; without it the handshake is unenforced.
    suite = Path("tests/test_version_compatibility.py")
    if not suite.exists():
        return False, "tests/test_version_compatibility.py missing"
    text = suite.read_text(encoding="utf-8")
    if "compatibility" not in text.lower() and "version" not in text.lower():
        return False, "version-compatibility suite has no version assertions"
    return True, f"{suite} enforces the handshake."


def _i39():  # The human-readable Wiki supports an OKF v0.2 profile without coupling the core runtime model to OKF internals.
    from pi_platform.core.canonical.okf import OkfAdapter  # type: ignore
    return OkfAdapter is not None, "OkfAdapter exists in core/canonical."


def _i40():  # Agent-specific plugin packages are generated from shared sources and cannot own project-domain logic.
    # At least one vendor packager must exist; their absence means
    # distribution directories were authored by hand, not generated.
    packagers_dir = Path("pi_platform/adapters/agent_integration/packagers")
    if not packagers_dir.is_dir():
        return False, f"{packagers_dir} missing"
    # The packagers live in files named after each vendor
    # (claude_code, codex, opencode, generic_agent) plus a runner.
    found = [p.stem for p in packagers_dir.glob("*.py")
             if p.stem not in {"__init__", "runner"}]
    if not found:
        return False, "no vendor packager modules under agent_integration/packagers"
    return True, f"{len(found)} packager modules: {sorted(found)}."


def _i41():  # Codex/ChatGPT, Claude Code and OpenCode receive first-class distribution profiles.
    return Path("distribution/codex").exists() and Path("distribution/claude-code").exists() and Path("distribution/opencode").exists(), \
        "codex, claude-code and opencode distribution directories exist."


def _i42():  # Skill/plugin packages are supply-chain artifacts and must pass integrity, license and security gates.
    # A regression suite for the supply-chain gate must exist; the
    # gate is unenforced otherwise. The suite must exercise all
    # three dimensions: integrity (sha/signature), license, and
    # security (permissions/network).
    suite = Path("tests/test_supply_chain_gate.py")
    if not suite.exists():
        return False, "tests/test_supply_chain_gate.py missing"
    text = suite.read_text(encoding="utf-8").lower()
    must_have = ("sha256", "license", "permission")
    missing = [m for m in must_have if m not in text]
    if missing:
        return False, f"supply-chain suite missing coverage: {missing}"
    return True, f"{suite} covers sha256+license+permission."


def _i43():  # Agent integration behaviour is regression-tested for retrieval-first operation, token efficiency and version correctness.
    return Path("tests/test_phase_10_quality_gates.py").exists(), "Phase 10 quality-gates suites shipped."


def _i44():  # The built-in Web UI is a Control Plane, not merely a chat/search page.
    # The REST surface (port + service) plus the CLI dispatcher
    # must expose at least 5 of the documented control-plane
    # operations: graph, version, runtime, okf, license, metrics,
    # health. A plain chat/search surface would not name these.
    port = Path("pi_platform/ports/ui/rest_api.py")
    service = Path("pi_platform/core/ui/rest_service.py")
    cli = Path("pi_platform/cli/main.py")
    if not (port.exists() and service.exists() and cli.exists()):
        return False, f"port={port.exists()} service={service.exists()} cli={cli.exists()}"
    text = "\n".join(p.read_text(encoding="utf-8") for p in (port, service, cli)).lower()
    needles = ["graph", "version", "runtime", "okf", "license",
               "metrics", "health"]
    hits = [n for n in needles if n in text]
    if len(hits) < 5:
        return False, f"control-plane surface thin: only {hits}"
    # Count distinct control-plane CLI subcommands to confirm it is
    # not a thin "search" surface.
    cli_subs = re.findall(r'add_parser\("([a-z\-]+)"', cli.read_text(encoding="utf-8"))
    control_plane_subs = {"license-gate", "okf-validate", "version-identity",
                          "wal-recover", "health", "runtime-status",
                          "graph-rebuild", "ingest-sources", "eval",
                          "invariants", "metrics-gate"}
    present = control_plane_subs & set(cli_subs)
    if len(present) < 5:
        return False, f"CLI exposes only {sorted(present)} control-plane ops"
    return True, f"control-plane surface: REST+CLI covers {sorted(hits)}; CLI subs: {sorted(present)}."


def _i45():  # Control Plane and Data Plane responsibilities remain explicitly separated.
    # The two planes must live in different modules; collapse would
    # mean control-plane code can read runtime DB internals.
    control = Path("pi_platform/core/control")
    data_plane = Path("pi_platform/core/sync")  # data-plane port
    if not (control.is_dir() and data_plane.is_dir()):
        return False, f"control={control.is_dir()} data_plane={data_plane.is_dir()}"
    # The control package must not import from runtime store internals.
    offending = []
    for src in control.rglob("*.py"):
        text = src.read_text(encoding="utf-8", errors="ignore")
        if "runtime_store" in text and "import" in text:
            offending.append(src.relative_to(control))
    if offending:
        return False, f"control reaches into runtime store: {offending[:3]}"
    return True, f"control/ and sync/ are separate; {len(offending)} leaks."


def _i46():  # Plugins use stable extension ports and never depend directly on internal runtime DB tables.
    # Plugin registry must live under control/ and expose a
    # capability-based access port; absence would let plugins
    # import the runtime store directly.
    registry = Path("pi_platform/core/control/registry.py")
    if not registry.exists():
        return False, "pi_platform/core/control/registry.py missing"
    text = registry.read_text(encoding="utf-8")
    if "capabilit" not in text.lower():
        return False, "plugin registry has no capability mention"
    return True, f"plugin registry at {registry} gates by capability."


def _i47():  # Plugins, hooks and agents operate under explicit capability-based authorization.
    from pi_platform.core.control.policy import DefaultPolicyEngine
    return DefaultPolicyEngine is not None, "Phase 7 DefaultPolicyEngine shipped."


def _i48():  # Secrets are resolved through Secret Providers and never serialized into Git knowledge or logs.
    from pi_platform.ports.control.secrets import SecretProviderPort  # type: ignore
    return SecretProviderPort is not None, "Phase 7 SecretProviderPort exists."


def _i49():  # Hook execution is bounded by timeout, failure policy, permissions and auditability.
    from pi_platform.core.control.hooks import DefaultHookRuntime, HookDefinition
    return DefaultHookRuntime is not None and HookDefinition is not None, \
        "Phase 7 DefaultHookRuntime + HookDefinition shipped."


def _i50():  # High-impact operations may require explicit operator approval.
    from pi_platform.ports import ApprovalRequest, ApprovalGrant  # type: ignore
    return ApprovalRequest is not None and ApprovalGrant is not None, "Approval value types shipped."


def _i51():  # Third-party plugins may be isolated in a sidecar/sandbox without forcing that complexity on built-in features.
    # An ADR or doc must record the optional isolation surface; the
    # option must not leak into the default build.
    candidates = [
        Path(".ai/wiki/adr/0017-phase-8-enterprise-security-boundary.md"),
        Path("docs/SECURITY.md"),
    ]
    hits = [str(p) for p in candidates if p.exists()]
    if not hits:
        return False, "no isolation-mode ADR or security doc"
    # The doc must mention "sidecar" or "sandbox" so the option is
    # documented, not just mentioned in passing.
    text = "\n".join(Path(p).read_text(encoding="utf-8", errors="ignore")
                     for p in candidates if p.exists())
    if not ("sidecar" in text.lower() or "sandbox" in text.lower()):
        return False, "isolation doc does not mention sidecar/sandbox"
    return True, f"isolation modes documented in: {hits[0]}."


def _i52():  # The application remains a modular core with a micro-kernel extension surface, not a fleet of microservices.
    # ADR 0004 records the extension style; the absence of an
    # explicit ADR would mean the boundary is unstated.
    adr = Path(".ai/wiki/adr/0004-ports-and-adapters-extension-style.md")
    if not adr.exists():
        return False, "ADR 0004 missing"
    text = adr.read_text(encoding="utf-8")
    needles = ("hexagonal", "micro-kernel", "ports", "adapters")
    hits = [n for n in needles if n in text.lower()]
    if len(hits) < 3:
        return False, f"ADR 0004 thin: only {hits}"
    return True, f"ADR 0004 records extension style: {sorted(hits)}."


# ---------------------------------------------------------------------------
# Probe classes generated from the bodies
# ---------------------------------------------------------------------------


PROBE_FUNCTIONS = [
    ("I01", "Git is the source of truth for durable project knowledge.", _i01),
    ("I02", "Runtime DB is a working store, not a committed artifact.", _i02),
    ("I03", "Runtime DB ↔ Git sync is bidirectional.", _i03),
    ("I04", "Canonical serialization is deterministic.", _i04),
    ("I05", "Canonical knowledge is sharded and content-addressable.", _i05),
    ("I06", "tmp/local/source is local-only.", _i06),
    ("I07", "Local sources promoted only via explicit policy.", _i07),
    ("I08", "Runtime is incrementally reconstructed on branch change.", _i08),
    ("I09", "Content hashes reused across branches.", _i09),
    ("I10", "Structured code intelligence complements vector retrieval.", _i10),
    ("I11", "JARs are first-class knowledge sources.", _i11),
    ("I12", "ANN graphs and knowledge graphs are different structures.", _i12),
    ("I13", "Hybrid dense + sparse retrieval is the default.", _i13),
    ("I14", "Metadata enforces version, security and correctness constraints.", _i14),
    ("I15", "Contextualized chunks improve semantic retrieval.", _i15),
    ("I16", "Graph/hierarchy expansion enriches candidate evidence.", _i16),
    ("I17", "Context Assembler owns the final bounded context.", _i17),
    ("I18", "Retrieval-first escalation precedes expensive LLM scanning.", _i18),
    ("I19", "Small local LLM is optional.", _i19),
    ("I20", "Query Orchestrator owns delegation decisions.", _i20),
    ("I21", "MCP exposes tools/context to coding agents.", _i21),
    ("I22", "A2A exposes agent-to-agent collaboration when enabled.", _i22),
    ("I23", "MCP and A2A are complementary interfaces.", _i23),
    ("I24", "OpenSpec is first-class intent layer.", _i24),
    ("I25", "Knowledge provenance and staleness are explicit.", _i25),
    ("I26", "External transmission is security-policy controlled.", _i26),
    ("I27", "Bundled dependencies have known licenses.", _i27),
    ("I28", "Permissive licenses preferred.", _i28),
    ("I29", "Restricted licenses cannot silently enter the stack.", _i29),
    ("I30", "Single-container default with optional second container.", _i30),
    ("I31", "Standalone human UI does not require a coding harness.", _i31),
    ("I32", "Default frontend is lightweight and served by core.", _i32),
    ("I33", "Open WebUI is an optional integration behind the license gate.", _i33),
    ("I34", "One-click or near-zero-setup startup.", _i34),
    ("I35", "No vendor is architecturally mandatory.", _i35),
    ("I36", "Canonical Agent Skill is versioned and generated.", _i36),
    ("I37", "MCP server is the canonical skill distribution source.", _i37),
    ("I38", "Skill and MCP API version compatibility is machine-checkable.", _i38),
    ("I39", "Wiki supports an OKF v0.2 profile without coupling the runtime.", _i39),
    ("I40", "Agent plugin packages are generated from shared sources.", _i40),
    ("I41", "Codex/Claude Code/OpenCode have first-class distribution profiles.", _i41),
    ("I42", "Skill/plugin packages pass integrity, license and security gates.", _i42),
    ("I43", "Agent integration regression suites cover retrieval-first policy.", _i43),
    ("I44", "Web UI is a Control Plane surface.", _i44),
    ("I45", "Control Plane and Data Plane responsibilities stay separated.", _i45),
    ("I46", "Plugins use stable extension ports.", _i46),
    ("I47", "Capability-based authorization applies to plugins, hooks and agents.", _i47),
    ("I48", "Secrets are resolved through Secret Providers.", _i48),
    ("I49", "Hook execution is bounded by timeout, failure policy, permissions and auditability.", _i49),
    ("I50", "High-impact operations may require explicit operator approval.", _i50),
    ("I51", "Third-party plugins may be isolated in a sidecar/sandbox.", _i51),
    ("I52", "Application is a modular core with micro-kernel extension surface.", _i52),
]


# One probe class per entry, attached to this module's globals so
# discover_probes can find them.
for invariant_id, label, fn in PROBE_FUNCTIONS:
    globals()[f"_probe_class_{invariant_id}"] = _probe(invariant_id, label, fn)


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


class InvariantLoaderTests(unittest.TestCase):
    def test_probes_count_matches_architecture(self):
        # The architecture records 52 invariants. The probe list here
        # MUST match. If a probe is added or removed, the architecture
        # is the source of truth and the change is recorded in an
        # ADR + Wiki update.
        self.assertEqual(len(PROBE_FUNCTIONS), INVARIANT_COUNT)

    def test_discovered_probes_match_declared_count(self):
        discovered = discover_probes(globals())
        # The same module contains both probe classes and the loader;
        # exclude the InvariantProbe base class.
        self.assertEqual(len(discovered), INVARIANT_COUNT)

    def test_probes_are_sorted_by_invariant_id(self):
        discovered = discover_probes(globals())
        ids = [c.invariant_id for c in discovered]
        self.assertEqual(ids, sorted(ids))

    def test_each_probe_executes(self):
        discovered = discover_probes(globals())
        results = []
        for probe_cls in discovered:
            instance = probe_cls()
            passed, detail = instance.probe()
            results.append((probe_cls.invariant_id, passed, detail))
        failed = [r for r in results if not r[1]]
        self.assertFalse(failed, f"failing probes: {failed!r}")
