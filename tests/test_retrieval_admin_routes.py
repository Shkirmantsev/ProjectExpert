"""Tests for the administrative retrieval routes (open spec change PR 11).

Covers the ``one-command-production-ux`` spec delta:

* ``GET /api/v1/admin/retrieval`` returns the current settings;
* ``PUT /api/v1/admin/retrieval`` updates them — but ONLY for an
  ``administrator`` capability; an ordinary ``coding-agent`` caller
  receives HTTP 403 with a structured ``{error, code, details}`` body;
* ``POST /api/v1/admin/models/pull`` and ``POST /api/v1/admin/reindex``
  queue jobs and return ``{job_id, status: "queued"}``;
* ``GET /api/v1/admin/jobs/<job_id>`` reports ``{job_id, status,
  progress_pct, message}``;
* the dispatcher passes non-admin paths through untouched.

No Flask (or any web framework) is required: the dispatcher is a
plain ``(method, path, body) -> response`` callable.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pi_platform.adapters.ui.retrieval_admin_routes import (
    MODELS_PULL_PATH,
    RETRIEVAL_PATH,
    REINDEX_PATH,
    RetrievalAdminRoutes,
    RouteResponse,
    register_routes,
)
from pi_platform.core.control.retrieval_settings import (
    RetrievalSettings,
    load_retrieval_settings,
    save_retrieval_settings,
)


ADMIN = "administrator"
CODING_AGENT = "coding-agent"


class AdminRoutesTestBase(unittest.TestCase):
    """Shared temp-repo fixture with an administrator caller."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="retrieval-admin-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.capability = ADMIN
        self.passthrough_calls: list[tuple[str, str, object]] = []

    def _capability_provider(self) -> str:
        return self.capability

    def _app(self, method: str, path: str, body: object = None) -> str:
        self.passthrough_calls.append((method, path, body))
        return "passthrough"

    def build(
        self, *, capability: str = ADMIN,
    ) -> tuple[RetrievalAdminRoutes, object]:
        self.capability = capability
        routes = RetrievalAdminRoutes(
            target_repo=self.tmp,
            caller_capability_provider=self._capability_provider,
        )
        dispatch = register_routes(
            self._app, caller_capability_provider=self._capability_provider,
            target_repo=self.tmp, routes=routes,
        )
        return routes, dispatch

    @staticmethod
    def assertStructuredError(
        case: unittest.TestCase, response: RouteResponse, status: int,
    ) -> dict:
        case.assertEqual(response.status, status)
        case.assertEqual(
            set(response.body), {"error", "code", "details"},
        )
        case.assertIsInstance(response.body["error"], str)
        case.assertIsInstance(response.body["code"], str)
        case.assertIsInstance(response.body["details"], dict)
        return response.body


class GetRetrievalTests(AdminRoutesTestBase):
    """GET returns the current settings."""

    def test_get_returns_current_settings(self) -> None:
        save_retrieval_settings(
            RetrievalSettings(
                embedding_model_alias="gemma-torch",
                device="cpu",
                document_processing_enabled=False,
                bootstrap_state="ready",
            ),
            self.tmp,
        )
        _routes, dispatch = self.build()
        response = dispatch("GET", RETRIEVAL_PATH)
        self.assertIsInstance(response, RouteResponse)
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.body,
            load_retrieval_settings(self.tmp).as_dict(),
        )
        self.assertEqual(response.body["embedding_model_alias"], "gemma-torch")
        self.assertEqual(response.body["device"], "cpu")


class PutRetrievalTests(AdminRoutesTestBase):
    """PUT updates settings for administrators only."""

    def test_put_updates_settings(self) -> None:
        _routes, dispatch = self.build()
        response = dispatch(
            "PUT", RETRIEVAL_PATH,
            {"embedding_model_alias": "gemma-torch", "device": "cuda"},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["embedding_model_alias"], "gemma-torch")
        self.assertEqual(response.body["device"], "cuda")
        persisted = load_retrieval_settings(self.tmp)
        self.assertEqual(persisted.embedding_model_alias, "gemma-torch")
        self.assertEqual(persisted.device, "cuda")

    def test_put_refused_for_non_admin_caller(self) -> None:
        _routes, dispatch = self.build(capability=CODING_AGENT)
        response = dispatch(
            "PUT", RETRIEVAL_PATH, {"embedding_model_alias": "gemma-torch"},
        )
        body = self.assertStructuredError(self, response, 403)
        self.assertEqual(body["code"], "admin-capability-required")
        self.assertEqual(body["details"]["required_capability"], ADMIN)
        self.assertEqual(body["details"]["caller_capability"], CODING_AGENT)
        # Nothing was persisted.
        persisted = load_retrieval_settings(self.tmp)
        self.assertEqual(persisted.embedding_model_alias, "gemma")

    def test_get_refused_for_non_admin_caller(self) -> None:
        _routes, dispatch = self.build(capability=CODING_AGENT)
        response = dispatch("GET", RETRIEVAL_PATH)
        body = self.assertStructuredError(self, response, 403)
        self.assertEqual(body["code"], "admin-capability-required")

    def test_put_rejects_unknown_model(self) -> None:
        _routes, dispatch = self.build()
        response = dispatch(
            "PUT", RETRIEVAL_PATH, {"embedding_model_alias": "llama-70b"},
        )
        body = self.assertStructuredError(self, response, 400)
        self.assertEqual(body["code"], "invalid-retrieval-settings")


