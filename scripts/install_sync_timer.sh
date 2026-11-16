#!/usr/bin/env bash
# Install a systemd user timer that runs the local corpus sync daily.
#
#   bash scripts/install_sync_timer.sh
#   systemctl --user list-timers hk-law-sync.timer
#   journalctl --user -u hk-law-sync.service -n 100
#
# Permission-gated case access is configured in ~/.config/hk-law-sync.env
# (mode 0600), not in the unit file. See docs/full-local-pipeline.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/hk-law-sync.env"
CALENDAR="${HK_LAW_SYNC_CALENDAR:-daily}"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found. Use cron instead:" >&2
  echo "  15 3 * * * $ROOT/scripts/sync.sh >> $HOME/.local/state/hk-law-sync.log 2>&1" >&2
  exit 1
fi

mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/hk-law-sync.service" <<EOF
[Unit]
Description=HK Criminal Law MCP local corpus sync
Documentation=file://$ROOT/docs/full-local-pipeline.md
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT
EnvironmentFile=-$ENV_FILE
ExecStart=$ROOT/scripts/sync.sh
TimeoutStartSec=6h
Nice=10
IOSchedulingClass=idle

[Install]
WantedBy=default.target
EOF

cat > "$UNIT_DIR/hk-law-sync.timer" <<EOF
[Unit]
Description=Daily HK Criminal Law MCP corpus sync

[Timer]
OnCalendar=$CALENDAR
Persistent=true
RandomizedDelaySec=30m
Unit=hk-law-sync.service

[Install]
WantedBy=timers.target
EOF

if [[ ! -f "$ENV_FILE" ]]; then
  umask 077
  cat > "$ENV_FILE" <<'EOF'
# Permission-gated case access only. Leave commented out until written
# permission is obtained and the scope matches docs/permission-request-template.md.
# HK_LAW_CASE_PERMISSION_REF=JUD-HKLII-YYYY-NNN
# HK_LAW_CASE_SOURCE=hklii
# HK_LAW_CASE_CITATIONS=/absolute/path/to/authorised-citations.txt
# HK_LAW_CASE_IMPORT_DIR=/absolute/path/to/authorised-judgment-export
# HK_LAW_CASE_SOURCE_URL=https://permitted.example/path
# HK_LAW_CASE_LICENSE=Private research — not for redistribution
EOF
fi

systemctl --user daemon-reload
systemctl --user enable --now hk-law-sync.timer

echo "Installed hk-law-sync.timer ($CALENDAR)."
echo "  Unit:    $UNIT_DIR/hk-law-sync.timer"
echo "  Env:     $ENV_FILE (mode 0600)"
echo "  Status:  systemctl --user status hk-law-sync.timer"
echo "  Logs:    journalctl --user -u hk-law-sync.service -n 100"
echo
echo "Run once now: $ROOT/scripts/sync.sh"
