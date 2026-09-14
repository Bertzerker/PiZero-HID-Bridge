from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .gadget import GadgetError, force_reconnect_gadget, gadget_status, setup_gadget, start_gadget, stop_gadget
from .input_forwarder import (
    ForwardingManager,
    click_mouse,
    send_mouse_report,
    send_named_key,
    send_test_key,
    send_test_mouse,
    send_text,
)
from .state import StateStore
from .usb import UsbDevice, list_usb_devices


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = PROJECT_ROOT / "web"


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Agent:
    def __init__(self) -> None:
        self.state = StateStore()
        self.forwarding = ForwardingManager()

    def devices(self) -> list[UsbDevice]:
        return list_usb_devices()

    def _selectable_devices(self) -> list[UsbDevice]:
        return [device for device in self.devices() if device.capability == "hid_input"]

    def _prune_selection(self) -> set[str]:
        allowed = {device.sys_name for device in self._selectable_devices()}
        return self.state.prune_selected(allowed)

    def api_devices(self) -> dict:
        devices = self.devices()
        selected = self.state.prune_selected(
            {device.sys_name for device in devices if device.capability == "hid_input"}
        )
        return {
            "devices": [
                {
                    **device.as_dict(),
                    "selected": device.sys_name in selected,
                }
                for device in self.devices()
            ]
        }

    def api_status(self) -> dict:
        selected = self._prune_selection()
        current_gadget_status = gadget_status()
        if not current_gadget_status["active"]:
            self.forwarding.stop()
        snapshot = self.forwarding.snapshot()
        return {
            "gadget": current_gadget_status,
            "forwarding": {
                "running": snapshot.running,
                "event_paths": snapshot.event_paths,
                "errors": snapshot.errors,
            },
            "selected": sorted(selected),
        }

    def select_device(self, payload: dict) -> dict:
        sys_name = str(payload.get("sys_name", ""))
        if not sys_name:
            raise ApiError(400, "sys_name is missing.")
        selectable = {device.sys_name for device in self._selectable_devices()}
        if sys_name not in selectable:
            raise ApiError(400, "This device is not selectable.")
        enabled = bool(payload.get("enabled", False))
        selected = self.state.set_selected(sys_name, enabled)
        return {"selected": sorted(selected)}

    def start_forwarding(self) -> dict:
        current_gadget_status = gadget_status()
        if not current_gadget_status["active"]:
            raise ApiError(400, "The host port is not active. Enable the host port first.")
        if current_gadget_status.get("udc_state") == "not attached":
            raise ApiError(400, "The client is not connected to the USB gadget. UDC status: not attached.")
        if not current_gadget_status["keyboard_ready"] or not current_gadget_status["mouse_ready"]:
            raise ApiError(400, "HID devices /dev/hidg0 and /dev/hidg1 are not ready yet.")

        selected = self._prune_selection()
        event_paths: list[str] = []
        unsupported: list[str] = []
        for device in self.devices():
            if device.sys_name not in selected:
                continue
            if device.capability == "hid_input":
                event_paths.extend(event.path for event in device.forwardable_input_events)
            else:
                unsupported.append(device.display_name)

        if unsupported and not event_paths:
            raise ApiError(400, "The selected devices cannot be forwarded as HID devices.")
        snapshot = self.forwarding.start(sorted(set(event_paths)))
        return {
            "running": snapshot.running,
            "event_paths": snapshot.event_paths,
            "errors": snapshot.errors,
            "unsupported": unsupported,
        }


class RequestHandler(BaseHTTPRequestHandler):
    agent: Agent

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file() or WEB_ROOT not in path.resolve().parents:
            self.send_error(404)
            return
        content = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(400, "Invalid JSON.") from exc

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/devices":
                self._send_json(self.agent.api_devices())
                return
            if parsed.path == "/api/status":
                self._send_json(self.agent.api_status())
                return
            if parsed.path == "/":
                self._send_file(WEB_ROOT / "index.html")
                return
            if parsed.path.startswith("/static/"):
                relative = parsed.path.removeprefix("/static/")
                self._send_file((WEB_ROOT / relative).resolve())
                return
            self.send_error(404)
        except ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/select":
                self._send_json(self.agent.select_device(self._read_json()))
                return
            if parsed.path == "/api/gadget/setup":
                setup_gadget()
                self._send_json(self.agent.api_status())
                return
            if parsed.path == "/api/gadget/start":
                start_gadget()
                self._send_json(self.agent.api_status())
                return
            if parsed.path == "/api/gadget/reconnect":
                self.agent.forwarding.stop()
                result = force_reconnect_gadget()
                self._send_json({**self.agent.api_status(), "action": result})
                return
            if parsed.path == "/api/gadget/stop":
                self.agent.forwarding.stop()
                stop_gadget()
                self._send_json(self.agent.api_status())
                return
            if parsed.path == "/api/forward/start":
                self._send_json(self.agent.start_forwarding())
                return
            if parsed.path == "/api/forward/stop":
                snapshot = self.agent.forwarding.stop()
                self._send_json(
                    {
                        "running": snapshot.running,
                        "event_paths": snapshot.event_paths,
                        "errors": snapshot.errors,
                    }
                )
                return
            if parsed.path == "/api/test/key":
                send_test_key()
                self._send_json({"ok": True})
                return
            if parsed.path == "/api/test/mouse":
                send_test_mouse()
                self._send_json({"ok": True})
                return
            if parsed.path == "/api/virtual/type":
                result = send_text(str(self._read_json().get("text", "")))
                self._send_json({"ok": True, **result})
                return
            if parsed.path == "/api/virtual/key":
                send_named_key(str(self._read_json().get("key", "")))
                self._send_json({"ok": True})
                return
            if parsed.path == "/api/virtual/mouse":
                payload = self._read_json()
                send_mouse_report(
                    int(payload.get("x", 0)),
                    int(payload.get("y", 0)),
                    int(payload.get("wheel", 0)),
                    int(payload.get("buttons", 0)),
                )
                self._send_json({"ok": True})
                return
            if parsed.path == "/api/virtual/click":
                click_mouse(str(self._read_json().get("button", "left")))
                self._send_json({"ok": True})
                return
            self.send_error(404)
        except ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except (GadgetError, OSError, RuntimeError) as exc:
            self._send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)


def build_server(host: str, port: int) -> ThreadingHTTPServer:
    agent = Agent()

    class BoundRequestHandler(RequestHandler):
        pass

    BoundRequestHandler.agent = agent
    return ThreadingHTTPServer((host, port), BoundRequestHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pi Zero USB HID bridge agent")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = build_server(args.host, args.port)
    print(f"Pi Zero USB Agent running at http://{args.host}:{args.port}")
    server.serve_forever()
