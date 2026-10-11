#!/usr/bin/env bash
set -euo pipefail

BOOTFS_DIR="/boot/firmware"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root: sudo bash install/install-bootfs-wifi-updater.sh"
  exit 1
fi

if [[ ! -d "$BOOTFS_DIR" ]]; then
  BOOTFS_DIR="/boot"
fi

install -m 0755 "$PROJECT_ROOT/bootfs/update-wifi.sh" "$BOOTFS_DIR/update-wifi.sh"
install -m 0755 "$PROJECT_ROOT/bootfs/bootstrap-wifi.sh" "$BOOTFS_DIR/bootstrap-wifi.sh"
install -m 0644 "$PROJECT_ROOT/bootfs/wifi-credentials.txt.template" "$BOOTFS_DIR/wifi-credentials.txt.template"
bash "$BOOTFS_DIR/bootstrap-wifi.sh" --install-only
