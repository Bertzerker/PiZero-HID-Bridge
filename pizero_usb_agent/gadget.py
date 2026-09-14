from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


CONFIGFS = Path("/sys/kernel/config")
GADGET_ROOT = CONFIGFS / "usb_gadget" / "pizero_remote"
UDC_ROOT = Path("/sys/class/udc")

KEYBOARD_REPORT_DESCRIPTOR = bytes(
    [
        0x05,
        0x01,
        0x09,
        0x06,
        0xA1,
        0x01,
        0x05,
        0x07,
        0x19,
        0xE0,
        0x29,
        0xE7,
        0x15,
        0x00,
        0x25,
        0x01,
        0x75,
        0x01,
        0x95,
        0x08,
        0x81,
        0x02,
        0x95,
        0x01,
        0x75,
        0x08,
        0x81,
        0x01,
        0x95,
        0x06,
        0x75,
        0x08,
        0x15,
        0x00,
        0x25,
        0x65,
        0x05,
        0x07,
        0x19,
        0x00,
        0x29,
        0x65,
        0x81,
        0x00,
        0xC0,
    ]
)

MOUSE_REPORT_DESCRIPTOR = bytes(
    [
        0x05,
        0x01,
        0x09,
        0x02,
        0xA1,
        0x01,
        0x09,
        0x01,
        0xA1,
        0x00,
        0x05,
        0x09,
        0x19,
        0x01,
        0x29,
        0x03,
        0x15,
        0x00,
        0x25,
        0x01,
        0x95,
        0x03,
        0x75,
        0x01,
        0x81,
        0x02,
        0x95,
        0x01,
        0x75,
        0x05,
        0x81,
        0x01,
        0x05,
        0x01,
        0x09,
        0x30,
        0x09,
        0x31,
        0x09,
        0x38,
        0x15,
        0x81,
        0x25,
        0x7F,
        0x75,
        0x08,
        0x95,
        0x03,
        0x81,
        0x06,
        0xC0,
        0xC0,
    ]
)


class GadgetError(RuntimeError):
    pass


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="ascii")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii").strip()
    except OSError:
        return ""


def _write_text_if_changed(path: Path, value: str) -> None:
    if _read_text(path) == value:
        return
    try:
        _write_text(path, value)
    except OSError as exc:
        if exc.errno == 16 and path.exists():
            return
        raise


def _write_bytes_if_changed(path: Path, value: bytes) -> None:
    try:
        if path.read_bytes() == value:
            return
    except OSError:
        pass
    try:
        path.write_bytes(value)
    except OSError as exc:
        if exc.errno == 16 and path.exists():
            return
        raise


def _ensure_configfs_mounted() -> None:
    subprocess.run(["modprobe", "libcomposite"], check=False)
    if (CONFIGFS / "usb_gadget").exists():
        return
    CONFIGFS.mkdir(parents=True, exist_ok=True)
    subprocess.run(["mount", "-t", "configfs", "none", str(CONFIGFS)], check=True)
    if not (CONFIGFS / "usb_gadget").exists():
        raise GadgetError("USB gadget configfs is not available. libcomposite could not be loaded.")


def _first_udc() -> str:
    try:
        return next(path.name for path in sorted(UDC_ROOT.iterdir()) if path.is_dir() or path.is_symlink())
    except StopIteration as exc:
        raise GadgetError(
            "No USB Device Controller found. Check that dtoverlay=dwc2,dr_mode=peripheral is active, "
            "the Pi has been rebooted, and the cable is connected to the USB/OTG data port."
        ) from exc
    except OSError as exc:
        raise GadgetError(
            "The UDC directory is not readable. Check whether dwc2 is loaded in peripheral mode."
        ) from exc


def available_udcs() -> list[str]:
    try:
        return sorted(path.name for path in UDC_ROOT.iterdir() if path.is_dir() or path.is_symlink())
    except OSError:
        return []


def _bound_configfs_gadgets() -> list[str]:
    gadget_parent = CONFIGFS / "usb_gadget"
    if not gadget_parent.exists():
        return []
    bound: list[str] = []
    for gadget_path in sorted(gadget_parent.iterdir()):
        udc = _read_text(gadget_path / "UDC")
        if udc:
            bound.append(f"{gadget_path.name} ({udc})")
    return bound


