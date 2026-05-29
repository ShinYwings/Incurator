"""Syncthing-aware device registry for synced Incurator vaults."""

from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


REGISTRY_VERSION = 1
REGISTRY_RELATIVE_PATH = ".curator/devices.json"


def default_syncthing_config_paths() -> list[Path]:
    home = Path.home()
    return [
        home / ".local/state/syncthing/config.xml",
        home / ".config/syncthing/config.xml",
        home / "Library/Application Support/Syncthing/config.xml",
    ]


def find_syncthing_config() -> Path | None:
    for path in default_syncthing_config_paths():
        if path.exists():
            return path
    return None


def parse_args_text(value: str | None) -> list[str]:
    if not value:
        return []
    value = value.strip()
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    return shlex.split(value)


def _resolve_config_path(path_text: str) -> Path:
    return Path(os.path.expandvars(path_text)).expanduser().resolve(strict=False)


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except OSError:
        return a.resolve(strict=False) == b.resolve(strict=False)


def parse_syncthing_config(config_xml: str, vault_root: Path) -> dict[str, Any]:
    root = ET.fromstring(config_xml)
    vault_root = vault_root.resolve(strict=False)

    devices: dict[str, dict[str, Any]] = {}
    for node in root.findall("device"):
        device_id = node.attrib.get("id", "")
        if not device_id:
            continue
        devices[device_id] = {
            "device_id": device_id,
            "name": node.attrib.get("name") or device_id[:12],
            "addresses": [addr.text for addr in node.findall("address") if addr.text],
        }

    folders: list[dict[str, Any]] = []
    for folder in root.findall("folder"):
        folder_path_text = folder.attrib.get("path", "")
        if not folder_path_text:
            continue
        folder_path = _resolve_config_path(folder_path_text)
        if not _same_path(folder_path, vault_root):
            continue
        folders.append(
            {
                "id": folder.attrib.get("id", ""),
                "label": folder.attrib.get("label", ""),
                "path": folder_path_text,
                "type": folder.attrib.get("type", ""),
                "device_ids": [
                    node.attrib.get("id", "")
                    for node in folder.findall("device")
                    if node.attrib.get("id")
                ],
            }
        )

    folder_device_ids = {
        device_id
        for folder in folders
        for device_id in folder.get("device_ids", [])
    }
    return {
        "config_version": root.attrib.get("version"),
        "devices": [devices[d] for d in sorted(folder_device_ids) if d in devices],
        "folders": folders,
    }


def read_syncthing_status(config_path: Path, timeout: float = 0.25) -> dict[str, Any]:
    """Best-effort local Syncthing REST status.

    Returns an empty dict when Syncthing is not running or the GUI API is
    disabled. The static config parser remains the primary source.
    """

    try:
        root = ET.parse(config_path).getroot()
        gui = root.find("gui")
        if gui is None:
            return {}
        address = (gui.findtext("address") or "127.0.0.1:8384").strip()
        api_key = (gui.findtext("apikey") or "").strip()
        if not api_key:
            return {}
        scheme = "https" if gui.attrib.get("tls") == "true" else "http"
        if not address.startswith(("http://", "https://")):
            address = f"{scheme}://{address}"
        request = urllib.request.Request(
            f"{address.rstrip('/')}/rest/system/status",
            headers={"X-API-Key": api_key},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ET.ParseError):
        return {}


def infer_local_device_id(devices: list[dict[str, Any]], status: dict[str, Any]) -> str | None:
    status_id = status.get("myID")
    if isinstance(status_id, str) and status_id:
        return status_id

    hostnames = {
        socket.gethostname().lower(),
        socket.gethostname().split(".")[0].lower(),
        platform.node().lower(),
        platform.node().split(".")[0].lower(),
    }
    for device in devices:
        name = str(device.get("name", "")).lower()
        if name and name in hostnames:
            return str(device.get("device_id"))
    return None


def backend_launcher(command: str | None = None, args: list[str] | None = None) -> dict[str, Any]:
    backend_root = Path(__file__).resolve().parents[2]
    command = command or shutil.which("wiki") or "wiki"
    args = args if args else ["mcp"]
    return {
        "command": command,
        "args": args,
        "backend_root": str(backend_root),
        "uv_fallback": {
            "command": shutil.which("uv") or "uv",
            "args": ["--directory", str(backend_root), "run", "wiki", "mcp"],
        },
    }


def registry_path(vault_root: Path) -> Path:
    return vault_root / REGISTRY_RELATIVE_PATH


def load_registry(vault_root: Path) -> dict[str, Any]:
    path = registry_path(vault_root)
    if not path.exists():
        return {"version": REGISTRY_VERSION, "devices": {}, "syncthing": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": REGISTRY_VERSION, "devices": {}, "syncthing": {}}
    if not isinstance(data.get("devices"), dict):
        data["devices"] = {}
    if not isinstance(data.get("syncthing"), dict):
        data["syncthing"] = {}
    data["version"] = REGISTRY_VERSION
    return data


def write_registry(vault_root: Path, registry: dict[str, Any]) -> Path:
    path = registry_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sync_device_registry(
    vault_root: Path,
    *,
    syncthing_config: Path | None = None,
    backend_command: str | None = None,
    backend_args: list[str] | None = None,
) -> dict[str, Any]:
    config_path = syncthing_config or find_syncthing_config()
    syncthing: dict[str, Any] = {"devices": [], "folders": [], "config_path": None}
    status: dict[str, Any] = {}
    if config_path and config_path.exists():
        syncthing = parse_syncthing_config(config_path.read_text(encoding="utf-8"), vault_root)
        syncthing["config_path"] = str(config_path)
        status = read_syncthing_status(config_path)

    devices = syncthing.get("devices", [])
    local_device_id = infer_local_device_id(devices, status) or "local"
    now = int(time.time())

    registry = load_registry(vault_root)
    registry["syncthing"] = syncthing
    registry["updated_at"] = now
    registry["local_device_id"] = local_device_id

    known_devices = registry.setdefault("devices", {})
    for device in devices:
        device_id = str(device.get("device_id"))
        known_devices.setdefault(device_id, {})
        known_devices[device_id].update(
            {
                "device_id": device_id,
                "name": device.get("name") or device_id[:12],
                "syncthing": device,
            }
        )

    local_entry = known_devices.setdefault(local_device_id, {})
    local_entry.update(
        {
            "device_id": local_device_id,
            "name": local_entry.get("name")
            or next((d.get("name") for d in devices if d.get("device_id") == local_device_id), None)
            or socket.gethostname(),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python": sys.executable,
            },
            "backend": backend_launcher(backend_command, backend_args),
            "updated_at": now,
        }
    )

    write_registry(vault_root, registry)
    return registry
