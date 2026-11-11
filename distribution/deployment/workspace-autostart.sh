#!/usr/bin/env bash
# Explicit opt-in only. Default launcher supervision lasts for this login session.
set -euo pipefail
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
unit="projectexpert-workspace-$(printf '%s' "$kit" | sha256sum | cut -c1-16).service"
case "${1:-}" in
  install)
    # Reject systemd syntax metacharacters rather than generate an ambiguous unit.
    [[ "$kit" != *[\"\\\$%$'\n'$'\r']* ]] || { echo 'Unsupported kit path for systemd unit' >&2; exit 2; }
    mkdir -p "$HOME/.config/systemd/user"
    cat > "$HOME/.config/systemd/user/$unit" <<EOF
[Unit]
Description=ProjectExpert managed workspace supervisor
[Service]
WorkingDirectory=$kit
ExecStart=/bin/bash "$kit/workspace-autostart.sh" supervise
Restart=on-failure
RestartSec=30
[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now $unit
    ;;
  supervise) cd -- "$kit"; source ./workspace.sh; [ "$workspace_managed" = 1 ]; workspace_agent supervise ;;
  uninstall) systemctl --user disable --now $unit; rm -f "$HOME/.config/systemd/user/$unit"; systemctl --user daemon-reload ;;
  *) echo 'Usage: bash workspace-autostart.sh install|uninstall|supervise (explicit per-user opt-in)' >&2; exit 2 ;;
esac
