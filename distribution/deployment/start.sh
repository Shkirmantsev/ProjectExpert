#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
docker info >/dev/null || { echo 'Start Docker Engine or Docker Desktop first.' >&2; exit 1; }
bash ./compose.sh up -d --wait --wait-timeout "${PI_WAIT_TIMEOUT:-1800}"
# The readiness line is produced by the shared resolver, so the reported URL
# is the effective one (shell environment, then deployment.env, then default).
ready=$(bash ./url.sh)
printf '%s\n' "$ready"
if [ "${PI_OPEN_BROWSER:-1}" != 0 ] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${ready#Ready: }" >/dev/null 2>&1 || true
fi
