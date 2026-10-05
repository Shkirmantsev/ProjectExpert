# Base image pinned by digest (sha256:...) for reproducible builds;
# the `python:3.12-slim-bookworm` mutable tag would silently pull
# whatever the Docker Hub maintainers published today vs. next week.
FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
WORKDIR /app
COPY proxy.py .
USER 65532:65532
ENTRYPOINT ["python","/app/proxy.py"]