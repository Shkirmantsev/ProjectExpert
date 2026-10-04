# Implementation conventions

- Prefer the smallest behaviorally complete vertical change.
- Match established project patterns before introducing a new abstraction or dependency.
- Do not mix unrelated cleanup with a feature or bug fix.
- Preserve backward compatibility unless the approved requirement explicitly changes it.
- Verify real runtime configuration and boundaries; annotations or naming alone are not sufficient evidence.
- Validate inputs at appropriate boundaries and preserve original exceptions as causes when wrapping.
- Avoid mutable global state, hidden side effects, magic values, dead code, debug output, and unresolved TODOs without a reference.
- Record deviations from approved design and update the design before completion.
