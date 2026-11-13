#!/usr/bin/env bash
# Read-only diagnostics. Host HTTPS is not proof of Docker daemon registry trust.
set -euo pipefail
image=${1:-}
[ -n "$image" ] || exit 0
context=$(docker context show 2>/dev/null || printf unknown)
printf 'Registry preflight: Docker context=%s\n' "$context"
if docker image inspect "$image" >/dev/null 2>&1; then
  echo 'Required asset image is cached; no registry HTTPS probe needed.'
  exit 0
fi
registry=${image%%/*}
# Only OCI registry hostnames, never credentials or arbitrary URL paths.
[[ "$registry" =~ ^[a-zA-Z0-9.-]+(:[0-9]+)?$ ]] || exit 0
echo 'Container host-trust bundles do not configure Docker Engine registry trust.'
if command -v curl >/dev/null 2>&1; then
  if ! curl --silent --show-error --output /dev/null --connect-timeout 5 --max-time 15 "https://$registry/v2/"; then
    echo 'Host registry HTTPS probe failed. Check proxy/CA policy; engine pull must also validate TLS.' >&2
  fi
fi
echo 'Linux rootful: /etc/docker/certs.d/<registry>/ca.crt; rootless: ${XDG_CONFIG_HOME:-~/.config}/docker/certs.d/<registry>/ca.crt.'
echo 'Docker Desktop: configure approved host CA trust. Rancher Desktop: configure the selected VM/engine trust separately.'
echo 'See https://docs.docker.com/engine/security/certificates/ . No trust settings were changed; the actual pull remains authoritative.'
