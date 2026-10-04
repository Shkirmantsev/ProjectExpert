# Testing conventions

When practical, use:

```text
requirement/scenario -> failing test -> minimal implementation -> passing test -> refactor -> wider verification
```

- Derive tests from requirements/scenarios, not only from implementation shape.
- For bugs, add a regression/characterization test that demonstrates the defect when practical.
- Do not weaken or delete tests merely to make a change pass unless the approved behavior changed.
- Keep unit tests focused; use integration/component tests for real framework, persistence, messaging and external-contract behavior.
- Verify that the intended tests actually ran; zero-test success is not evidence.
- Cover important happy path, failure path, compatibility and retry/idempotency/concurrency effects where relevant.
