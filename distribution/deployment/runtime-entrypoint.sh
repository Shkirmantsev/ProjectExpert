#!/bin/sh
set -eu
# Backend discovery runs before setup on fresh hosts and needs no Python/models.
if [ "${1:-}" = --list-devices ]; then
  exec /app/llama-server "$@"
fi
# Reuse the pinned application's stdlib-only Python, prepared in the model volume.
# Retain CUDA/NVIDIA/library paths inherited from the runtime image.
export PYTHONHOME=/models/runtime-python
export LD_LIBRARY_PATH="${PYTHONHOME}/lib:${LD_LIBRARY_PATH:-}"
exec "${PYTHONHOME}/bin/python3" /control/runtime_supervisor.py "$@"
