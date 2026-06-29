"""XC-1/G08-5: plugin API best-effort failures should be visible."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from curator import config as cfg
from curator import db
from curator import ingest_raw
from curator import plugin_api
from curator import search


@pytest.fixture
def source_vault(tmp_path: Path) -> tuple[cfg.WikiPaths, int]:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    for raw_dir in paths.raw_dirs:
        raw_dir.mkdir(parents=True, exist_ok=True)
    cfg.save_config(paths, {})
    db.init_db(paths.state_db)

    source_file = vault / "04_Resources" / "paper.md"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "# Paper\n\nEnough content to register as a tracked source.\n",
        encoding="utf-8",
    )
    outcome = ingest_raw.add_file(paths, source_file)
    return paths, int(outcome.source_id)


def test_register_source_warns_when_index_refresh_fails(source_vault: tuple[cfg.WikiPaths, int]) -> None:
    paths, source_id = source_vault
    with patch(
        "curator.ingest_raw.generate_l1_structural_context",
        return_value="CTX-warn0001",
    ), patch(
        "curator.plugin_api.search.update_index",
        side_effect=search.SearchBackendError("fts5 busy"),
    ):
        result = plugin_api.register_source(paths, source_id=source_id, build=False, force=True)

    assert result["ok"] is True
    assert result["warnings"] == ["Search index refresh skipped: SearchBackendError: fts5 busy"]


def test_register_source_propagates_unexpected_index_refresh_error(source_vault: tuple[cfg.WikiPaths, int]) -> None:
    paths, source_id = source_vault
    with patch(
        "curator.ingest_raw.generate_l1_structural_context",
        return_value="CTX-boom0001",
    ), patch(
        "curator.plugin_api.search.update_index",
        side_effect=RuntimeError("programmer error"),
    ):
        with pytest.raises(RuntimeError, match="programmer error"):
            plugin_api.register_source(paths, source_id=source_id, build=False, force=True)
