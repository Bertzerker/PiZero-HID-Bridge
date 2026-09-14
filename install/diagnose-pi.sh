#!/usr/bin/env bash
set -u

BOOT_CONFIG="/boot/config.txt"
BOOT_CMDLINE="/boot/cmdline.txt"

if [[ -f /boot/firmware/config.txt ]]; then
  BOOT_CONFIG="/boot/firmware/config.txt"
fi

if [[ -f /boot/firmware/cmdline.txt ]]; then
  BOOT_CMDLINE="/boot/firmware/cmdline.txt"
fi

echo "Pi Zero USB Agent Diagnostics"
echo
echo "Boot config: $BOOT_CONFIG"
grep -nE 'pizero-usb-agent|dtoverlay=dwc2|otg_mode=1|\[all\]' "$BOOT_CONFIG" 2>/dev/null || true
echo
echo "Kernel cmdline: $BOOT_CMDLINE"
cat "$BOOT_CMDLINE" 2>/dev/null || true
echo
echo
echo "Loaded modules:"
lsmod | grep -E '^(dwc2|libcomposite)\b' || true
echo
echo "USB Device Controller:"
if [[ -d /sys/class/udc ]]; then
  find /sys/class/udc -maxdepth 1 -mindepth 1 -printf '%f\n' 2>/dev/null || true
  for udc in /sys/class/udc/*; do
    [[ -e "$udc/state" ]] || continue
    echo "$(basename "$udc") state: $(cat "$udc/state")"
  done
else
  echo "/sys/class/udc does not exist"
fi
echo
echo "USB role / VBUS hints:"
if compgen -G "/sys/class/usb_role/*" >/dev/null; then
  for role in /sys/class/usb_role/*; do
    echo "$(basename "$role") role: $(cat "$role/role" 2>/dev/null || true)"
  done
else
  echo "No usb_role interface found"
fi
find /sys/devices/platform -maxdepth 5 -type f \( -name role -o -name state -o -name vbus -o -name mode \) 2>/dev/null \
  | grep -Ei 'usb|dwc|otg' \
  | while read -r path; do
      echo "$path: $(cat "$path" 2>/dev/null || true)"
    done
echo
echo "HID Gadget Devices:"
ls -l /dev/hidg* 2>/dev/null || true
echo
echo "Configfs Gadget:"
if [[ -d /sys/kernel/config/usb_gadget/pizero_remote ]]; then
  echo "UDC: $(cat /sys/kernel/config/usb_gadget/pizero_remote/UDC 2>/dev/null || true)"
  echo "Product: $(cat /sys/kernel/config/usb_gadget/pizero_remote/strings/0x409/product 2>/dev/null || true)"
  find /sys/kernel/config/usb_gadget/pizero_remote/configs/c.1 -maxdepth 1 -type l -printf '%f -> %l\n' 2>/dev/null || true
else
  echo "pizero_remote is not set up"
fi
echo
echo "USB OTG/gadget dmesg hints:"
dmesg | grep -Ei 'dwc2|udc|gadget|otg' | tail -n 40 || true
