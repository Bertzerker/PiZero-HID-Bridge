from __future__ import annotations

import os
import select
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
SYN_REPORT = 0

REL_X = 0
REL_Y = 1
REL_WHEEL = 8

BTN_LEFT = 272
BTN_RIGHT = 273
BTN_MIDDLE = 274

EVENT_FORMAT = "@llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

MODIFIER_CODES = {
    29: 0x01,
    42: 0x02,
    56: 0x04,
    125: 0x08,
    97: 0x10,
    54: 0x20,
    100: 0x40,
    126: 0x80,
}

KEY_CODES = {
    1: 0x29,
    2: 0x1E,
    3: 0x1F,
    4: 0x20,
    5: 0x21,
    6: 0x22,
    7: 0x23,
    8: 0x24,
    9: 0x25,
    10: 0x26,
    11: 0x27,
    12: 0x2D,
    13: 0x2E,
    14: 0x2A,
    15: 0x2B,
    16: 0x14,
    17: 0x1A,
    18: 0x08,
    19: 0x15,
    20: 0x17,
    21: 0x1C,
    22: 0x18,
    23: 0x0C,
    24: 0x12,
    25: 0x13,
    26: 0x2F,
    27: 0x30,
    28: 0x28,
    30: 0x04,
    31: 0x16,
    32: 0x07,
    33: 0x09,
    34: 0x0A,
    35: 0x0B,
    36: 0x0D,
    37: 0x0E,
    38: 0x0F,
    39: 0x33,
    40: 0x34,
    41: 0x35,
    43: 0x31,
    44: 0x1D,
    45: 0x1B,
    46: 0x06,
    47: 0x19,
    48: 0x05,
    49: 0x11,
    50: 0x10,
    51: 0x36,
    52: 0x37,
    53: 0x38,
    57: 0x2C,
    58: 0x39,
    59: 0x3A,
    60: 0x3B,
    61: 0x3C,
    62: 0x3D,
    63: 0x3E,
    64: 0x3F,
    65: 0x40,
    66: 0x41,
    67: 0x42,
    68: 0x43,
    87: 0x44,
    88: 0x45,
    99: 0x46,
    102: 0x4A,
    103: 0x52,
    104: 0x4B,
    105: 0x50,
    106: 0x4F,
    107: 0x4D,
    108: 0x51,
    109: 0x4E,
    110: 0x49,
    111: 0x4C,
    119: 0x48,
}

NAMED_KEY_USAGES = {
    "escape": (0, 0x29),
    "tab": (0, 0x2B),
    "enter": (0, 0x28),
    "backspace": (0, 0x2A),
    "space": (0, 0x2C),
    "delete": (0, 0x4C),
    "home": (0, 0x4A),
    "end": (0, 0x4D),
    "pageup": (0, 0x4B),
    "pagedown": (0, 0x4E),
    "up": (0, 0x52),
    "down": (0, 0x51),
    "left": (0, 0x50),
    "right": (0, 0x4F),
    "f1": (0, 0x3A),
    "f2": (0, 0x3B),
    "f3": (0, 0x3C),
    "f4": (0, 0x3D),
    "f5": (0, 0x3E),
    "f6": (0, 0x3F),
    "f7": (0, 0x40),
    "f8": (0, 0x41),
    "f9": (0, 0x42),
    "f10": (0, 0x43),
    "f11": (0, 0x44),
    "f12": (0, 0x45),
}

