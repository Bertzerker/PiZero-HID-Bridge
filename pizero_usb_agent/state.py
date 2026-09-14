from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock


DEFAULT_STATE_PATH = Path(os.environ.get("PIZERO_USB_STATE", "/var/lib/pizero-usb-agent/state.json"))


class StateStore:
    def __init__(self, path: Path = DEFAULT_STATE_PATH) -> None:
        self.path = path
        self._lock = RLock()
        self._data = {"selected": []}
        self._load()

    def _load(self) -> None:
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._data = {"selected": []}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        temporary_path.replace(self.path)

    def selected(self) -> set[str]:
        with self._lock:
            return set(self._data.get("selected", []))

    def set_selected(self, sys_name: str, enabled: bool) -> set[str]:
        with self._lock:
            selected = self.selected()
            if enabled:
                selected.add(sys_name)
            else:
                selected.discard(sys_name)
            self._data["selected"] = sorted(selected)
            self._save()
            return selected

    def prune_selected(self, allowed_sys_names: set[str]) -> set[str]:
        with self._lock:
            selected = self.selected()
            pruned = selected.intersection(allowed_sys_names)
            if pruned != selected:
                self._data["selected"] = sorted(pruned)
                self._save()
            return pruned
