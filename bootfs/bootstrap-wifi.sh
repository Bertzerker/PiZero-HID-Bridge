#!/bin/bash
set -euo pipefail

BOOTFS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/bootfs-wifi-update.service"
MODE="${1:-}"

[[ "$(id -u)" -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
[[ -f "$BOOTFS_DIR/update-wifi.sh" ]] || {
  echo "Copy update-wifi.sh beside bootstrap-wifi.sh on bootfs." >&2
  exit 1
}
[[ -z "$MODE" || "$MODE" == "--install-only" ]] || {
  echo "Usage: bootstrap-wifi.sh [--install-only]" >&2
  exit 1
}

if [[ -z "$MODE" ]]; then
  [[ -f "$BOOTFS_DIR/cmdline.txt" ]] || {
    echo "cmdline.txt is missing beside bootstrap-wifi.sh." >&2
    exit 1
  }
fi

mkdir -p "$(dirname "$SERVICE_FILE")"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Apply Wi-Fi credentials from bootfs
RequiresMountsFor=$BOOTFS_DIR
After=local-fs.target NetworkManager.service wpa_supplicant.service
Before=network-online.target
Wants=NetworkManager.service wpa_supplicant.service
ConditionPathExists=$BOOTFS_DIR/wifi-credentials.txt

[Service]
Type=oneshot
ExecStart=/bin/bash $BOOTFS_DIR/update-wifi.sh
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bootfs-wifi-update.service

if [[ -z "$MODE" ]]; then
  # Only remove this bootstrap's arguments; keep the existing boot configuration.
  python3 - "$BOOTFS_DIR/cmdline.txt" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
options = (
    "systemd.run=/boot/firmware/bootstrap-wifi.sh",
    "systemd.run=/boot/bootstrap-wifi.sh",
    "systemd.run_success_action=reboot",
    "systemd.run_failure_action=none",
    "systemd.unit=kernel-command-line.target",
)
for option in options:
    text = re.sub(r"(?<!\S)" + re.escape(option) + r"(?!\S)", "", text)
path.write_text(text.strip() + "\n")
PY
  sync
  echo "Wi-Fi updater installed. The bootstrap boot options have been removed."
  echo "The next normal boot will apply and delete wifi-credentials.txt."
else
  echo "Wi-Fi updater installed. Put wifi-credentials.txt on $BOOTFS_DIR, then reboot."
fi