CHAR_USAGES = {
    "a": (0, 0x04),
    "b": (0, 0x05),
    "c": (0, 0x06),
    "d": (0, 0x07),
    "e": (0, 0x08),
    "f": (0, 0x09),
    "g": (0, 0x0A),
    "h": (0, 0x0B),
    "i": (0, 0x0C),
    "j": (0, 0x0D),
    "k": (0, 0x0E),
    "l": (0, 0x0F),
    "m": (0, 0x10),
    "n": (0, 0x11),
    "o": (0, 0x12),
    "p": (0, 0x13),
    "q": (0, 0x14),
    "r": (0, 0x15),
    "s": (0, 0x16),
    "t": (0, 0x17),
    "u": (0, 0x18),
    "v": (0, 0x19),
    "w": (0, 0x1A),
    "x": (0, 0x1B),
    "y": (0, 0x1C),
    "z": (0, 0x1D),
    "A": (0x02, 0x04),
    "B": (0x02, 0x05),
    "C": (0x02, 0x06),
    "D": (0x02, 0x07),
    "E": (0x02, 0x08),
    "F": (0x02, 0x09),
    "G": (0x02, 0x0A),
    "H": (0x02, 0x0B),
    "I": (0x02, 0x0C),
    "J": (0x02, 0x0D),
    "K": (0x02, 0x0E),
    "L": (0x02, 0x0F),
    "M": (0x02, 0x10),
    "N": (0x02, 0x11),
    "O": (0x02, 0x12),
    "P": (0x02, 0x13),
    "Q": (0x02, 0x14),
    "R": (0x02, 0x15),
    "S": (0x02, 0x16),
    "T": (0x02, 0x17),
    "U": (0x02, 0x18),
    "V": (0x02, 0x19),
    "W": (0x02, 0x1A),
    "X": (0x02, 0x1B),
    "Y": (0x02, 0x1C),
    "Z": (0x02, 0x1D),
    "1": (0, 0x1E),
    "2": (0, 0x1F),
    "3": (0, 0x20),
    "4": (0, 0x21),
    "5": (0, 0x22),
    "6": (0, 0x23),
    "7": (0, 0x24),
    "8": (0, 0x25),
    "9": (0, 0x26),
    "0": (0, 0x27),
    "\n": (0, 0x28),
    "\t": (0, 0x2B),
    " ": (0, 0x2C),
    "-": (0, 0x2D),
    "=": (0, 0x2E),
    "[": (0, 0x2F),
    "]": (0, 0x30),
    "\\": (0, 0x31),
    ";": (0, 0x33),
    "'": (0, 0x34),
    "`": (0, 0x35),
    ",": (0, 0x36),
    ".": (0, 0x37),
    "/": (0, 0x38),
    "!": (0x02, 0x1E),
    "@": (0x02, 0x1F),
    "#": (0x02, 0x20),
    "$": (0x02, 0x21),
    "%": (0x02, 0x22),
    "^": (0x02, 0x23),
    "&": (0x02, 0x24),
    "*": (0x02, 0x25),
    "(": (0x02, 0x26),
    ")": (0x02, 0x27),
    "_": (0x02, 0x2D),
    "+": (0x02, 0x2E),
    "{": (0x02, 0x2F),
    "}": (0x02, 0x30),
    "|": (0x02, 0x31),
    ":": (0x02, 0x33),
    '"': (0x02, 0x34),
    "~": (0x02, 0x35),
    "<": (0x02, 0x36),
    ">": (0x02, 0x37),
    "?": (0x02, 0x38),
}


def _clamp_signed_byte(value: int) -> int:
    return max(-127, min(127, value))


def _signed_byte(value: int) -> int:
    return value & 0xFF


class HidWriteError(RuntimeError):
    pass


def _write_hid_report(path: str, report: bytes) -> None:
    deadline = time.monotonic() + 0.5
    last_error: Optional[OSError] = None

    while time.monotonic() < deadline:
        fd = -1
        try:
            fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, report)
            return
        except BlockingIOError as exc:
            last_error = exc
            time.sleep(0.02)
        except OSError as exc:
            last_error = exc
            break
        finally:
            if fd >= 0:
                os.close(fd)

    detail = f": {last_error}" if last_error else ""
    raise HidWriteError(f"{path} cannot be written. Is the client connected as a USB host and fully enumerated?{detail}")


def _keyboard_report(modifier: int, usage: int) -> bytes:
    return bytes([modifier, 0, usage, 0, 0, 0, 0, 0])


def send_key_usage(modifier: int, usage: int) -> None:
    _write_hid_report("/dev/hidg0", _keyboard_report(modifier, usage))
    _write_hid_report("/dev/hidg0", _keyboard_report(0, 0))


def send_named_key(name: str) -> None:
    key = name.strip().lower()
    if key not in NAMED_KEY_USAGES:
        raise HidWriteError(f"Unknown key: {name}")
    modifier, usage = NAMED_KEY_USAGES[key]
    send_key_usage(modifier, usage)


def send_text(text: str) -> dict:
    sent = 0
    skipped: list[str] = []
    for char in text:
        mapping = CHAR_USAGES.get(char)
        if not mapping:
            skipped.append(char)
            continue
        send_key_usage(*mapping)
        sent += 1
    return {"sent": sent, "skipped": skipped}


def send_test_key() -> None:
    send_key_usage(0, 0x04)


def send_test_mouse() -> None:
    send_mouse_report(40, 0, 0, 0)
    send_mouse_report(-40, 0, 0, 0)


def send_mouse_report(x: int, y: int, wheel: int = 0, buttons: int = 0) -> None:
    report = bytes(
        [
            buttons & 0xFF,
            _signed_byte(_clamp_signed_byte(x)),
            _signed_byte(_clamp_signed_byte(y)),
            _signed_byte(_clamp_signed_byte(wheel)),
        ]
    )
    _write_hid_report("/dev/hidg1", report)


def click_mouse(button: str) -> None:
    buttons = {"left": 0x01, "right": 0x02, "middle": 0x04}.get(button)
    if buttons is None:
        raise HidWriteError(f"Unknown mouse button: {button}")
    send_mouse_report(0, 0, 0, buttons)
    send_mouse_report(0, 0, 0, 0)


