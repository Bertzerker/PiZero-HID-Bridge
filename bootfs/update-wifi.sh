#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CREDENTIAL_FILE="${WIFI_CREDENTIAL_FILE:-$SCRIPT_DIR/wifi-credentials.txt}"
LOG_FILE="/var/log/bootfs-wifi-update.log"
DEFAULT_COUNTRY="DE"

log() {
  printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE"
}

fail() {
  log "ERROR: $*"
  exit 1
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

unquote() {
  local value
  value="$(trim "$1")"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

delete_credentials() {
  if [[ -f "$CREDENTIAL_FILE" ]]; then
    rm -f "$CREDENTIAL_FILE"
    log "Deleted credential file: $CREDENTIAL_FILE"
  fi
}

load_credentials() {
  WIFI_SSID=""
  WIFI_PASSWORD=""
  WIFI_COUNTRY="$DEFAULT_COUNTRY"
  WIFI_HIDDEN="false"

  [[ -f "$CREDENTIAL_FILE" ]] || exit 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="$(trim "$line")"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == *=* ]] || continue

    key="$(trim "${line%%=*}")"
    value="$(unquote "${line#*=}")"

    case "${key,,}" in
      ssid | wifi_ssid)
        WIFI_SSID="$value"
        ;;
      password | passphrase | psk | wifi_password)
        WIFI_PASSWORD="$value"
        ;;
      country | wifi_country)
        WIFI_COUNTRY="$value"
        ;;
      hidden | wifi_hidden)
        WIFI_HIDDEN="${value,,}"
        ;;
    esac
  done < "$CREDENTIAL_FILE"

  delete_credentials

  [[ -n "$WIFI_SSID" ]] || fail "SSID is missing in $CREDENTIAL_FILE"
}

configure_with_networkmanager() {
  local connection_name="bootfs-${WIFI_SSID}"

  log "Configuring Wi-Fi with NetworkManager for SSID: $WIFI_SSID"
  nmcli radio wifi on || true

  if nmcli -t -f NAME connection show | grep -Fxq "$connection_name"; then
    nmcli connection delete "$connection_name" >/dev/null
  fi

  nmcli connection add type wifi ifname wlan0 con-name "$connection_name" ssid "$WIFI_SSID" >/dev/null
  nmcli connection modify "$connection_name" connection.autoconnect yes

  if [[ "$WIFI_HIDDEN" == "true" || "$WIFI_HIDDEN" == "1" || "$WIFI_HIDDEN" == "yes" ]]; then
    nmcli connection modify "$connection_name" 802-11-wireless.hidden yes
  fi

  if [[ -n "$WIFI_PASSWORD" ]]; then
    nmcli connection modify "$connection_name" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$WIFI_PASSWORD"
  fi

  nmcli connection up "$connection_name" || true
}

escape_wpa_value() {
  python3 - "$1" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1]))
PY
}

configure_with_wpa_supplicant() {
  local config_file="/etc/wpa_supplicant/wpa_supplicant.conf"
  local ssid_json
  local password_json

  log "Configuring Wi-Fi with wpa_supplicant for SSID: $WIFI_SSID"
  mkdir -p "$(dirname "$config_file")"

  ssid_json="$(escape_wpa_value "$WIFI_SSID")"

  {
    echo "country=$WIFI_COUNTRY"
    echo "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev"
    echo "update_config=1"
    echo
    echo "network={"
    echo "    ssid=$ssid_json"
    if [[ -n "$WIFI_PASSWORD" ]]; then
      password_json="$(escape_wpa_value "$WIFI_PASSWORD")"
      echo "    psk=$password_json"
    else
      echo "    key_mgmt=NONE"
    fi
    if [[ "$WIFI_HIDDEN" == "true" || "$WIFI_HIDDEN" == "1" || "$WIFI_HIDDEN" == "yes" ]]; then
      echo "    scan_ssid=1"
    fi
    echo "}"
  } > "$config_file"

  chmod 600 "$config_file"
  rfkill unblock wifi 2>/dev/null || true
  systemctl restart wpa_supplicant 2>/dev/null || true
  systemctl restart dhcpcd 2>/dev/null || true
}

main() {
  if [[ "$(id -u)" -ne 0 ]]; then
    fail "Run as root."
  fi

  load_credentials

  if command -v nmcli >/dev/null 2>&1 && systemctl is-active --quiet NetworkManager 2>/dev/null; then
    configure_with_networkmanager
  else
    configure_with_wpa_supplicant
  fi

  log "Wi-Fi update completed."
}

main "$@"
