#!/usr/bin/env bash
# Phase 1 launcher skeleton for the v0.8 Project Intelligence Platform.
# Final one-click behaviour ships in Phase 9. This Phase 1 version:
#   1. verifies that docker or podman is available;
#   2. prepares the runtime volume directory;
#   3. starts the default "core-headless" profile via docker compose;
#   4. waits for the control-plane health check.
#
# Usage:
#   scripts/project-intelligence.sh start [--target <repo>]
#   scripts/project-intelligence.sh stop  [--target <repo>]
#   scripts/project-intelligence.sh status
#   scripts/project-intelligence.sh --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_REPO="$(pwd)"
COMPOSE_CMD=""
PROFILE="core-headless"
CMD="status"

log() { printf '[project-intelligence] %s\n' "$*" >&2; }
die() { printf '[project-intelligence] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

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
  fi
  return 1
}

ensure_target_repo() {
  TARGET_REPO="$(cd "$TARGET_REPO" && pwd)"
  PI_TARGET_REPO="$TARGET_REPO" \
  PI_CONTROL_PORT="${PI_CONTROL_PORT:-8765}" \
  PI_UI_PORT="${PI_UI_PORT:-8766}" \
  export PI_TARGET_REPO PI_CONTROL_PORT PI_UI_PORT
}

start() {
  detect_container_runtime || die "neither docker compose nor podman-compose is usable"
  ensure_target_repo
  log "using runtime: ${COMPOSE_CMD}"
  log "target repo:  ${TARGET_REPO}"
  log "profile:      ${PROFILE}"
  ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" up -d --build )
  log "waiting for health check on http://localhost:${PI_CONTROL_PORT:-8765}/health"
  for _ in $(seq 1 30); do
    if curl --silent --fail "http://localhost:${PI_CONTROL_PORT:-8765}/health" >/dev/null 2>&1; then
      log "platform is healthy"
      exit 0
    fi
    sleep 2
  done
  log "WARNING: health check did not respond within 60s; check 'docker compose logs'"
}

stop() {
  detect_container_runtime || die "neither docker compose nor podman-compose is usable"
  ensure_target_repo
  ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" down )
}

status() {
  detect_container_runtime || die "neither docker compose nor podman-compose is usable"
  ensure_target_repo
  ( cd "$PROJECT_ROOT" && $COMPOSE_CMD --profile "$PROFILE" ps )
}

if [ $# -eq 0 ]; then usage; fi
while [ $# -gt 0 ]; do
  case "$1" in
    start)  CMD=start; shift ;;
    stop)   CMD=stop; shift ;;
    status) CMD=status; shift ;;
    --target) TARGET_REPO="$2"; shift 2 ;;
    --help|-h) usage ;;
    *) die "unknown argument: $1" ;;
  esac
done

case "$CMD" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) die "unknown command: $CMD" ;;
esac