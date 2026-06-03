from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

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

SYNCTHING_CONFIG_WITH_ZOTERO = """
<configuration version="52">
  <device id="MACOS-DEVICE" name="MacOS">
    <address>dynamic</address>
  </device>
  <device id="LINUX-DEVICE" name="shin">
    <address>tcp://192.168.1.10:22000</address>
  </device>
  <folder id="vault-folder" label="Second Brain" path="{vault}" type="sendreceive">
    <device id="MACOS-DEVICE" />
    <device id="LINUX-DEVICE" />
  </folder>
  <folder id="zotero-folder" label="Zotero" path="{zotero}" type="sendreceive">
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
    assert parsed["folders"][0]["role"] == "vault"
    assert {device["name"] for device in parsed["devices"]} == {"MacOS", "shin"}


def test_parse_syncthing_config_maps_vault_and_zotero_folders(tmp_path: Path) -> None:
    vault = tmp_path / "second_brain"
    zotero = tmp_path / "Zotero"
    vault.mkdir()
    zotero.mkdir()

    parsed = device_registry.parse_syncthing_config(
        SYNCTHING_CONFIG_WITH_ZOTERO.format(vault=vault, zotero=zotero),
        vault,
        zotero_roots=[zotero],
    )

    roles = {folder["label"]: folder["role"] for folder in parsed["folders"]}
    assert roles == {"Second Brain": "vault", "Zotero": "zotero"}
    for folder in parsed["folders"]:
        assert set(folder["device_ids"]) == {"MACOS-DEVICE", "LINUX-DEVICE"}


def test_sync_device_registry_preserves_remote_device_profiles(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setattr(
        device_registry,
        "read_syncthing_status",
        lambda _config_path: {"myID": "LINUX-DEVICE"},
    )

    registry = device_registry.sync_device_registry(
        vault,
        syncthing_config=config_path,
        backend_command="/usr/bin/wiki",
        backend_args=[],
    )

    assert registry["devices"]["MACOS-DEVICE"]["backend"]["command"] == "/opt/homebrew/bin/uv"
    local_id = registry["local_device_id"]
    assert registry["devices"][local_id]["backend"]["command"] == "/usr/bin/wiki"
    assert registry["syncthing"]["folders"][0]["id"] == "nm6xn-urvs7"


def test_sync_device_registry_prunes_stale_syncthing_devices(tmp_path: Path) -> None:
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
                    "MACOS-DEVICE": {"device_id": "MACOS-DEVICE", "name": "MacOS"},
                    "STALE-DEVICE": {
                        "device_id": "STALE-DEVICE",
                        "name": "Old laptop",
                        "backend": {"command": "/old/wiki", "args": []},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    registry = device_registry.sync_device_registry(
        vault,
        syncthing_config=config_path,
        backend_command="/usr/bin/wiki",
        backend_args=[],
    )

    assert set(registry["devices"]) == {"MACOS-DEVICE", "LINUX-DEVICE"}
    assert "STALE-DEVICE" not in registry["devices"]


def test_sync_device_registry_restores_missing_local_id_from_platform_entry(tmp_path: Path, monkeypatch) -> None:
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
                        "platform": {"system": "Darwin"},
                        "backend": {"command": "/Users/shin/wiki", "args": []},
                        "updated_at": 1780408526,
                    },
                    "LINUX-DEVICE": {"device_id": "LINUX-DEVICE", "name": "shin"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(device_registry, "read_syncthing_status", lambda _config_path: {})
    monkeypatch.setattr(device_registry.socket, "gethostname", lambda: "not-a-syncthing-name")
    monkeypatch.setattr(device_registry.platform, "node", lambda: "not-a-syncthing-name")

    registry = device_registry.sync_device_registry(
        vault,
        syncthing_config=config_path,
        backend_command="/usr/bin/wiki",
        backend_args=[],
    )

    assert registry["local_device_id"] == "MACOS-DEVICE"
    assert registry["devices"]["MACOS-DEVICE"]["backend"]["command"] == "/usr/bin/wiki"


def test_parse_args_text_accepts_json_or_shell_style() -> None:
    assert device_registry.parse_args_text('["--directory", "/repo/backend", "run", "wiki"]') == [
        "--directory",
        "/repo/backend",
        "run",
        "wiki",
    ]
    assert device_registry.parse_args_text("--directory /repo/backend run wiki") == [
        "--directory",
        "/repo/backend",
        "run",
        "wiki",
    ]


def test_read_syncthing_status_uses_ssl_context_for_https_gui(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.xml"
    config_path.write_text(
        """
<configuration version="52">
  <gui tls="true">
    <address>127.0.0.1:8384</address>
    <apikey>abc123</apikey>
  </gui>
</configuration>
""".strip(),
        encoding="utf-8",
    )

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self) -> bytes:
            return b'{"myID":"LOCAL-DEVICE"}'

    urlopen_mock = Mock(return_value=_Response())
    monkeypatch.setattr(device_registry.urllib.request, "urlopen", urlopen_mock)

    status = device_registry.read_syncthing_status(config_path)

    assert status == {"myID": "LOCAL-DEVICE"}
    assert urlopen_mock.call_count == 1
    assert urlopen_mock.call_args.kwargs.get("context") is not None
