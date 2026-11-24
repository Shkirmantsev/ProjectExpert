#!/usr/bin/env bash
# Print the effective browser URL of the deployed control plane.
#
# The port is resolved exactly the way Compose resolves it: the shell
# environment overrides deployment.env, and deployment.env is read as plain
# text -- it is never sourced or executed as shell code. The script needs
# neither Docker nor Python and never mutates the deployment.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

port="${PI_CONTROL_PORT:-}"
if [ -z "$port" ] && [ -f deployment.env ]; then
  port=$(sed -n 's/^PI_CONTROL_PORT=//p' deployment.env | tail -1)
fi
# Tolerate quoted or padded operator values.
port="${port//\"/}"
port="${port//\'/}"
port="${port//$'\r'/}"
port="${port//$'\t'/}"
port="${port// /}"
printf 'Service URL: http://localhost:%s\n' "${port:-8765}"

printf 'Index readiness: /health/ready (the service can start while indexing is pending)\n'

mode=${1:-}
if [ "$mode" = --open-if-enabled ] && [ "${PI_OPEN_BROWSER:-1}" = 0 ]; then
  exit 0
fi
case "$mode" in --open|--open-if-enabled) ;; *) exit 0 ;; esac
if ! command -v xdg-open >/dev/null 2>&1; then
  if [ "$mode" = --open ]; then echo 'No browser launcher available (xdg-open).' >&2; exit 1; fi
  exit 0
fi
# Ask the running topology for the real host port before sending a credential
# to a browser. Forwarding peers and user-supplied origins convey no authority.
if ! published=$(bash ./compose.sh port production 8765 2>/dev/null) ||
   ! [[ "$published" =~ ^(127\.0\.0\.1|\[::1\]):([0-9]{1,5})$ ]]; then
  if [ "$mode" = --open ]; then echo 'ProjectExpert is not published on a local loopback port.' >&2; exit 1; fi
  exit 0
fi
browser_url="http://localhost:${BASH_REMATCH[2]}/"
set +x
if ! key=$(bash ./compose.sh exec -T production python -m pi_platform.deployment.local_ui 2>/dev/null); then
  if [ "$mode" = --open ]; then echo 'Could not open the running ProjectExpert deployment.' >&2; exit 1; fi
  exit 0
fi
if [[ "$key" =~ ^[A-Za-z0-9_-]{43}$ ]]; then
  browser_url+="#local-owner=$key"
fi
xdg-open "$browser_url" >/dev/null 2>&1 || [ "$mode" = --open-if-enabled ]
