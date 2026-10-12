"""Phase 7 §59.6, §59.7 default Hook Runtime.

The default runtime fires on the documented lifecycle
events with bounded timeout, cancellation, structured
result, correlation id, audit record, bounded retries if
explicitly configured and the documented failure policies.

Every hook callback runs on a bounded worker thread so the
documented ``timeout_ms`` is enforceable and the calling
data-plane action cannot be deadlocked by a hanging hook.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional

from pi_platform.core.control.audit import _safe_record
from pi_platform.ports.control.hooks import (
    HookCancelledError,
    HookContext,
    HookDefinition,
    HookEvent,
    HookFailurePolicy,
    HookResult,
    HookRuntimePort,
    HookTimeoutError,
)


__all__ = ["DefaultHookRuntime"]


@dataclass
class DefaultHookRuntime(HookRuntimePort):
    """Default production Hook Runtime."""

    _hooks: dict[str, HookDefinition] = field(default_factory=dict)
    _cancellations: dict[str, threading.Event] = field(
        default_factory=dict, repr=False)
    _audit_hook: Optional[object] = field(default=None, repr=False)
    _policy_engine: Optional[object] = field(default=None, repr=False)
    _plugin_registry: Optional[object] = field(default=None, repr=False)
    _plugin_disable_hook: Optional[Callable[[str], None]
                                  ] = field(default=None, repr=False)

    def register(self, definition: HookDefinition) -> None:
        self._hooks[definition.hook_id] = definition

    def unregister(self, hook_id: str) -> None:
        self._hooks.pop(hook_id, None)

    def dispatch(self, event: HookEvent, *,
                 correlation_id: str,
                 project_version: str,
                 input_payload: Mapping[str, object]
                 ) -> HookResult:
        cancel_event = threading.Event()
        self._cancellations[correlation_id] = cancel_event
        try:
            hooks = sorted(
                (h for h in self._hooks.values() if h.event is event),
                key=lambda h: h.priority,
            )
            if not hooks:
                return HookResult(
                    hook_id="", plugin_id="", event=event,
                    duration_ms=0, status="ok",
                    correlation_id=correlation_id,
                )
            # Every matching hook fires in documented
            # priority order. A single-hook dispatch returns
            # that hook's structured result unchanged; a
            # multi-hook dispatch aggregates the per-hook
            # results so no registered hook is silently
            # dropped.
            results = []
            for hook in hooks:
                # Consult the Phase 7 Policy Engine before
                # dispatching the hook payload. The runtime
                # raises the typed DeniedError /
                # ApprovalRequired when the policy engine
                # denies or demands approval.
                self._check_policy(hook, correlation_id=correlation_id,
                                    project_version=project_version)
                results.append(self._invoke(
                    hook,
                    correlation_id=correlation_id,
                    project_version=project_version,
                    input_payload=input_payload,
                    cancel_event=cancel_event,
                ))
            if len(results) == 1:
                return results[0]
            status = "ok"
            for result in results:
                if result.status != "ok":
                    status = result.status
                    break
            return HookResult(
                hook_id="", plugin_id="", event=event,
                duration_ms=sum(r.duration_ms for r in results),
                status=status,
                correlation_id=correlation_id,
                output={"results": [
                    {"hookId": r.hook_id, "pluginId": r.plugin_id,
                     "status": r.status, "durationMs": r.duration_ms}
                    for r in results
                ]},
            )
        finally:
            self._cancellations.pop(correlation_id, None)

    def list_event_hooks(self, event: HookEvent
                         ) -> Iterable[HookDefinition]:
        for h in sorted(
            (h for h in self._hooks.values() if h.event is event),
            key=lambda h: h.priority,
        ):
            yield h

    def cancel(self, correlation_id: str) -> None:
        event = self._cancellations.get(correlation_id)
        if event is not None:
            event.set()

    def serialise(self) -> str:
        payload = {
            "hooks": [
                {**h.as_dict(), "callback": None}
                for h in sorted(self._hooks.values(),
                                key=lambda h: h.hook_id)
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_policy(self, hook: HookDefinition, *,
                       correlation_id: str,
                       project_version: str) -> None:
        if self._policy_engine is None:
            return
        from pi_platform.ports.control.policy import (
            Capability, PolicyRequest, Role, UnknownCapabilityError,
        )
        # Map the hook event to a coarse capability. Hooks
        # may declare additional capabilities in
        # ``hook.permissions``; the policy engine evaluates
        # the union, so a declared ``secret.resolve`` /
        # ``secret.reference`` / ``audit.write`` request is
        # authorised even when the event mapping alone
        # would not ask for it.
        capabilities = [self._capability_for_event(hook.event)]
        for permission in hook.permissions:
            try:
                capabilities.append(Capability(permission))
            except ValueError as exc:
                raise UnknownCapabilityError(
                    f"unknown-capability: capability={permission!r}"
                ) from exc
        for capability in capabilities:
            self._policy_engine.authorize(PolicyRequest(
                actor_type="hook",
                actor_id=hook.plugin_id,
                role=Role.MAINTAINER,
                capability=capability,
                resource=hook.hook_id,
                project_version=project_version,
                correlation_id=correlation_id,
            ))

    def _capability_for_event(self, event: HookEvent) -> "object":
        from pi_platform.ports.control.policy import Capability
        # Security-sensitive hooks require ``secret.resolve``
        # authority; observability hooks require ``audit.write``.
        if event in (
            HookEvent.BEFORE_MATERIALIZATION,
            HookEvent.BEFORE_MCP_TOOL,
            HookEvent.BEFORE_AGENT_DELEGATION,
        ):
            return Capability.SECRET_RESOLVE
        if event in (
            HookEvent.AFTER_RETRIEVAL,
            HookEvent.AFTER_CONTEXT_ASSEMBLY,
            HookEvent.AFTER_MCP_TOOL,
        ):
            return Capability.AUDIT_WRITE
        return Capability.AUDIT_WRITE

    def _invoke(self, hook: HookDefinition, *,
                correlation_id: str,
                project_version: str,
                input_payload: Mapping[str, object],
                cancel_event: threading.Event) -> HookResult:
        policy = hook.failure_policy
        start = time.monotonic_ns()
        attempts = 0
        last_error: Optional[BaseException] = None
        max_attempts = max(1, hook.max_retries + 1)
        while attempts < max_attempts:
            attempts += 1
            try:
                if cancel_event.is_set():
                    raise HookCancelledError(
                        f"hook-cancelled: hook_id={hook.hook_id}")
                if hook.callback is None:
                    duration_ms = (time.monotonic_ns() - start) // 1_000_000
                    self._audit(operation=f"hook.{hook.event.value}",
                                status="ok", correlation_id=correlation_id,
                                duration_ms=duration_ms,
                                plugin_id=hook.plugin_id)
                    return HookResult(
                        hook_id=hook.hook_id,
                        plugin_id=hook.plugin_id,
                        event=hook.event,
                        duration_ms=duration_ms,
                        status="ok",
                        correlation_id=correlation_id,
                    )
                ctx = HookContext(
                    hook_id=hook.hook_id,
                    plugin_id=hook.plugin_id,
                    event=hook.event,
                    correlation_id=correlation_id,
                    project_version=project_version,
                    input_payload=dict(input_payload),
                )
                output = self._run_callback(hook, ctx, cancel_event)
                if not isinstance(output, HookResult):
                    duration_ms = (time.monotonic_ns() - start) // 1_000_000
                    output = HookResult(
                        hook_id=hook.hook_id,
                        plugin_id=hook.plugin_id,
                        event=hook.event,
                        duration_ms=duration_ms,
                        status="ok",
                        output={"value": output},
                        correlation_id=correlation_id,
                    )
                self._audit(operation=f"hook.{hook.event.value}",
                            status=output.status,
                            correlation_id=correlation_id,
                            duration_ms=output.duration_ms,
                            plugin_id=hook.plugin_id)
                return output
            except HookTimeoutError as exc:
                last_error = exc
                break
            except HookCancelledError as exc:
                last_error = exc
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        duration_ms = (time.monotonic_ns() - start) // 1_000_000
        self._apply_failure_policy(hook, policy, last_error,
                                   correlation_id, duration_ms)
        if isinstance(last_error, HookTimeoutError):
            status = "timeout"
        elif isinstance(last_error, HookCancelledError):
            status = "cancelled"
        else:
            status = "error"
        return HookResult(
            hook_id=hook.hook_id,
            plugin_id=hook.plugin_id,
            event=hook.event,
            duration_ms=duration_ms,
            status=status,
            correlation_id=correlation_id,
        )

    def _run_callback(self, hook: HookDefinition, ctx: "HookContext",
                      cancel_event: threading.Event) -> object:
        """Run the hook callback on a worker thread bounded
        by the documented ``timeout_ms``.

        A hook that exceeds its timeout MUST NOT deadlock
        the calling data-plane action: the caller unblocks
        with the typed :class:`HookTimeoutError` and the
        cancel event is raised so a cooperative worker can
        exit within the documented cancellation grace
        window.
        """
        box: dict[str, object] = {}

        def _target() -> None:
            try:
                box["output"] = hook.callback(ctx)  # type: ignore[misc]
            except BaseException as exc:  # noqa: BLE001
                box["error"] = exc

        worker = threading.Thread(
            target=_target, daemon=True, name=f"hook-{hook.hook_id}")
        worker.start()
        worker.join(timeout=max(hook.timeout_ms, 0) / 1000.0)
        if worker.is_alive():
            cancel_event.set()
            raise HookTimeoutError(
                f"hook-timeout: hook_id={hook.hook_id} "
                f"timeout_ms={hook.timeout_ms}")
        if "error" in box:
            raise box["error"]  # type: ignore[misc]
        if cancel_event.is_set():
            raise HookCancelledError(
                f"hook-cancelled: hook_id={hook.hook_id}")
        return box.get("output")

    def _apply_failure_policy(self, hook: HookDefinition,
                              policy: HookFailurePolicy,
                              error: Optional[BaseException],
                              correlation_id: str,
                              duration_ms: int) -> None:
        self._audit(operation=f"hook.{hook.event.value}.failure",
                    status=policy.value,
                    correlation_id=correlation_id,
                    duration_ms=duration_ms,
                    plugin_id=hook.plugin_id)
        if isinstance(error, HookTimeoutError):
            # §59.6 bounded-timeout scenario audit entry.
            self._audit(
                operation="hook.timeout",
                status=("denied" if policy is HookFailurePolicy.FAIL_CLOSED
                        else policy.value),
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                plugin_id=hook.plugin_id)
        if policy is HookFailurePolicy.FAIL_OPEN:
            return
        if policy is HookFailurePolicy.WARN_ONLY:
            return
        if policy is HookFailurePolicy.DISABLE_PLUGIN:
            if self._plugin_disable_hook is not None:
                try:
                    self._plugin_disable_hook(hook.plugin_id)
                except Exception:
                    pass
            return
        # FAIL_CLOSED: propagate
        if isinstance(error, HookTimeoutError):
            raise error
        if isinstance(error, HookCancelledError):
            raise error
        if error is not None:
            raise error
        raise HookTimeoutError(
            f"hook-failed-closed: hook_id={hook.hook_id}")

    def _audit(self, *, operation: str, status: str,
               correlation_id: str, duration_ms: int,
               plugin_id: str = "") -> None:
        _safe_record(
            self._audit_hook,
            operation=operation,
            result=status,
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            plugin_agent_id=plugin_id,
        )

    def attach_policy_engine(self, policy: object) -> None:
        self._policy_engine = policy

    def attach_audit_log(self, audit_log: object) -> None:
        self._audit_hook = audit_log