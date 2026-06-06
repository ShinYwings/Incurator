"""Syncthing auto-sync (one-writer-per-file) — backend tests.

Covers the structural design locked in
`.agents/plans/syncthing_auto_sync.md`:
- P1: config block, device-local sync_state.json, _DEVICE_LOCAL_COLUMNS, .stignore.
- P2: export_for_device / import_all_peers / detect_conflict_files, the dry-run
  regression lock, offline edit/delete tie-breaks, reference-mode path preservation,
  no-self-import, incremental --since.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import config as cfg
from curator import db, db_sync


# ---------------------------------------------------------------------------
# P1 — config / state / constants / .stignore
# ---------------------------------------------------------------------------


class TestAutoSyncConfig:
    def test_default_config_has_auto_sync_block(self) -> None:
        block = cfg.DEFAULT_CONFIG.get("auto_sync")
        assert isinstance(block, dict)
        assert block["enabled"] is False  # opt-in, no regression for CLI users
        assert block["dir"] == "sync"
        assert "debounce_ms" in block
        assert "poll_ms" in block


class TestSyncState:
    def test_round_trip(self, tmp_path: Path) -> None:
        internal = tmp_path / ".curator"
        internal.mkdir()
        db_sync.write_sync_state(internal, {"device_id": "abc", "peers": {}})
        assert db_sync.read_sync_state(internal)["device_id"] == "abc"

    def test_read_missing_returns_empty(self, tmp_path: Path) -> None:
        assert db_sync.read_sync_state(tmp_path / ".curator") == {}

    def test_get_device_id_generates_and_persists(self, tmp_path: Path) -> None:
        internal = tmp_path / ".curator"
        internal.mkdir()
        first = db_sync.get_device_id(internal)
        assert first and len(first) == 12
        # Stable across calls (persisted).
        assert db_sync.get_device_id(internal) == first
        assert db_sync.read_sync_state(internal)["device_id"] == first


class TestConstantsAndIgnore:
    def test_device_local_columns_protects_external_path(self) -> None:
        assert "external_path" in db_sync._DEVICE_LOCAL_COLUMNS["sources"]

    def test_stignore_template_excludes_sync_state(self) -> None:
        template = (
            Path(cfg.__file__).parent / "workspace" / "templates" / "stignore.template"
        )
        text = template.read_text(encoding="utf-8")
        assert "sync_state.json" in text
        # The synced knowledge files must NOT be excluded.
        assert ".curator/sync/\n" not in text and ".curator/sync/*" not in text


# ---------------------------------------------------------------------------
# Shared fixtures for P2
# ---------------------------------------------------------------------------


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A minimal initialized .curator dir with an empty state DB."""
    internal = tmp_path / ".curator"
    internal.mkdir()
    db.init_db(internal / "state.sqlite")
    return tmp_path
