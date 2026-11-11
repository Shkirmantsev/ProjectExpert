#!/usr/bin/env bash
# Source this file from the kit launcher. Dotenv is data, never shell code.
workspace_value() {
  local line value=""
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    case "$line" in "$1="*) value=${line#*=} ;; esac
  done < deployment.env
  if [[ "$value" == \"*\" || "$value" == \'*\' ]]; then value=${value:1:${#value}-2}; fi
  printf '%s' "$value"
}
workspace_mode=${PI_WORKSPACE_MODE:-$(workspace_value PI_WORKSPACE_MODE)}
case "${workspace_mode:-auto}" in auto|bind) workspace_managed=0 ;; volume) workspace_managed=1 ;; *) echo 'PI_WORKSPACE_MODE must be auto, bind or volume' >&2; return 2 ;; esac
workspace_repo=${PI_TARGET_REPO:-$(workspace_value PI_TARGET_REPO)}
if [ "$workspace_managed" = 1 ]; then workspace_repo=$(cd -- "${workspace_repo:-..}" && pwd -P); fi
# Only documented helper settings cross the data/command boundary.
if [ "$workspace_managed" = 1 ]; then
  for workspace_key in PI_WORKSPACE_EXCLUDE PI_WORKSPACE_MAX_FILE_BYTES PI_RUNTIME_BACKUP PI_RUNTIME_BACKUP_DIR PI_RUNTIME_BACKUP_INTERVAL_MINUTES PI_RUNTIME_BACKUP_INTERVAL_SECONDS PI_WORKSPACE_DEBOUNCE_MS PI_WORKSPACE_VERIFY_INTERVAL_SECONDS; do
    if [ -z "${!workspace_key:-}" ]; then
      workspace_setting=$(workspace_value "$workspace_key")
      if [ -n "$workspace_setting" ]; then export "$workspace_key=$workspace_setting"; fi
    fi
  done
fi
workspace_kit=$PWD
workspace_agent() {
  local binary=workspace-agent-linux-amd64 expected actual
  expected=$(awk -v name="$binary" '$2 == name || $2 == "*" name {print $1}' workspace-agent-SHA256SUMS)
  [ ${#expected} = 64 ] || { echo 'Missing workspace helper checksum' >&2; return 2; }
  actual=$(sha256sum "$binary"); actual=${actual%% *}
  [ "$actual" = "$expected" ] || { echo 'Workspace helper checksum mismatch' >&2; return 2; }
  chmod u+x "$binary"
  "./$binary" "$1" --repo "$workspace_repo" --kit "$workspace_kit"
}
workspace_before() {
  [ "$workspace_managed" = 1 ] || return 0
  case " $* " in
    *" up "*|*" run "*|*" restart "*) workspace_agent prepare; workspace_agent sync ;;
    *" down "*) workspace_agent backup || echo "Warning: workspace backup failed" >&2; workspace_agent stop ;;
    *" stop "*) workspace_agent stop ;;
  esac
  case " $* " in
    *" up "*|*" restart "*) (workspace_agent supervise >>workspace-agent.log 2>&1 </dev/null &);;
  esac
}
workspace_compose() {
  if [ "$workspace_managed" != 1 ]; then docker compose "$@"; return; fi
  local leading=() arg context
  context=$(workspace_agent context) || return
  [ -n "$context" ] || { echo "Missing pinned Docker context" >&2; return 2; }
  while [ "$#" -gt 0 ]; do
    arg=$1; shift
    case "$arg" in
      up|run|restart|config|ps|logs|down|stop|start|exec|pull|build|images|top|version|ls|events|pause|unpause|kill|rm|create|cp|port|wait|watch)
        docker --context "$context" compose "${leading[@]}" --env-file workspace.env -f compose.workspace-volume.yaml "$arg" "$@"; return ;;
      *) leading+=("$arg") ;;
    esac
  done
  docker --context "$context" compose "${leading[@]}" --env-file workspace.env -f compose.workspace-volume.yaml
}
