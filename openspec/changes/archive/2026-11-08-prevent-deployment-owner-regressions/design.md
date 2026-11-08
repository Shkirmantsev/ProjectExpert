# Design

Application services in the portable kit and root Compose topology override the entrypoint with a small Python bootstrap. It imports the existing ownership preparation function before importing or dispatching the CLI. An incompatible image fails with an upgrade instruction before touching the target. The bootstrap enables preparation and uses PI_TARGET_ROOT, already supplied by Compose. Model setup retains its separate entrypoint and model-volume scope. No image digest is hardcoded in source: published kits still receive the tested digest through PI_DEPLOY_IMAGE.

On POSIX, the Wiki atomic writer applies the destination's existing rwx bits to its completed temporary file, or 0644 for a new page, before replacement. Restrictive existing modes remain restrictive. Windows retains its current filesystem behavior. This does not recursively chmod/chown source files or migrate deliberately private existing pages.

The release gate builds its test kit with the candidate image and checks fallback resolution without deployment.env. The real smoke test creates a curated page via MCP and verifies ownership and modes alongside cache ownership after restart.
