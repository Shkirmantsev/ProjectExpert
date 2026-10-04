# syntax=docker/dockerfile:1.7
# Phase 1 skeleton for the v0.8 Project Intelligence Platform container.
# Final image behaviour ships in Phase 9 (one-click launcher); this image
# installs the platform Python package, copies the documented stub
# license/SBOM artifacts and exposes the control-plane port (default 8765).
#
# Build:  docker build -t project-intelligence:dev .
# Run:    docker run --rm -p 8765:8765 \
#               -v "$(pwd):/repo" \
#               project-intelligence:dev --help
FROM python:3.11-slim AS runtime

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

# Phase 1 ships the platform package itself; later phases copy additional
# adapters (ingest parsers, embeddings, control-plane web assets).
COPY pi_platform ./pi_platform
COPY pyproject.toml ./pyproject.toml
COPY README.md ./README.md
COPY distribution/licenses ./distribution/licenses
COPY distribution/sbom ./distribution/sbom

RUN pip install --no-cache-dir .
# Java native libraries remain optional: install the approved java extra in a
# derived image to enable the isolated parser. Default uses metadata-only mode.

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -m pi_platform.cli health || exit 1

ENTRYPOINT ["python", "-m", "pi_platform.cli"]
CMD ["--help"]