class HidWriter:
    def __init__(self, keyboard_path: str = "/dev/hidg0", mouse_path: str = "/dev/hidg1") -> None:
        self.keyboard_path = keyboard_path
        self.mouse_path = mouse_path
        self._keyboard = None
        self._mouse = None
        self._lock = threading.RLock()
        self.modifiers = 0
        self.keys: list[int] = []
        self.mouse_buttons = 0
        self.rel_x = 0
        self.rel_y = 0
        self.rel_wheel = 0

    def open(self) -> None:
        self._keyboard = open(self.keyboard_path, "wb", buffering=0)
        self._mouse = open(self.mouse_path, "wb", buffering=0)

    def close(self) -> None:
        for handle in (self._keyboard, self._mouse):
            if handle:
                try:
                    handle.close()
                except OSError:
                    pass

    def key_event(self, code: int, value: int) -> None:
        with self._lock:
            pressed = value != 0
            if code in MODIFIER_CODES:
                if pressed:
                    self.modifiers |= MODIFIER_CODES[code]
                else:
                    self.modifiers &= ~MODIFIER_CODES[code]
                self._write_keyboard()
                return

            usage = KEY_CODES.get(code)
            if not usage:
                return
            if pressed and usage not in self.keys:
                self.keys.append(usage)
            elif not pressed and usage in self.keys:
                self.keys.remove(usage)
            self._write_keyboard()

    def rel_event(self, code: int, value: int) -> None:
        with self._lock:
            if code == REL_X:
                self.rel_x += value
            elif code == REL_Y:
                self.rel_y += value
            elif code == REL_WHEEL:
                self.rel_wheel += value

    def mouse_button_event(self, code: int, value: int) -> bool:
        bit = {BTN_LEFT: 0x01, BTN_RIGHT: 0x02, BTN_MIDDLE: 0x04}.get(code)
        if bit is None:
            return False
        with self._lock:
            if value:
                self.mouse_buttons |= bit
            else:
                self.mouse_buttons &= ~bit
            self._write_mouse()
        return True

    def sync(self) -> None:
        with self._lock:
            if self.rel_x or self.rel_y or self.rel_wheel:
                self._write_mouse()
                self.rel_x = 0
                self.rel_y = 0
                self.rel_wheel = 0

    def _write_keyboard(self) -> None:
        if not self._keyboard:
            return
        report_keys = self.keys[:6]
        report = bytes([self.modifiers, 0, *report_keys, *([0] * (6 - len(report_keys)))])
        self._keyboard.write(report)

    def _write_mouse(self) -> None:
        if not self._mouse:
            return
        report = bytes(
            [
                self.mouse_buttons,
                _signed_byte(_clamp_signed_byte(self.rel_x)),
                _signed_byte(_clamp_signed_byte(self.rel_y)),
                _signed_byte(_clamp_signed_byte(self.rel_wheel)),
            ]
        )
        self._mouse.write(report)


class EventForwarder(threading.Thread):
    def __init__(self, event_path: str, writer: HidWriter, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self.event_path = event_path
        self.writer = writer
        self.stop_event = stop_event
        self.error = ""

    def run(self) -> None:
        try:
            fd = os.open(self.event_path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as exc:
            self.error = f"{self.event_path}: {exc}"
            return

        with os.fdopen(fd, "rb", buffering=0) as handle:
            while not self.stop_event.is_set():
                readable, _, _ = select.select([handle], [], [], 0.25)
                if not readable:
                    continue
                try:
                    data = handle.read(EVENT_SIZE)
                except OSError as exc:
                    self.error = f"{self.event_path}: {exc}"
                    return
                if not data or len(data) < EVENT_SIZE:
                    continue
                _, _, event_type, code, value = struct.unpack(EVENT_FORMAT, data)
                if event_type == EV_KEY:
                    if not self.writer.mouse_button_event(code, value):
                        self.writer.key_event(code, value)
                elif event_type == EV_REL:
                    self.writer.rel_event(code, value)
                elif event_type == EV_SYN and code == SYN_REPORT:
                    self.writer.sync()


@dataclass
class ForwardingSnapshot:
    running: bool
    event_paths: list[str]
    errors: list[str]


class ForwardingManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._threads: list[EventForwarder] = []
        self._writer: Optional[HidWriter] = None
        self._event_paths: list[str] = []

    def start(self, event_paths: list[str]) -> ForwardingSnapshot:
        with self._lock:
            self.stop()
            usable_paths = [path for path in event_paths if Path(path).exists()]
            if not usable_paths:
                raise RuntimeError("No forwardable /dev/input/event* devices selected.")
            self._stop_event = threading.Event()
            self._writer = HidWriter()
            self._writer.open()
            self._threads = [EventForwarder(path, self._writer, self._stop_event) for path in usable_paths]
            self._event_paths = usable_paths
            for thread in self._threads:
                thread.start()
            return self.snapshot()

    def stop(self) -> ForwardingSnapshot:
        with self._lock:
            self._stop_event.set()
            for thread in self._threads:
                thread.join(timeout=1.0)
            if self._writer:
                self._writer.close()
            self._threads = []
            self._writer = None
            self._event_paths = []
            return self.snapshot()

    def snapshot(self) -> ForwardingSnapshot:
        with self._lock:
            errors = [thread.error for thread in self._threads if thread.error]
            running = bool(self._threads) and any(thread.is_alive() for thread in self._threads)
            return ForwardingSnapshot(running=running, event_paths=list(self._event_paths), errors=errors)
