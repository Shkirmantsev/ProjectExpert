#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
backend="${PI_ACCELERATOR:-$(sed -n 's/^PI_ACCELERATOR=//p' deployment.env | tail -1)}"
model="${PI_EMBEDDING_MODEL:-$(sed -n 's/^PI_EMBEDDING_MODEL=//p' deployment.env | tail -1)}"
backend="${backend:-cpu}"
model="${model:-qwen}"
case "$backend" in cpu|vulkan|cuda) ;; *) echo 'PI_ACCELERATOR must be cpu, vulkan or cuda' >&2; exit 2 ;; esac
case "$model" in gemma|gemma-gguf|qwen|qwen-gguf) ;; *) echo 'Select gemma, qwen, gemma-gguf or qwen-gguf' >&2; exit 2 ;; esac
files=(-f compose.yaml)
# Native CPU preserves the selected model. GPU selects its corresponding GGUF.
if [ "$backend" != cpu ] || [[ "$model" == *-gguf ]]; then
  export PI_ACCELERATOR="$backend"
  files+=(-f compose.accelerator.yaml -f "compose.$backend.yaml")
  if [[ "$model" == gemma* ]]; then files+=(-f compose.gemma-gguf.yaml); fi
else
  export PI_EMBEDDING_DEVICE=cpu
fi
exec docker compose --env-file deployment.env "${files[@]}" "$@"
