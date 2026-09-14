from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


USB_SYSFS = Path("/sys/bus/usb/devices")
INPUT_SYSFS = Path("/sys/class/input")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


@dataclass
class UsbInterface:
    name: str
    interface_class: str
    interface_subclass: str
    interface_protocol: str

    @property
    def is_hid(self) -> bool:
        return self.interface_class.lower() == "03"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "class": self.interface_class,
            "subclass": self.interface_subclass,
            "protocol": self.interface_protocol,
            "is_hid": self.is_hid,
        }


@dataclass
class InputEvent:
    path: str
    name: str
    kind: str
    forwardable: bool

    @property
    def label(self) -> str:
        if self.kind == "keyboard":
            return "Keyboard"
        if self.kind == "mouse":
            return "Mouse"
        if self.kind == "consumer":
            return "Sondertasten"
        return "Sonstiger HID-Kanal"

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "kind": self.kind,
            "label": self.label,
            "forwardable": self.forwardable,
        }


@dataclass
class UsbDevice:
    sys_name: str
    vendor_id: str
    product_id: str
    manufacturer: str
    product: str
    serial: str
    busnum: str
    devnum: str
    speed: str
    device_class: str
    interfaces: list[UsbInterface] = field(default_factory=list)
    input_events: list[InputEvent] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        parts = [self.manufacturer, self.product]
        name = " ".join(part for part in parts if part).strip()
        return name or f"USB {self.vendor_id}:{self.product_id}"

    @property
    def is_hid_input(self) -> bool:
        return bool(self.forwardable_input_events) and any(interface.is_hid for interface in self.interfaces)

    @property
    def forwardable_input_events(self) -> list[InputEvent]:
        return [event for event in self.input_events if event.forwardable]

    @property
    def capability(self) -> str:
        if self.is_hid_input:
            return "hid_input"
        return "unsupported"

    @property
    def capability_label(self) -> str:
        if self.capability == "hid_input":
            return "Keyboard/mouse forwarding available"
        return "Nur Erkennung, keine physische Durchleitung"

    def as_dict(self) -> dict:
        return {
            "sys_name": self.sys_name,
            "name": self.display_name,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "manufacturer": self.manufacturer,
            "product": self.product,
            "serial": self.serial,
            "busnum": self.busnum,
            "devnum": self.devnum,
            "speed": self.speed,
            "device_class": self.device_class,
            "interfaces": [interface.as_dict() for interface in self.interfaces],
            "input_events": [event.path for event in self.input_events],
            "input_channels": [event.as_dict() for event in self.input_events],
            "forwardable_input_events": [event.path for event in self.forwardable_input_events],
            "capability": self.capability,
            "capability_label": self.capability_label,
        }


def _capability_bits(text: str) -> set[int]:
    parts = [part for part in text.split() if part]
    if not parts:
        return set()

    bits: set[int] = set()
    bits_per_word = 64 if any(len(part) > 8 for part in parts) else 32
    for word_index, part in enumerate(reversed(parts)):
        try:
            value = int(part, 16)
        except ValueError:
            continue
        bit_index = 0
        while value:
            if value & 1:
                bits.add(word_index * bits_per_word + bit_index)
            value >>= 1
            bit_index += 1
    return bits


def _event_kind(event_path: Path) -> str:
    device_path = event_path / "device"
    name = _read_text(device_path / "name").lower()
    phys = _read_text(device_path / "phys").lower()
    ev_bits = _capability_bits(_read_text(device_path / "capabilities" / "ev"))
    key_bits = _capability_bits(_read_text(device_path / "capabilities" / "key"))
    rel_bits = _capability_bits(_read_text(device_path / "capabilities" / "rel"))

    has_mouse_axes = 2 in ev_bits and ({0, 1} <= rel_bits)
    has_mouse_buttons = bool({272, 273, 274}.intersection(key_bits))
    has_keyboard_keys = bool({1, 14, 15, 28, 30, 31, 32, 33, 34, 35, 36, 57}.intersection(key_bits))
    has_letter_keys = bool(set(range(16, 26)).intersection(key_bits) or set(range(30, 39)).intersection(key_bits))

    if "keyboard" in name or "kbd" in phys or (has_keyboard_keys and has_letter_keys):
        return "keyboard"

    if "mouse" in name or "mouse" in phys or (has_mouse_axes and has_mouse_buttons):
        return "mouse"

    if "consumer" in name or "control" in name:
        return "consumer"

    return "other"


