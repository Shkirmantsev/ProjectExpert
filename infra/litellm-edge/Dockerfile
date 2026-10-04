FROM python:3.12-slim-bookworm
WORKDIR /app
COPY proxy.py .
USER 65532:65532
ENTRYPOINT ["python","/app/proxy.py"]
