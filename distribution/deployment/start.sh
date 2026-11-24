#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
docker info >/dev/null || { echo 'Start Docker Engine or Docker Desktop first.' >&2; exit 1; }
bash ./compose.sh up -d --wait --wait-timeout "${PI_WAIT_TIMEOUT:-1800}"
# Open a browser through the same authorization path as the Make target.
bash ./url.sh --open-if-enabled
