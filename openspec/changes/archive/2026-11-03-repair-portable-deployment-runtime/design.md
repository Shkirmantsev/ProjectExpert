# Design

Use explicit llama.cpp argument vectors consistently across accelerator, CUDA, Vulkan and native defaults. 4096 provides headroom for the existing chunk projection and task prompt; it is not an unlimited-input guarantee.

Keep Open WebUI optional through Compose profile open-webui in the base topology, so all existing launch wrappers retain the same topology. Its API base is the internal production:8765/v1 address. Override the pinned image's curl/jq probe with Python urllib and JSON status validation; retain application authentication defaults.

The exporter remains non-destructive by default. Explicit --upgrade updates managed templates with backups of changed files, preserves operator deployment.env and unrecognized files, and refuses managed symlinks before writes. New environment defaults must be documented for existing env files.

Add an end-to-end failed embedding followed by successful retry regression. If current readiness already recovers, record that observation and avoid speculative code changes. Never delete the whole runtime cache as routine recovery because it includes chat credentials and vector reuse.
