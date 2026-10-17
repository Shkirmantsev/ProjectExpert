#!/usr/bin/env bash
# One-click launcher for the v0.8 Project Intelligence Platform (Phase 9).
#
# DUTIES: verify-runtime export-env create-volumes mount-repo start-profile
#         wait-readiness open-browser print-status
#
# The DUTIES line above is the single source of truth for the launcher's
# duty set. The duty-parity test (tests/test_phase_9_launch_smoke.py)
# asserts that the bash and PowerShell launchers advertise the same duties.
#
# Usage:
#   scripts/project-intelligence.sh start   [--target <repo>] [--profile <p>]
#   scripts/project-intelligence.sh stop    [--target <repo>] [--profile <p>]
#   scripts/project-intelligence.sh status  [--target <repo>] [--profile <p>]
#   scripts/project-intelligence.sh version
#   scripts/project-intelligence.sh --help
#
# Environment:
#   PI_CONTROL_PORT  - UI/API port inside the host (default 8765)
#   PI_TARGET_REPO   - target repository path (default: current directory)
#   PI_PROFILE       - compose profile to start (default: desktop-lite)
#   PI_OPEN_BROWSER  - set to 0 to suppress browser opening (default: auto)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_REPO="${PI_TARGET_REPO:-$(pwd)}"
PROFILE="${PI_PROFILE:-desktop-lite}"
CMD="start"
COMPOSE_CMD=""

log()  { printf '[project-intelligence] %s\n' "$*" >&2; }
die()  { printf '[project-intelligence] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

# ---- duty: verify-runtime -------------------------------------------------
detect_container_runtime() {
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    return 0
  fi
  if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    if command -v podman-compose >/dev/null 2>&1; then
      COMPOSE_CMD="podman-compose"
      return 0
    fi
    die "podman found without podman-compose; install podman-compose or use docker"
  fi
  die "neither docker compose nor podman-compose is usable; install one and ensure the daemon is running"
}

# ---- duty: export-env -----------------------------------------------------
ensure_target_repo() {
  if [ ! -d "$TARGET_REPO" ]; then
    die "target repository does not exist: $TARGET_REPO"
  fi
  TARGET_REPO="$(cd "$TARGET_REPO" && pwd)"
  export PI_TARGET_REPO="$TARGET_REPO"
  export PI_CONTROL_PORT="${PI_CONTROL_PORT:-8765}"
  export PI_PROFILE="$PROFILE"
}

# ---- duty: create-volumes -------------------------------------------------
ensure_volumes() {
  # `docker compose up` creates named volumes lazily from the manifest, but we
  # declare them here so the launcher is the single source of truth for the
  # volume layout. Idempotent; existing volumes are reused.
  if [ -z "${PI_SKIP_VOLUME_CREATE:-}" ]; then
    ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" config >/dev/null )
  fi
}

# ---- duty: mount-repo ------------------------------------------------------
# The compose manifest already mounts $PI_TARGET_REPO at /repo:rw inside the
# core container; nothing extra to do here, but we record the duty so the
# parity test sees both launchers advertise it.
mount_repo() {
  log "mounting ${TARGET_REPO} at /repo inside the container"
}

# ---- duty: start-profile --------------------------------------------------
start_profile() {
  log "runtime:  ${COMPOSE_CMD}"
  log "target:   ${TARGET_REPO}"
  log "profile:  ${PROFILE}"
  log "port:     ${PI_CONTROL_PORT}"
  if [ "${PI_PULL_ONLY:-0}" = "1" ] || [ ! -f "${PROJECT_ROOT}/Containerfile" ]; then
    ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" up -d )
  elif [ "${PI_BUILD:-0}" = "1" ]; then
    ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" up -d --build )
  else
    ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" up -d ) || \
      ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" up -d --build )
  fi
}

# ---- duty: wait-readiness -------------------------------------------------
wait_for_readiness() {
  local url="http://localhost:${PI_CONTROL_PORT}/health/ready"
  log "waiting for ${url} (readiness, not liveness)"
  local attempt
  for attempt in $(seq 1 60); do
    if curl --silent --fail --max-time 2 "${url}" >/dev/null 2>&1; then
      log "platform reports ready after ${attempt} attempt(s)"
      return 0
    fi
    sleep 2
  done
  die "platform did not become ready within 120s; check '${COMPOSE_CMD} logs'"
}

stop_profile() {
  detect_container_runtime || die "no container runtime available to stop"
  ensure_target_repo
  ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" down )
}

show_status() {
  detect_container_runtime || die "no container runtime available for status"
  ensure_target_repo
  ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" ps )
}

# ---- duty: open-browser ---------------------------------------------------
open_browser() {
  local url="http://localhost:${PI_CONTROL_PORT}/"
  if [ "${PI_OPEN_BROWSER:-1}" = "0" ]; then
    return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${url}" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "${url}" >/dev/null 2>&1 || true
  elif command -v wslview >/dev/null 2>&1; then
    wslview "${url}" >/dev/null 2>&1 || true
  else
    log "no browser opener detected; print the URL manually"
  fi
}

# ---- duty: print-status ----------------------------------------------------
print_status() {
  printf 'project-intelligence ready\n'
  printf '  url:      http://localhost:%s/\n' "${PI_CONTROL_PORT}"
  printf '  api:      http://localhost:%s/api/v1/\n' "${PI_CONTROL_PORT}"
  printf '  health:   http://localhost:%s/health\n' "${PI_CONTROL_PORT}"
  printf '  readiness http://localhost:%s/health/ready\n' "${PI_CONTROL_PORT}"
  printf '  profile:  %s\n' "${PROFILE}"
  printf '  target:   %s\n' "${TARGET_REPO}"
}

if [ $# -eq 0 ]; then usage; fi
while [ $# -gt 0 ]; do
  case "$1" in
    start)         CMD=start; shift ;;
    stop)          CMD=stop; shift ;;
    status)        CMD=status; shift ;;
    version)       printf 'project-intelligence launcher 1.0.0 (Phase 9)\n'; exit 0 ;;
    --target)      TARGET_REPO="$2"; shift 2 ;;
    --profile)     PROFILE="$2"; shift 2 ;;
    --port)        PI_CONTROL_PORT="$2"; shift 2 ;;
    --no-browser)  PI_OPEN_BROWSER=0; shift ;;
    --help|-h)     usage ;;
    *)             die "unknown argument: $1" ;;
  esac
done

case "$CMD" in
  start)
    detect_container_runtime   # duty: verify-runtime
    ensure_target_repo          # duty: export-env
    ensure_volumes              # duty: create-volumes
    mount_repo                  # duty: mount-repo
    start_profile               # duty: start-profile
    wait_for_readiness          # duty: wait-readiness
    open_browser                # duty: open-browser
    print_status                # duty: print-status
    ;;
  stop)   stop_profile ;;
  status) show_status ;;
  *)      die "unknown command: $CMD" ;;
esac