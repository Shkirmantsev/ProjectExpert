## Design
Use stdlib tomllib, ast and zipfile in additive Python adapters. Dependency records retain raw requirements and normalized package names; a conservative requirement parser preserves constraints/markers rather than solving them. Requirements include directives remain explicit partial evidence rather than following arbitrary filesystem paths. Wheel METADATA provides exact distribution identity and Requires-Dist edges; Python members provide source API evidence. No implicit network or target execution.

Reuse SourceAdapterRegistry, DependencyChunker, runtime record cache and normal hybrid retrieval. Version the changed parser composition so older plain-text caches cannot mask new structured records.

Review fixes stay in the responsible Wiki, launcher and release-gate layers. Verification uses regression tests, model-free integration, deployment config checks and real container checks where available. Physical Windows/CUDA certification and registry publication cannot be inferred from Linux tests.
