#!/usr/bin/env bash
# Print the effective browser URL of the deployed control plane.
#
# The port is resolved exactly the way Compose resolves it: the shell
# environment overrides deployment.env, and deployment.env is read as plain
# text -- it is never sourced or executed as shell code. The script needs
# neither Docker nor Python and never mutates the deployment.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

read_setting() {
  local value=${!1:-}
  if [ -z "$value" ] && [ -f deployment.env ]; then
    value=$(sed -n "s/^$1=//p" deployment.env | tail -1)
  fi
  value=${value//\"/}
  value=${value//\'/}
  value=${value//$'\r'/}
  value=${value//$'\t'/}
  printf '%s' "${value// /}"
}

browser_host() {
  case "$1" in
    ''|0.0.0.0|127.0.0.1|::|::1|'[::]'|'[::1]') printf '%s' localhost ;;
    *) printf '%s' "$1" ;;
  esac
}

port=$(read_setting PI_CONTROL_PORT)
host=$(browser_host "$(read_setting PI_BIND_HOST)")
printf 'Service URL: http://%s:%s\n' "$host" "${port:-8765}"

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
# Use the actual published address, including explicit LAN bindings.
if ! published=$(bash ./compose.sh port production 8765 2>/dev/null) ||
   ! [[ "$published" =~ ^([0-9.]+|\[[0-9a-fA-F:]+\]):([0-9]{1,5})$ ]]; then
  if [ "$mode" = --open ]; then echo 'ProjectExpert has no published HTTP port.' >&2; exit 1; fi
  exit 0
fi
port=${BASH_REMATCH[2]}
host=$(browser_host "${BASH_REMATCH[1]}")
xdg-open "http://$host:$port/" >/dev/null 2>&1 || [ "$mode" = --open-if-enabled ]
