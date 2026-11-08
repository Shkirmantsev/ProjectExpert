# Tasks

- [x] 1. Research official SEP-2640 and current Beta extension specification.
- [x] 2. Add failing protocol, integrity, compatibility and boundary regressions.
- [x] 3. Implement manifests, standard resources and shared transport discovery.
- [x] 4. Verify actual container packaging and HTTP/stdio delivery.
- [x] 5. Update Wiki, operator instructions and accepted spec.
- [x] 6. Run focused tests, OpenSpec validation, artifact manifest and full harness.

Verification: `python3 harness.py check` PASS; 56 focused protocol/distribution
tests PASS; 11 standalone HTTP/stdio tests PASS; final local image
`projectexpert:local-mcp-skills-20261108` minimal Docker smoke (discovery, every
resource digest, restart and cleanup) PASS. No upstream image was published.
