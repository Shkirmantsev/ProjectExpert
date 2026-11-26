# Design

Allowlist the browser's read-only methods and routes. Use the viewer role and retrieval-only search before authentication, with a limited index status projection. Defer loading and showing administrative UI controls until the authorization endpoint confirms access. Retain existing policy and bearer checks for integration endpoints.
