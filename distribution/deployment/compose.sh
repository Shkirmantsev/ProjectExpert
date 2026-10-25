#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
backend="${PI_ACCELERATOR:-$(sed -n 's/^PI_ACCELERATOR=//p' deployment.env | tail -1)}"
model="${PI_EMBEDDING_MODEL:-$(sed -n 's/^PI_EMBEDDING_MODEL=//p' deployment.env | tail -1)}"
backend="${backend:-cpu}"
model="${model:-qwen-gguf}"
case "$backend" in cpu|vulkan|cuda) ;; *) echo 'PI_ACCELERATOR must be cpu, vulkan or cuda' >&2; exit 2 ;; esac
case "$model" in gemma|gemma-gguf|qwen|qwen-gguf) ;; *) echo 'Select gemma, qwen, gemma-gguf or qwen-gguf' >&2; exit 2 ;; esac
files=(-f compose.yaml)
# Native CPU preserves an explicit selection. Default Q4 also uses the sidecar.
if [ "$backend" != cpu ] || [[ "$model" == *-gguf ]]; then
  export PI_ACCELERATOR="$backend"
  files+=(-f compose.accelerator.yaml -f "compose.$backend.yaml")
  if [[ "$model" == gemma* ]]; then files+=(-f compose.gemma-gguf.yaml); fi
else
  export PI_EMBEDDING_DEVICE=cpu
fi
# Probe only for startup; config, logs, stop and CPU remain usable without a GPU.
if [ "$backend" != cpu ] && [[ " $* " == *" up "* ]]; then
  if [ "$backend" = vulkan ] && [ ! -d /dev/dri ]; then
    echo 'Vulkan requires /dev/dri on the Docker Engine host and vendor drivers. For Windows use start.ps1; for CPU set PI_ACCELERATOR=cpu.' >&2
    exit 2
  fi
  device="${PI_GPU_DEVICE:-$(sed -n 's/^PI_GPU_DEVICE=//p' deployment.env | tail -1)}"
  if [ -z "$device" ]; then
    if [ "$backend" = vulkan ]; then device=Vulkan0; else device=CUDA0; fi
  fi
  if ! probe=$(docker compose --env-file deployment.env "${files[@]}" run --rm --no-deps embeddings --list-devices 2>&1); then
    printf '%s\n' "$probe" >&2
    echo 'GPU preflight failed. Install Vulkan vendor drivers or NVIDIA Container Toolkit, or set PI_ACCELERATOR=cpu.' >&2
    exit 2
  fi
  if ! printf '%s\n' "$probe" | grep -Fq "$device:"; then
    printf '%s\n' "$probe" >&2
    printf 'Selected device %s is unavailable. Set PI_GPU_DEVICE to a listed device or PI_ACCELERATOR=cpu.\n' "$device" >&2
    exit 2
  fi
fi
exec docker compose --env-file deployment.env "${files[@]}" "$@"
