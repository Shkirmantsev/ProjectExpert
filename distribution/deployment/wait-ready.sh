#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# Executes in the existing application; the ordinary start waits for liveness.
exec bash ./compose.sh exec -T production python -c '
import os, time, urllib.request
end = time.monotonic() + int(os.environ.get("PI_READY_TIMEOUT", "1800"))
while True:
    try:
        urllib.request.urlopen("http://127.0.0.1:8765/health/ready", timeout=4).close()
        break
    except OSError:
        if time.monotonic() >= end:
            raise SystemExit("Index readiness timed out; inspect indexing status and application logs")
        time.sleep(2)
'
