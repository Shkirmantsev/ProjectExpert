#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
mkdir -p host-trust
for bundle in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem; do
  if [ -r "$bundle" ]; then
    temporary=$(mktemp host-trust/.ca-XXXXXX)
    trap 'rm -f "$temporary"' EXIT
    cp -- "$bundle" "$temporary"
    if grep -q 'PRIVATE KEY' "$temporary"; then echo 'Refusing private material in CA bundle' >&2; exit 1; fi
    chmod 644 "$temporary"
    mv -- "$temporary" host-trust/host-ca-bundle.pem
    exit 0
  fi
done
echo 'No host CA bundle found. Set up the host trust store or use PI_EXTRA_CA_BUNDLE.' >&2
exit 1
