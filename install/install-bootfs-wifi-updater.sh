#!/usr/bin/env bash
set -euo pipefail

BOOTFS_DIR="/boot/firmware"
SERVICE_FILE="/etc/systemd/system/bootfs-wifi-update.service"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root: sudo bash install/install-bootfs-wifi-updater.sh"
  exit 1
fi

if [[ ! -d "$BOOTFS_DIR" ]]; then
  BOOTFS_DIR="/boot"
fi

install -m 0755 bootfs/update-wifi.sh "$BOOTFS_DIR/update-wifi.sh"
install -m 0644 bootfs/wifi-credentials.txt.template "$BOOTFS_DIR/wifi-credentials.txt.template"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Apply Wi-Fi credentials from bootfs
After=local-fs.target NetworkManager.service wpa_supplicant.service
Before=network-online.target
Wants=NetworkManager.service wpa_supplicant.service
ConditionPathExists=$BOOTFS_DIR/wifi-credentials.txt

[Service]
Type=oneshot
ExecStart=/usr/bin/env bash $BOOTFS_DIR/update-wifi.sh
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bootfs-wifi-update.service

echo "Installed bootfs Wi-Fi updater."
echo "Put wifi-credentials.txt on $BOOTFS_DIR, then reboot the Pi."
