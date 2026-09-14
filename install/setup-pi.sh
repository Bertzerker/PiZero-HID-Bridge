#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/pizero-usb-agent"
SERVICE_FILE="/etc/systemd/system/pizero-usb-agent.service"
BOOT_CONFIG="/boot/config.txt"
BOOT_CMDLINE="/boot/cmdline.txt"
MODULES_LOAD_FILE="/etc/modules-load.d/pizero-usb-agent.conf"
MODPROBE_FILE="/etc/modprobe.d/pizero-usb-agent.conf"
CONFIG_BEGIN="# BEGIN pizero-usb-agent"
CONFIG_END="# END pizero-usb-agent"

ensure_cmdline_module() {
  local module="$1"
  local current
  local modules
  local replacement

  current="$(grep -o 'modules-load=[^ ]*' "$BOOT_CMDLINE" | head -n 1 || true)"
  if [[ -z "$current" ]]; then
    sed -i "1 s/$/ modules-load=$module/" "$BOOT_CMDLINE"
    return
  fi

  modules="${current#modules-load=}"
  if [[ ",$modules," == *",$module,"* ]]; then
    return
  fi

  replacement="modules-load=$modules,$module"
  sed -i "0,/$current/s//$replacement/" "$BOOT_CMDLINE"
}

ensure_boot_config_block() {
  local tmp_file
  tmp_file="$(mktemp)"

  sed "/^$CONFIG_BEGIN$/,/^$CONFIG_END$/d" "$BOOT_CONFIG" > "$tmp_file"
  cat >> "$tmp_file" <<EOF

$CONFIG_BEGIN
[all]
dtoverlay=dwc2,dr_mode=peripheral
$CONFIG_END
EOF
  cp "$tmp_file" "$BOOT_CONFIG"
  rm -f "$tmp_file"
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root: sudo bash install/setup-pi.sh"
  exit 1
fi

apt-get update
apt-get install -y python3

mkdir -p "$PROJECT_DIR" /var/lib/pizero-usb-agent
cp -r pizero_usb_agent web "$PROJECT_DIR/"
cp install/pizero-usb-agent.service "$SERVICE_FILE"

if [[ -f /boot/firmware/config.txt ]]; then
  BOOT_CONFIG="/boot/firmware/config.txt"
fi

if [[ -f /boot/firmware/cmdline.txt ]]; then
  BOOT_CMDLINE="/boot/firmware/cmdline.txt"
fi

sed -i '/^otg_mode=1/s/^/# disabled by pizero-usb-agent: /' "$BOOT_CONFIG"
sed -i '/^dtoverlay=dwc2/s/^/# replaced by pizero-usb-agent: /' "$BOOT_CONFIG"
ensure_boot_config_block

ensure_cmdline_module "dwc2"
ensure_cmdline_module "libcomposite"

cat > "$MODULES_LOAD_FILE" <<EOF
dwc2
libcomposite
EOF

cat > "$MODPROBE_FILE" <<EOF
options dwc2 dr_mode=peripheral
EOF

systemctl daemon-reload
systemctl enable pizero-usb-agent.service

echo "Installed. Please reboot. The web interface will then be available on port 8080."