class JobQueueTests(AdminRoutesTestBase):
    """Model pull / reindex queue jobs; jobs report progress."""

    def test_models_pull_returns_queued_job(self) -> None:
        routes, dispatch = self.build()
        response = dispatch(
            "POST", MODELS_PULL_PATH, {"alias": "gemma"},
        )
        self.assertEqual(response.status, 202)
        self.assertEqual(response.body["status"], "queued")
        job_id = response.body["job_id"]
        self.assertIsInstance(job_id, str)
        self.assertTrue(job_id)
        self.assertIsNotNone(routes.job_view(job_id))

    def test_models_pull_rejects_unknown_alias(self) -> None:
        _routes, dispatch = self.build()
        response = dispatch(
            "POST", MODELS_PULL_PATH, {"alias": "llama-70b"},
        )
        body = self.assertStructuredError(self, response, 400)
        self.assertEqual(body["code"], "unknown-model-alias")

    def test_reindex_returns_queued_job(self) -> None:
        _routes, dispatch = self.build()
        response = dispatch("POST", REINDEX_PATH)
        self.assertEqual(response.status, 202)
        self.assertEqual(response.body["status"], "queued")
        self.assertTrue(response.body["job_id"])

    def test_job_status_reports_progress(self) -> None:
        routes, dispatch = self.build()
        job_id = routes.enqueue_job("reindex")
        view = dispatch("GET", f"/api/v1/admin/jobs/{job_id}")
        self.assertEqual(view.status, 200)
        self.assertEqual(
            set(view.body),
            {"job_id", "status", "progress_pct", "message"},
        )
        self.assertEqual(view.body["status"], "queued")
        self.assertEqual(view.body["progress_pct"], 0)

        routes.set_job_progress(
            job_id, status="running", progress_pct=40,
            message="embedding chunk 40/100",
        )
        view = dispatch("GET", f"/api/v1/admin/jobs/{job_id}")
        self.assertEqual(view.body["status"], "running")
        self.assertEqual(view.body["progress_pct"], 40)
        self.assertEqual(view.body["message"], "embedding chunk 40/100")

    def test_unknown_job_returns_404(self) -> None:
        _routes, dispatch = self.build()
        response = dispatch("GET", "/api/v1/admin/jobs/job-does-not-exist")
        body = self.assertStructuredError(self, response, 404)
        self.assertEqual(body["code"], "job-not-found")


class DispatcherTests(AdminRoutesTestBase):
    """Route recognition and pass-through behaviour."""

    def test_dispatcher_recognises_the_four_routes(self) -> None:
        routes, dispatch = self.build()
        table = routes.route_table()
        self.assertEqual(
            set(table),
            {
                ("GET", RETRIEVAL_PATH),
                ("PUT", RETRIEVAL_PATH),
                ("POST", MODELS_PULL_PATH),
                ("POST", REINDEX_PATH),
            },
        )
        recognised = [
            dispatch("GET", RETRIEVAL_PATH),
            dispatch("PUT", RETRIEVAL_PATH, {}),
            dispatch("POST", MODELS_PULL_PATH, {"alias": "gemma"}),
            dispatch("POST", REINDEX_PATH),
        ]
        for response in recognised:
            self.assertIsInstance(response, RouteResponse)
        # None of those calls fell through to the app.
        self.assertEqual(self.passthrough_calls, [])

    def test_unknown_admin_path_returns_structured_404(self) -> None:
        _routes, dispatch = self.build()
        response = dispatch("GET", "/api/v1/admin/does-not-exist")
        body = self.assertStructuredError(self, response, 404)
        self.assertEqual(body["code"], "route-not-found")
        self.assertEqual(self.passthrough_calls, [])

    def test_wrong_method_returns_405(self) -> None:
        _routes, dispatch = self.build()
        response = dispatch("DELETE", RETRIEVAL_PATH)
        body = self.assertStructuredError(self, response, 405)
        self.assertEqual(body["code"], "method-not-allowed")

    def test_unknown_path_passes_through(self) -> None:
        _routes, dispatch = self.build()
        result = dispatch("GET", "/api/v1/query", {"text": "hello"})
        self.assertEqual(result, "passthrough")
        self.assertEqual(
            self.passthrough_calls, [("GET", "/api/v1/query", {"text": "hello"})],
        )

    def test_routes_are_json_serialisable(self) -> None:
        _routes, dispatch = self.build()
        response = dispatch("GET", RETRIEVAL_PATH)
        self.assertEqual(
            json.loads(response.json()), response.body,
        )


if __name__ == "__main__":
    unittest.main()