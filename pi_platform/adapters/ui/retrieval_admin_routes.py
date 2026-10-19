"""Administrative retrieval HTTP routes (open spec change PR 11, plan §59, §60).

Covers the ``one-command-production-ux`` spec delta: the platform
MUST expose administrative endpoints

* ``GET   /api/v1/admin/retrieval``
* ``PUT   /api/v1/admin/retrieval``
* ``POST  /api/v1/admin/models/pull``
* ``POST  /api/v1/admin/reindex``
* ``GET   /api/v1/admin/jobs/<job_id>``

and MUST require an ``administrator`` capability to invoke them — an
ordinary ``coding-agent`` caller receives HTTP 403 with a structured
``{"error", "code", "details"}`` body.

The module has **no Flask dependency**: it ships a tiny dispatcher
over an explicit route table. ``register_routes(app, ...)`` returns a
``dispatch(method, path, body)`` callable that recognises the
``/api/v1/admin/...`` paths and passes every other path through to
``app`` (which may be a plain ``(method, path, body) -> response``
callable or an object exposing ``add_route(path, method, handler)``).
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from pi_platform.core.control.retrieval_settings import (
    RetrievalSettings,
    RetrievalSettingsError,
    load_retrieval_settings,
    normalise_model_alias,
    save_retrieval_settings,
    validate_retrieval_settings,
)


__all__ = [
    "RouteResponse",
    "RetrievalAdminRoutes",
    "register_routes",
    "create_dispatcher",
    "build_route_table",
    "ADMIN_PREFIX",
    "ADMIN_CAPABILITY",
    "RETRIEVAL_PATH",
    "MODELS_PULL_PATH",
    "REINDEX_PATH",
    "JOBS_PREFIX",
]


ADMIN_CAPABILITY = "administrator"
RETRIEVAL_PATH = "/api/v1/admin/retrieval"
MODELS_PULL_PATH = "/api/v1/admin/models/pull"
REINDEX_PATH = "/api/v1/admin/reindex"
JOBS_PREFIX = "/api/v1/admin/jobs/"
ADMIN_PREFIX = "/api/v1/admin/"

_FIXED_ADMIN_PATHS = frozenset({
    RETRIEVAL_PATH, MODELS_PULL_PATH, REINDEX_PATH,
})


@dataclass(frozen=True)
class RouteResponse:
    """A JSON-able HTTP response (status code + body)."""

    status: int
    body: dict[str, Any]

    @classmethod
    def ok(cls, body: Mapping[str, Any], *, status: int = 200) -> "RouteResponse":
        return cls(status=status, body=dict(body))

    @classmethod
    def error(
        cls,
        status: int,
        *,
        error: str,
        code: str,
        details: Optional[Mapping[str, Any]] = None,
    ) -> "RouteResponse":
        """The mandated structured error shape."""

        return cls(
            status=status,
            body={
                "error": error,
                "code": code,
                "details": dict(details or {}),
            },
        )

    def json(self) -> str:
        """Serialise the body for the wire."""

        return json.dumps(self.body, sort_keys=True)


def _as_mapping(body: Any) -> Mapping[str, Any]:
    """Coerce a request body into a mapping (dict or JSON text)."""

    if body is None:
        return {}
    if isinstance(body, Mapping):
        return body
    if isinstance(body, (bytes, str)):
        try:
            decoded = json.loads(body)
        except ValueError as exc:
            raise RetrievalSettingsError(
                f"request body is not valid JSON: {exc}"
            ) from exc
        if isinstance(decoded, Mapping):
            return decoded
        raise RetrievalSettingsError("request body must be a JSON object")
    raise RetrievalSettingsError(
        f"request body must be a JSON object, got {type(body).__name__}"
    )


class RetrievalAdminRoutes:
    """The administrative route handlers plus their in-memory job registry.

    Construct one instance per target repository; the instance holds
    the current settings location and the queued-job bookkeeping the
    ``jobs/<id>`` endpoint reports on.
    """

    def __init__(
        self,
        *,
        target_repo: Path | None = None,
        caller_capability_provider: Callable[[], str] | None = None,
    ) -> None:
        self._target_repo = Path(target_repo) if target_repo else Path.cwd()
        self._caller_capability_provider = caller_capability_provider or (
            lambda: ADMIN_CAPABILITY
        )
        self._jobs: dict[str, dict[str, Any]] = {}

    # -- introspection -----------------------------------------------

    @property
    def target_repo(self) -> Path:
        return self._target_repo

    @property
    def caller_capability(self) -> str:
        """The capability string the current caller reports."""

        capability = self._caller_capability_provider()
        return str(capability).strip().lower() if capability else ""

    def current_settings(self) -> RetrievalSettings:
        """The persisted settings for the bound target repository."""

        return load_retrieval_settings(self._target_repo)

    # -- authorisation ------------------------------------------------

    def _forbidden(
        self, *, method: str, path: str, operation: str,
    ) -> RouteResponse:
        caller = self.caller_capability
        return RouteResponse.error(
            403,
            error=(
                f"{operation} requires the {ADMIN_CAPABILITY!r} capability; "
                f"caller has {caller!r}"
            ),
            code="admin-capability-required",
            details={
                "required_capability": ADMIN_CAPABILITY,
                "caller_capability": caller,
                "method": method,
                "path": path,
                "operation": operation,
            },
        )

    def _authorize_admin(
        self, *, method: str, path: str, operation: str,
    ) -> Optional[RouteResponse]:
        """Return the 403 response when the caller is not an administrator."""

        if self.caller_capability == ADMIN_CAPABILITY:
            return None
        return self._forbidden(method=method, path=path, operation=operation)

    # -- job registry --------------------------------------------------

    def enqueue_job(self, kind: str, **details: Any) -> str:
        """Register a queued job and return its ``job_id``."""

        job_id = f"job-{secrets.token_hex(8)}"
        self._jobs[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "status": "queued",
            "progress_pct": 0,
            "message": f"{kind} queued",
            "details": dict(details),
        }
        return job_id

    def set_job_progress(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress_pct: int | None = None,
        message: str | None = None,
    ) -> bool:
        """Update a queued job; ``False`` when the job is unknown."""

        job = self._jobs.get(job_id)
        if job is None:
            return False
        if status is not None:
            job["status"] = status
        if progress_pct is not None:
            job["progress_pct"] = int(progress_pct)
        if message is not None:
            job["message"] = message
        return True

    def job_view(self, job_id: str) -> Optional[dict[str, Any]]:
        """The ``{job_id, status, progress_pct, message}`` projection."""

        job = self._jobs.get(job_id)
        if job is None:
            return None
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "progress_pct": job["progress_pct"],
            "message": job["message"],
        }

    # -- handlers -------------------------------------------------------

    def handle_get_retrieval(self, body: Any = None) -> RouteResponse:
        """``GET /api/v1/admin/retrieval`` — current settings."""

        denied = self._authorize_admin(
            method="GET", path=RETRIEVAL_PATH, operation="retrieval settings read",
        )
        if denied is not None:
            return denied
        return RouteResponse.ok(self.current_settings().as_dict())

    def handle_put_retrieval(self, body: Any = None) -> RouteResponse:
        """``PUT /api/v1/admin/retrieval`` — update the settings.

        A model switch (or any other settings change) is refused with
        403 unless the caller reports the ``administrator`` capability;
        an ordinary ``coding-agent`` caller receives the structured
        authorisation error.
        """

        denied = self._authorize_admin(
            method="PUT", path=RETRIEVAL_PATH, operation="retrieval settings update",
        )
        if denied is not None:
            return denied
        try:
            patch = _as_mapping(body)
        except RetrievalSettingsError as exc:
            return RouteResponse.error(
                400, error=str(exc), code="invalid-request",
                details={"path": RETRIEVAL_PATH},
            )
        merged = dict(self.current_settings().as_dict())
        for key, value in patch.items():
            if key in ("model", "model_id", "embedding_model"):
                merged["embedding_model_alias"] = value
            else:
                merged[key] = value
        try:
            settings = validate_retrieval_settings(merged)
        except RetrievalSettingsError as exc:
            return RouteResponse.error(
                400,
                error=str(exc),
                code="invalid-retrieval-settings",
                details={"path": RETRIEVAL_PATH, "payload": dict(patch)},
            )
        try:
            save_retrieval_settings(settings, self._target_repo)
        except RetrievalSettingsError as exc:
            return RouteResponse.error(
                500,
                error=str(exc),
                code="settings-write-failed",
                details={"path": RETRIEVAL_PATH},
            )
        return RouteResponse.ok(settings.as_dict())

    def handle_models_pull(self, body: Any = None) -> RouteResponse:
        """``POST /api/v1/admin/models/pull`` — queue a model pull job."""

        denied = self._authorize_admin(
            method="POST", path=MODELS_PULL_PATH, operation="model pull",
        )
        if denied is not None:
            return denied
        try:
            payload = _as_mapping(body)
        except RetrievalSettingsError as exc:
            return RouteResponse.error(
                400, error=str(exc), code="invalid-request",
                details={"path": MODELS_PULL_PATH},
            )
        alias = payload.get("alias")
        if alias is None:
            return RouteResponse.error(
                400,
                error="request body must include the model 'alias'",
                code="invalid-request",
                details={"path": MODELS_PULL_PATH, "field": "alias"},
            )
        try:
            normalise_model_alias(alias)
        except RetrievalSettingsError as exc:
            return RouteResponse.error(
                400,
                error=str(exc),
                code="unknown-model-alias",
                details={"path": MODELS_PULL_PATH, "alias": str(alias)},
            )
        job_id = self.enqueue_job("models.pull", alias=str(alias))
        return RouteResponse(
            status=202,
            body={"job_id": job_id, "status": "queued"},
        )

    def handle_reindex(self, body: Any = None) -> RouteResponse:
        """``POST /api/v1/admin/reindex`` — queue a reindex job."""

        denied = self._authorize_admin(
            method="POST", path=REINDEX_PATH, operation="reindex",
        )
        if denied is not None:
            return denied
        job_id = self.enqueue_job("reindex")
        return RouteResponse(
            status=202,
            body={"job_id": job_id, "status": "queued"},
        )

    def handle_job_status(self, job_id: str, body: Any = None) -> RouteResponse:
        """``GET /api/v1/admin/jobs/<job_id>`` — job progress."""

        denied = self._authorize_admin(
            method="GET", path=JOBS_PREFIX + job_id, operation="job status read",
        )
        if denied is not None:
            return denied
        view = self.job_view(job_id)
        if view is None:
            return RouteResponse.error(
                404,
                error=f"unknown job {job_id!r}",
                code="job-not-found",
                details={"job_id": job_id},
            )
        return RouteResponse.ok(view)

    # -- route table -----------------------------------------------------

    def route_table(
        self,
    ) -> dict[tuple[str, str], Callable[[Any], RouteResponse]]:
        """The fixed ``(METHOD, path) -> handler`` route table."""

        return {
            ("GET", RETRIEVAL_PATH): self.handle_get_retrieval,
            ("PUT", RETRIEVAL_PATH): self.handle_put_retrieval,
            ("POST", MODELS_PULL_PATH): self.handle_models_pull,
            ("POST", REINDEX_PATH): self.handle_reindex,
        }


def build_route_table(
    routes: RetrievalAdminRoutes,
) -> dict[tuple[str, str], Callable[[Any], RouteResponse]]:
    """Return the route table for ``routes`` (the dispatcher's map)."""

    return routes.route_table()


def create_dispatcher(
    routes: RetrievalAdminRoutes,
    *,
    table: Mapping[tuple[str, str], Callable[[Any], RouteResponse]] | None = None,
    fallback: Callable[..., Any] | None = None,
) -> Callable[[str, str, Any], Any]:
    """Build ``dispatch(method, path, body=None)`` over ``routes``.

    Paths under ``/api/v1/admin/`` are matched against the route
    table (with ``/api/v1/admin/jobs/<job_id>`` handled by pattern);
    every other path is passed through to ``fallback`` (``None``
    passes the call through untouched by returning ``None``).
    """

    route_table = dict(table) if table is not None else routes.route_table()

    def dispatch(method: str, path: str, body: Any = None) -> Any:
        verb = (method or "").upper()
        if not str(path).startswith(ADMIN_PREFIX):
            if fallback is None:
                return None
            return fallback(method, path, body)
        if (verb, path) in route_table:
            return route_table[(verb, path)](body)
        if path in _FIXED_ADMIN_PATHS:
            return RouteResponse.error(
                405,
                error=f"method {verb!r} is not allowed for {path}",
                code="method-not-allowed",
                details={
                    "method": verb,
                    "path": path,
                    "allowed": sorted(
                        m for (m, p) in route_table if p == path
                    ),
                },
            )
        if path.startswith(JOBS_PREFIX):
            job_id = path[len(JOBS_PREFIX):]
            if not job_id or "/" in job_id:
                return RouteResponse.error(
                    404,
                    error=f"unknown admin path {path!r}",
                    code="route-not-found",
                    details={"method": verb, "path": path},
                )
            if verb != "GET":
                return RouteResponse.error(
                    405,
                    error=f"method {verb!r} is not allowed for {path}",
                    code="method-not-allowed",
                    details={"method": verb, "path": path, "allowed": ["GET"]},
                )
            return routes.handle_job_status(job_id, body)
        return RouteResponse.error(
            404,
            error=f"unknown admin path {path!r}",
            code="route-not-found",
            details={"method": verb, "path": path},
        )

    return dispatch


def register_routes(
    app: Callable[..., Any],
    *,
    caller_capability_provider: Callable[[], str],
    target_repo: Path | None = None,
    routes: RetrievalAdminRoutes | None = None,
) -> Callable[[str, str, Any], Any]:
    """Register the administrative routes and return the dispatcher.

    ``app`` serves two compatible roles:

    * an object exposing ``add_route(path, method, handler)`` gets
      every fixed admin route registered on it (blueprint-free,
      Flask-like);
    * a plain callable is used as the pass-through target for every
      path the admin dispatcher does not recognise.

    ``caller_capability_provider`` returns the caller's capability
    string (``"administrator"`` vs e.g. ``"coding-agent"``) and is
    consulted on every admin request.
    """

    admin_routes = routes or RetrievalAdminRoutes(
        target_repo=target_repo,
        caller_capability_provider=caller_capability_provider,
    )
    table = admin_routes.route_table()
    add_route = getattr(app, "add_route", None)
    if callable(add_route):
        for (method, path), handler in table.items():
            add_route(path, method, handler)
    fallback = app if callable(app) else None
    return create_dispatcher(admin_routes, table=table, fallback=fallback)