def _input_event(event_path: Path) -> InputEvent:
    kind = _event_kind(event_path)
    return InputEvent(
        path=f"/dev/input/{event_path.name}",
        name=_read_text(event_path / "device" / "name"),
        kind=kind,
        forwardable=kind in {"keyboard", "mouse"},
    )


def _device_input_events(device_path: Path) -> list[InputEvent]:
    event_names: set[str] = set()
    for event_path in device_path.rglob("event*"):
        if event_path.is_dir() and event_path.name.startswith("event"):
            event_names.add(event_path.name)

    try:
        resolved_device_path = device_path.resolve()
    except OSError:
        return sorted(event_names)

    if INPUT_SYSFS.exists():
        for event_path in INPUT_SYSFS.glob("event*"):
            if not event_path.name.removeprefix("event").isdigit():
                continue
            try:
                event_device_path = (event_path / "device").resolve()
                event_device_path.relative_to(resolved_device_path)
            except (OSError, ValueError):
                continue
            event_names.add(event_path.name)

    events: list[InputEvent] = []
    for event_name in sorted(event_names):
        sysfs_event_path = INPUT_SYSFS / event_name
        if sysfs_event_path.exists():
            events.append(_input_event(sysfs_event_path))
        else:
            events.append(InputEvent(path=f"/dev/input/{event_name}", name="", kind="other", forwardable=False))
    return events


def _device_interfaces(device_path: Path) -> list[UsbInterface]:
    interfaces: list[UsbInterface] = []
    for interface_path in sorted(device_path.glob("*:*")):
        if not interface_path.is_dir():
            continue
        interface_class = _read_text(interface_path / "bInterfaceClass")
        if not interface_class:
            continue
        interfaces.append(
            UsbInterface(
                name=interface_path.name,
                interface_class=interface_class,
                interface_subclass=_read_text(interface_path / "bInterfaceSubClass"),
                interface_protocol=_read_text(interface_path / "bInterfaceProtocol"),
            )
        )
    return interfaces


def _is_internal_usb_device(
    vendor_id: str,
    product_id: str,
    product: str,
    device_class: str,
) -> bool:
    product_name = product.lower()
    is_linux_root_hub = vendor_id.lower() == "1d6b" and product_id.lower() in {"0002", "0003"}
    is_hub_class = device_class.lower() == "09"
    is_virtual_controller = "dwc otg controller" in product_name or "usb/ip virtual host controller" in product_name
    return (is_linux_root_hub and is_hub_class) or is_virtual_controller


def list_usb_devices(sysfs_root: Path = USB_SYSFS) -> list[UsbDevice]:
    devices: list[UsbDevice] = []
    if not sysfs_root.exists():
        return devices

    for device_path in sorted(sysfs_root.iterdir(), key=lambda item: item.name):
        if not device_path.is_dir():
            continue
        vendor_id = _read_text(device_path / "idVendor")
        product_id = _read_text(device_path / "idProduct")
        if not vendor_id or not product_id:
            continue
        product = _read_text(device_path / "product")
        device_class = _read_text(device_path / "bDeviceClass")
        if _is_internal_usb_device(vendor_id, product_id, product, device_class):
            continue

        devices.append(
            UsbDevice(
                sys_name=device_path.name,
                vendor_id=vendor_id,
                product_id=product_id,
                manufacturer=_read_text(device_path / "manufacturer"),
                product=product,
                serial=_read_text(device_path / "serial"),
                busnum=_read_text(device_path / "busnum"),
                devnum=_read_text(device_path / "devnum"),
                speed=_read_text(device_path / "speed"),
                device_class=device_class,
                interfaces=_device_interfaces(device_path),
                input_events=_device_input_events(device_path),
            )
        )

    return devices