def _symlink(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        return
    os.symlink(source, target)


def _setup_hid_function(
    function_path: Path,
    protocol: str,
    report_length: str,
    report_descriptor: bytes,
) -> None:
    function_path.mkdir(parents=True, exist_ok=True)
    _write_text_if_changed(function_path / "protocol", protocol)
    _write_text_if_changed(function_path / "subclass", "1")
    _write_text_if_changed(function_path / "report_length", report_length)
    _write_bytes_if_changed(function_path / "report_desc", report_descriptor)


def setup_gadget() -> None:
    _ensure_configfs_mounted()
    GADGET_ROOT.mkdir(parents=True, exist_ok=True)

    _write_text_if_changed(GADGET_ROOT / "idVendor", "0x1d6b")
    _write_text_if_changed(GADGET_ROOT / "idProduct", "0x0104")
    _write_text_if_changed(GADGET_ROOT / "bcdDevice", "0x0100")
    _write_text_if_changed(GADGET_ROOT / "bcdUSB", "0x0200")

    strings = GADGET_ROOT / "strings" / "0x409"
    strings.mkdir(parents=True, exist_ok=True)
    _write_text_if_changed(strings / "serialnumber", "pizero-remote-0001")
    _write_text_if_changed(strings / "manufacturer", "Raspberry Pi Zero 2 W")
    _write_text_if_changed(strings / "product", "Pi Zero Remote HID")

    config = GADGET_ROOT / "configs" / "c.1"
    config.mkdir(parents=True, exist_ok=True)
    _write_text_if_changed(config / "MaxPower", "250")
    config_strings = config / "strings" / "0x409"
    config_strings.mkdir(parents=True, exist_ok=True)
    _write_text_if_changed(config_strings / "configuration", "HID Keyboard and Mouse")

    keyboard = GADGET_ROOT / "functions" / "hid.usb0"
    _setup_hid_function(keyboard, "1", "8", KEYBOARD_REPORT_DESCRIPTOR)

    mouse = GADGET_ROOT / "functions" / "hid.usb1"
    _setup_hid_function(mouse, "2", "4", MOUSE_REPORT_DESCRIPTOR)

    _symlink(keyboard, config / "hid.usb0")
    _symlink(mouse, config / "hid.usb1")


def start_gadget() -> None:
    setup_gadget()
    udc_path = GADGET_ROOT / "UDC"
    current = udc_path.read_text(encoding="ascii").strip() if udc_path.exists() else ""
    if current:
        return
    try:
        _write_text(udc_path, _first_udc())
    except OSError as exc:
        if exc.errno == 16:
            bound = [name for name in _bound_configfs_gadgets() if not name.startswith("pizero_remote ")]
            suffix = f" Active configfs gadgets: {', '.join(bound)}." if bound else ""
            raise GadgetError(
                "The USB Device Controller is busy. Stop other USB gadget services or reboot the Pi."
                + suffix
            ) from exc
        raise


def reconnect_gadget() -> dict:
    before = gadget_status()
    stop_gadget()
    unbound = gadget_status()
    time.sleep(0.5)
    start_gadget()
    time.sleep(0.5)
    after = gadget_status()
    return {
        "before": before,
        "unbound": unbound,
        "after": after,
        "message": (
            f"USB reconnect completed: {before.get('udc_state') or 'unbound'} -> "
            f"{unbound.get('udc_state') or 'unbound'} -> {after.get('udc_state') or 'unknown'}."
        ),
    }


def force_reconnect_gadget() -> dict:
    result = reconnect_gadget()
    if result["after"].get("udc_state") == "not attached":
        result["message"] += (
            " The client is still not electrically connected to the USB gadget. "
            "Check the data cable, client USB port, Pi OTG port, and client VBUS power."
        )
    return result


def stop_gadget() -> None:
    udc_path = GADGET_ROOT / "UDC"
    if udc_path.exists():
        _write_text(udc_path, "")


def gadget_status() -> dict:
    udc = ""
    udc_state = ""
    if (GADGET_ROOT / "UDC").exists():
        try:
            udc = (GADGET_ROOT / "UDC").read_text(encoding="ascii").strip()
        except OSError:
            udc = ""
    if udc:
        udc_state = _read_text(UDC_ROOT / udc / "state")
    udcs = available_udcs()
    return {
        "configured": GADGET_ROOT.exists(),
        "bound": bool(udc),
        "active": bool(udc) and udc_state not in {"", "not attached"},
        "udc": udc,
        "udc_state": udc_state,
        "udc_available": bool(udcs),
        "available_udcs": udcs,
        "keyboard_device": "/dev/hidg0",
        "mouse_device": "/dev/hidg1",
        "keyboard_ready": Path("/dev/hidg0").exists(),
        "mouse_ready": Path("/dev/hidg1").exists(),
    }
