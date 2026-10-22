# syntax=docker/dockerfile:1.7
# One-click container for the v0.8 Project Intelligence Platform (Phase 9).
#
# Build:  docker build -f Containerfile --target production -t project-intelligence:production .
# Run:    docker run --rm -p 8765:8765 \
#               -v "$(pwd):/repo" \
#               -e PI_TARGET_ROOT=/repo \
#               project-intelligence:production serve --target /repo
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
FROM python:3.11-slim-bookworm@sha256:2333bd330d12de02514770b3585cad313644316047cdee24a7acfdece6de6efb AS core

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

# The operator-selected host repository normally has a different UID from root
# inside Docker Desktop/Linux. Trust only the documented mount, never '*'.
RUN git config --system --add safe.directory /repo

WORKDIR /opt/project-intelligence

# Phase 9 ships the full platform package plus the UI assets, canonical Agent
# Skill, evaluation corpora, and the OKF compatibility profile. Bundling
# project Wiki content or development harness files is explicitly forbidden
# (Block D2 anti-goals); only product runtime artefacts are copied.
LABEL org.opencontainers.image.title="Project Intelligence Platform" \
      org.opencontainers.image.description="Portable, version-aware project intelligence platform (REST, UI, MCP, A2A, OKF v0.2)" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/Shkirmantsev/ProjectExpert"

COPY pyproject.toml ./pyproject.toml
COPY README.md ./README.md
COPY pi_platform ./pi_platform
COPY distribution/okf-profile ./distribution/okf-profile
COPY distribution/skills ./distribution/skills
COPY distribution/licenses ./distribution/licenses
COPY distribution/sbom ./distribution/sbom
COPY evals ./evals

RUN pip install --no-cache-dir . \
    && python -m pi_platform.cli package-plugins --output-root /opt/project-intelligence/distribution

# The core target is deliberately model-free. Production below installs the
# complete dependency closure and enables fail-closed semantic startup.
ENV PI_STARTUP_PROFILE=minimal \
    PI_EMBEDDING_MODEL=hashing \
    PI_DENSE_INDEX=flat \
    PI_DOCLING_ENABLED=0

EXPOSE 8765

# Liveness probe. The readiness signal is exposed at /health/ready inside the
# HTTP adapter and reflects whether knowledge hydration finished; readiness is
# distinct from liveness (Block F1, #default-profile-is-one-container).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -m pi_platform.cli health || exit 1

ENTRYPOINT ["python", "-m", "pi_platform.cli"]
CMD ["serve", "--target", "/repo", "--host", "0.0.0.0", "--port", "8765"]

# Runnable OCI deployment artifact: docker run exports files; no Docker socket.
FROM python:3.11-slim-bookworm@sha256:2333bd330d12de02514770b3585cad313644316047cdee24a7acfdece6de6efb AS deployment-kit
WORKDIR /bundle
COPY distribution/deployment/ /bundle/
ARG PI_DEPLOY_IMAGE=ghcr.io/shkirmantsev/project-intelligence:production
RUN python -c 'import os,pathlib; [p.write_text(p.read_text().replace("ghcr.io/shkirmantsev/project-intelligence:production", os.environ["PI_DEPLOY_IMAGE"])) for p in pathlib.Path(".").glob("compose*.yaml")]'
ENTRYPOINT ["python", "/bundle/export.py"]

# Cache the hash-locked dependency closure independently from application edits.
FROM python:3.11-slim-bookworm@sha256:2333bd330d12de02514770b3585cad313644316047cdee24a7acfdece6de6efb AS production-dependencies
COPY requirements-production-linux-x86_64.txt /requirements-production-linux-x86_64.txt
RUN python -m pip install --no-cache-dir --require-hashes --prefix=/opt/production \
        --index-url https://pypi.org/simple \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r /requirements-production-linux-x86_64.txt

# Normal end-user image (CPU, Linux x86_64). No model weights are embedded.
# Build: docker build -f Containerfile --target production -t project-intelligence:production .
# Minimal: docker build -f Containerfile --target core -t project-intelligence:core .
FROM core AS production
COPY requirements-production-linux-x86_64.txt ./requirements-production-linux-x86_64.txt
COPY --from=production-dependencies /opt/production/ /usr/local/
RUN python -m pip install --no-cache-dir --no-deps ".[production]" \
    && python -m pip check \
    && python -m pi_platform.cli license-gate \
        --inventory distribution/licenses/production-dependency-inventory.json \
        --production-lock requirements-production-linux-x86_64.txt \
        --license-review distribution/licenses/production-license-review.json \
        --license-evidence distribution/licenses/production-license-evidence.json --sbom-output .
ENV PI_STARTUP_PROFILE=production \
    PI_EMBEDDING_MODEL=qwen \
    PI_DENSE_INDEX=usearch \
    PI_DOCLING_ENABLED=1 \
    PI_PREPARE_DOCLING=1 \
    XDG_CACHE_HOME=/models/cache \
    PI_MODEL_CACHE=/models/huggingface \
    HF_HOME=/models/huggingface
