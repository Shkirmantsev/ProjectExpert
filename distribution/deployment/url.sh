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
printf 'Ready: http://localhost:%s\n' "${port:-8765}"
