# Verification evidence

- Before implementation: new capacity/frontend/upgrade regressions failed on old defaults and missing behavior. Existing readiness retry was characterized rather than presumed broken.
- 78 focused deployment, UI and inference tests PASS.
- 47 final portable deployment, runtime repair and inference policy tests PASS.
- Actual embedding-port failure followed by a successful same-cache retry PASS; persisted reason clears and chat settings survive.
- Merged CPU Compose configuration with the optional profile PASS; explicit 4096 flags, internal endpoint and loopback binding checked.
- Pinned installed Open WebUI 0.6.5 image provides Python/urllib/json probe dependencies (isolated network-disabled container check PASS); probe status true/false behavior covered by HTTP fixture.
- Strict OpenSpec validation PASS (active change included).
- Full python3 harness.py check: PASS (including module tests, Wiki, strict specs, isolated Docker checks and manifest).

## Limits
No target repository or running deployment modified. No new application/kit artifact published. The strengthened real Gemma CPU smoke is NOT RUN locally: pinned runtime image and model cache are absent; no large downloads were initiated. CI release smoke uses the shared shipped argument vector and a runtime-tokenized >1049-token document. Native GPU/Windows hardware verification is NOT RUN in this task.
