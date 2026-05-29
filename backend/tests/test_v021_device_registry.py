from __future__ import annotations

import json
from pathlib import Path

from curator import device_registry


SYNCTHING_CONFIG = """
<configuration version="52">
  <device id="MACOS-DEVICE" name="MacOS">
    <address>dynamic</address>
  </device>
  <device id="LINUX-DEVICE" name="shin">
    <address>tcp://192.168.1.10:22000</address>
  </device>
  <folder id="nm6xn-urvs7" label="Second Brain" path="{vault}" type="sendreceive">
    <device id="MACOS-DEVICE" />
    <device id="LINUX-DEVICE" />
  </folder>
</configuration>
"""


def test_parse_syncthing_config_for_matching_vault(tmp_path: Path) -> None:
    vault = tmp_path / "second_brain"
    vault.mkdir()

    parsed = device_registry.parse_syncthing_config(
        SYNCTHING_CONFIG.format(vault=vault),
        vault,
    )

    assert parsed["folders"][0]["label"] == "Second Brain"
    assert {device["name"] for device in parsed["devices"]} == {"MacOS", "shin"}


def test_sync_device_registry_preserves_remote_device_profiles(tmp_path: Path) -> None:
    vault = tmp_path / "second_brain"
    curator_dir = vault / ".curator"
    curator_dir.mkdir(parents=True)
    config_path = tmp_path / "config.xml"
    config_path.write_text(SYNCTHING_CONFIG.format(vault=vault), encoding="utf-8")
    registry_path = vault / device_registry.REGISTRY_RELATIVE_PATH
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "devices": {
                    "MACOS-DEVICE": {
                        "device_id": "MACOS-DEVICE",
                        "name": "MacOS",
                        "backend": {"command": "/opt/homebrew/bin/uv", "args": ["run", "wiki", "mcp"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    registry = device_registry.sync_device_registry(
        vault,
        syncthing_config=config_path,
        backend_command="/usr/bin/wiki",
        backend_args=["mcp"],
    )

    assert registry["devices"]["MACOS-DEVICE"]["backend"]["command"] == "/opt/homebrew/bin/uv"
    local_id = registry["local_device_id"]
    assert registry["devices"][local_id]["backend"]["command"] == "/usr/bin/wiki"
    assert registry["syncthing"]["folders"][0]["id"] == "nm6xn-urvs7"


def test_parse_args_text_accepts_json_or_shell_style() -> None:
    assert device_registry.parse_args_text('["--directory", "/repo/backend", "run", "wiki", "mcp"]') == [
        "--directory",
        "/repo/backend",
        "run",
        "wiki",
        "mcp",
    ]
    assert device_registry.parse_args_text("--directory /repo/backend run wiki mcp") == [
        "--directory",
        "/repo/backend",
        "run",
        "wiki",
        "mcp",
    ]
