# syntax=docker/dockerfile:1.7
# One-click container for the v0.8 Project Intelligence Platform (Phase 9).
#
# Build:  docker build -t project-intelligence:dev .
# Run:    docker run --rm -p 8765:8765 \
#               -v "$(pwd):/repo" \
#               -e PI_TARGET_ROOT=/repo \
#               project-intelligence:dev serve --target /repo
#
# Composition (per design.md §45.1 "single-container default"):
#   - backend, REST surface, static UI, runtime store and MCP all in one image
#   - the lightweight static UI is served by this same container at GET /
#   - Node.js / npm are deliberately absent from the final image
#   - the OKF v0.2 compatibility profile ships at /opt/.../distribution/okf-profile
#
# Supply-chain (§5.5 / §34):
#   - base image pinned by digest (sha256:...) so rebuilds are reproducible
#   - refresh: pull `python:3.11-slim-bookworm`, update the digest, commit
FROM python:3.11-slim-bookworm@sha256:2333bd330d12de02514770b3585cad313644316047cdee24a7acfdece6de6efb AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PI_PLATFORM_HOME=/opt/project-intelligence \
    PI_CONTROL_PORT=8765

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/project-intelligence

# Phase 9 ships the full platform package plus the UI assets and the OKF
# compatibility profile. Bundling project Wiki content is explicitly forbidden
# (Block D2 anti-goals); the profile and template only are copied.
COPY pyproject.toml ./pyproject.toml
COPY README.md ./README.md
COPY pi_platform ./pi_platform
COPY distribution/okf-profile ./distribution/okf-profile
COPY distribution/licenses ./distribution/licenses
COPY distribution/sbom ./distribution/sbom

RUN pip install --no-cache-dir .

# Phase 4 retrieval opt-in dependencies. The default image ships
# without the heavy multilingual sentence-transformer stack so the
# CPU-only fallback (`HashingEmbeddingAdapter`) covers the
# multilingual-DE/EN/UK retrieval scenario. Install the
# `retrieval` extra in a derived image to enable the multilingual
# sentence-transformer adapter and the cross-encoder reranker.
# The ColBERT-style late-interaction adapter remains off by
# default; install the optional `colbert` extra in a derived
# image to enable it. All three extras pass `LicenseGate` against
# the SPDX inventory at `distribution/licenses/dependency-inventory.json`.
# RUN pip install --no-cache-dir ".[retrieval]"

# Java native libraries remain optional: install the approved java extra in a
# derived image to enable the isolated parser. Default uses metadata-only mode.

EXPOSE 8765

# Liveness probe. The readiness signal is exposed at /health/ready inside the
# HTTP adapter and reflects whether knowledge hydration finished; readiness is
# distinct from liveness (Block F1, #default-profile-is-one-container).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -m pi_platform.cli health || exit 1

ENTRYPOINT ["python", "-m", "pi_platform.cli"]
CMD ["serve", "--target", "/repo", "--host", "0.0.0.0", "--port", "8765"]