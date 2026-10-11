"""Phase 9 Block A1 — REST port declaration and core UI service behaviour.

Covers ``openspec/changes/implement-phase-9-distribution/specs/2026-10-11-human-interface-web-ui/spec.md``:
the ten-operation surface, policy authorisation with deny-by-default, fail-closed
materialisation and egress-gated delegation.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from pi_platform.core.ui.rest_service import (
    OPERATION_CAPABILITIES,
    RestService,
    UiOperationDenied,
)
from pi_platform.ports import ApprovalGrant, ApprovalRequest
from pi_platform.ports.control.policy import (
    Capability,
    Decision,
    PolicyDecision,
    PolicyRequest,
    Role,
)
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    RetrievalQuery,
    RetrievalResult,
)
from pi_platform.ports.security.egress import EgressChannel, EgressDecision
from pi_platform.ports.ui.rest_api import (
    UI_OPERATIONS,
    AgentDelegationRequest,
    GraphRequest,
    MaterializeRequest,
    QueryRequest,
    RetrieveRequest,
    UiActor,
    WikiRequest,
)

ACTOR = UiActor(actor_type="human", actor_id="operator", role=Role.VIEWER.value)


class FakePolicy:
    """Policy engine double recording every authorisation request."""

    def __init__(self, decision=Decision.ALLOW, by_capability=None):
        self._decision = decision
        self._by_capability = by_capability or {}
        self.requests: list[PolicyRequest] = []

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        self.requests.append(request)
        decision = self._by_capability.get(request.capability, self._decision)
        return PolicyDecision(
            decision=decision,
            capability=request.capability,
            resource=request.resource,
            policy_decision_rationale="test",
        )

    def capabilities_for(self, operation: str) -> set:
        return {r.capability for r in self.requests if r.resource == operation}


class FakeOrchestrator:
    def __init__(self):
        self.calls: list[tuple] = []

    def orchestrate(self, query, *, level=None, **kwargs):
        self.calls.append((query, level))
        return type(
            "R",
            (),
            {
                "level": type("L", (), {"name": "LEVEL_0"})(),
                "retrieval": None,
                "llm_completion": "answer",
                "explanations": ("direct retrieval",),
                "budgetUsed": 7,
            },
        )()

    def escalate(self, orchestration, *, reason):  # pragma: no cover - unused
        raise AssertionError("escalation not expected")

    def stats(self):  # pragma: no cover - unused
        return {}


class FakeRetrieval:
    def __init__(self):
        self.queries: list[RetrievalQuery] = []

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        self.queries.append(query)
        return RetrievalResult(hits=("hit-1",), conflicts=("conflict-1",))

    def stats(self):  # pragma: no cover - unused
        return {}


class FakeGit:
    def head(self, repo_root: Path) -> str:
        return "deadbeef"

    def current_branch(self, repo_root: Path):
        return "feature/x"


class FakeReadiness:
    def __init__(self, consistent=True, in_progress=False):
        self._snapshot = type(
            "S",
            (),
            {
                "consistent": consistent,
                "in_progress": in_progress,
                "current_head": "deadbeef",
                "working_tree_fingerprint": "fp",
                "last_hydrate_at": 11,
                "last_reconcile_at": 12,
                "reason": "",
            },
        )()

    def snapshot(self):
        return self._snapshot

    def is_ready(self):
        return bool(self._snapshot.consistent) and not self._snapshot.in_progress


class FakeApproval:
    def __init__(self, valid_tokens=("good-token",)):
        self.valid = set(valid_tokens)
        self.calls: list[tuple] = []

    def issue(self, request, *, ttl_seconds: int = 300, issuer: str = "operator"):
        return "good-token"

    def verify(self, request: ApprovalRequest, token):
        self.calls.append((request, token))
        if token not in self.valid:
            raise PermissionError("invalid approval token")
        return ApprovalGrant(
            request=request, not_before=0, not_after=999999, issuer="operator"
        )


class FakeEgress:
    def __init__(self, allowed=True, rationale=""):
        self._allowed = allowed
        self._rationale = rationale
        self.requests = []

    def evaluate(self, request):
        self.requests.append(request)
        return EgressDecision(
            allowed=self._allowed,
            rationale=self._rationale,
            channel=EgressChannel.EXTERNAL,
            request=request,
        )

    def serialise(self) -> str:  # pragma: no cover - unused
        return "{}"


class FakeMaterialise:
    def __init__(self, okf_errors=()):
        self.calls: list[tuple] = []
        self._okf_errors = tuple(okf_errors)

    def materialise_durable_changes(self, repo_root, *, cache_root, approval_token=None, changes=None):
        self.calls.append((repo_root, approval_token))
        return type(
            "R",
            (),
            {
                "diff_files": ("project-knowledge/wiki/index.md",),
                "excluded_local_only": (),
                "policy_decision": None,
                "okf_validation_errors": self._okf_errors,
            },
        )()


class FakeRuntimeStore:
    def runtime_status(self, **kwargs):
        return type(
            "R",
            (),
            {
                "bound_version": "0.1.0",
                "backend": "sqlite",
                "cache_entries": 3,
                "wal_tail_length": 0,
                "families": (),
                "family_counts": (),
            },
        )()


def build_service(**overrides) -> RestService:
    repo = Path("/tmp/phase9-rest-core")
    defaults = dict(
        repo_root=repo,
        policy=FakePolicy(),
        orchestrator=FakeOrchestrator(),
        retrieval=FakeRetrieval(),
        git=FakeGit(),
        readiness=FakeReadiness(),
        approval=FakeApproval(),
        egress=FakeEgress(),
        materialise=FakeMaterialise(),
        runtime_store=FakeRuntimeStore(),
    )
    defaults.update(overrides)
    return RestService(**defaults)


class PortContractTests(unittest.TestCase):
    """The port declares exactly the ten §44.3 operations."""

    def test_operation_set_matches_architecture(self):
        self.assertEqual(
            set(UI_OPERATIONS),
            {
                "query",
                "retrieve",
                "sources",
                "graph",
                "wiki",
                "project-version",
                "indexing-status",
                "knowledge-status",
                "materialize",
                "agent-delegation",
            },
        )
        self.assertEqual(len(UI_OPERATIONS), 10)

    def test_every_operation_maps_to_a_capability(self):
        self.assertEqual(set(OPERATION_CAPABILITIES), set(UI_OPERATIONS))

    def test_materialize_maps_to_materialize_capability(self):
        self.assertIs(
            OPERATION_CAPABILITIES["materialize"], Capability.KNOWLEDGE_MATERIALIZE
        )

    def test_agent_delegation_maps_to_delegate_capability(self):
        self.assertIs(
            OPERATION_CAPABILITIES["agent-delegation"], Capability.AGENT_DELEGATE
        )

    def test_core_imports_no_http_transport(self):
        import pi_platform.core.ui.rest_service as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("http.server", source)
        self.assertNotIn("pi_platform.adapters", source)


class ReadOperationTests(unittest.TestCase):
    def test_query_delegates_to_orchestrator(self):
        service = build_service()
        result = service.query(ACTOR, QueryRequest(text="where is OrderStatus"))
        self.assertEqual(result.mode, "LEVEL_0")
        self.assertEqual(result.answer, "answer")
        self.assertEqual(service._orchestrator.calls, [("where is OrderStatus", None)])

    def test_retrieve_uses_deterministic_retrieval_only(self):
        service = build_service()
        result = service.retrieve(ACTOR, RetrieveRequest(text="order", top_k=3))
        self.assertEqual(result.results, ("hit-1",))
        self.assertEqual(service._retrieval.queries[0].top_k, 3)
        self.assertEqual(service._orchestrator.calls, [])

    def test_project_version_uses_git_identity(self):
        result = build_service().project_version(ACTOR)
        self.assertEqual(result.head, "deadbeef")
        self.assertEqual(result.branch, "feature/x")

    def test_indexing_status_reports_hydration(self):
        result = build_service().indexing_status(ACTOR)
        self.assertTrue(result.ready)
        self.assertEqual(result.indexes["backend"], "sqlite")

    def test_indexing_status_is_not_ready_while_hydrating(self):
        service = build_service(readiness=FakeReadiness(consistent=False, in_progress=True))
        self.assertFalse(service.indexing_status(ACTOR).ready)

    def test_wiki_and_sources_without_projection_return_empty(self):
        service = build_service()
        self.assertEqual(service.sources(ACTOR).sources, ())
        self.assertEqual(service.wiki(ACTOR, WikiRequest(query="x")).documents, ())
        self.assertEqual(service.graph(ACTOR, GraphRequest(entity="E")).nodes, ())


class AuthorisationTests(unittest.TestCase):
    def test_unknown_operation_is_denied_by_default(self):
        self.assertNotIn("does-not-exist", OPERATION_CAPABILITIES)
        service = build_service()
        with self.assertRaises(UiOperationDenied):
            service._authorise("does-not-exist", ACTOR)

    def test_unknown_role_is_denied(self):
        service = build_service()
        bad = UiActor(actor_type="human", actor_id="x", role="wizard")
        with self.assertRaises(UiOperationDenied):
            service.query(bad, QueryRequest(text="q"))

    def test_policy_denial_stops_the_operation(self):
        service = build_service(policy=FakePolicy(decision=Decision.DENY))
        with self.assertRaises(UiOperationDenied):
            service.query(ACTOR, QueryRequest(text="q"))
        self.assertEqual(service._orchestrator.calls, [])

    def test_each_operation_requests_its_own_capability(self):
        service = build_service()
        service.query(ACTOR, QueryRequest(text="q"))
        service.retrieve(ACTOR, RetrieveRequest(text="q"))
        service.sources(ACTOR)
        service.project_version(ACTOR)
        self.assertIn(
            Capability.RETRIEVAL_QUERY, service._policy.capabilities_for("query")
        )
        self.assertIn(
            Capability.SOURCE_READ, service._policy.capabilities_for("sources")
        )
        self.assertIn(Capability.GIT_READ, service._policy.capabilities_for("project-version"))


class MaterialisationTests(unittest.TestCase):
    def test_materialize_without_token_writes_nothing(self):
        materialise = FakeMaterialise()
        service = build_service(materialise=materialise)
        with self.assertRaises(UiOperationDenied):
            service.materialize(ACTOR, MaterializeRequest())
        self.assertEqual(materialise.calls, [])

    def test_materialize_with_invalid_token_writes_nothing(self):
        materialise = FakeMaterialise()
        service = build_service(materialise=materialise)
        with self.assertRaises(PermissionError):
            service.materialize(ACTOR, MaterializeRequest(approval_token="bad"))
        self.assertEqual(materialise.calls, [])

    def test_materialize_with_valid_token_writes(self):
        materialise = FakeMaterialise()
        service = build_service(materialise=materialise)
        result = service.materialize(
            ACTOR, MaterializeRequest(approval_token="good-token")
        )
        self.assertTrue(result.materialized)
        self.assertEqual(len(materialise.calls), 1)

    def test_materialize_surfaces_okf_validation_failure(self):
        service = build_service(materialise=FakeMaterialise(okf_errors=("bad type",)))
        result = service.materialize(
            ACTOR, MaterializeRequest(approval_token="good-token")
        )
        self.assertFalse(result.materialized)
        self.assertEqual(result.okf_validation_errors, ("bad type",))

    def test_require_approval_without_token_is_denied(self):
        service = build_service(
            policy=FakePolicy(
                by_capability={Capability.KNOWLEDGE_MATERIALIZE: Decision.REQUIRE_APPROVAL}
            ),
            materialise=FakeMaterialise(),
        )
        with self.assertRaises(UiOperationDenied):
            service.materialize(ACTOR, MaterializeRequest())
        self.assertEqual(service._materialise.calls, [])


class DelegationTests(unittest.TestCase):
    def test_denied_egress_blocks_delegation(self):
        service = build_service(egress=FakeEgress(allowed=False, rationale="blocked"))
        result = service.agent_delegation(ACTOR, AgentDelegationRequest(task="do"))
        self.assertEqual(result.status, "denied")
        self.assertEqual(service._orchestrator.calls, [])

    def test_allowed_egress_delegates_to_orchestrator(self):
        service = build_service()
        result = service.agent_delegation(
            ACTOR, AgentDelegationRequest(task="implement REQ-1", target="https://x")
        )
        self.assertEqual(result.status, "delegated")
        self.assertEqual(service._orchestrator.calls, [("implement REQ-1", 2)])
        self.assertEqual(service._egress.requests[0].url, "https://x")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()