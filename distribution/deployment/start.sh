#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
docker info >/dev/null || { echo 'Start Docker Engine or Docker Desktop first.' >&2; exit 1; }
bash ./compose.sh up -d --wait --wait-timeout "${PI_WAIT_TIMEOUT:-1800}"
port="${PI_CONTROL_PORT:-$(sed -n 's/^PI_CONTROL_PORT=//p' deployment.env | tail -1)}"
url="http://localhost:${port:-8765}"
printf 'Ready: %s\n' "$url"
if [ "${PI_OPEN_BROWSER:-1}" != 0 ] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$url" >/dev/null 2>&1 || true
fi
