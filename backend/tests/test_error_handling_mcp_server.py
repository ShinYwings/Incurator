"""XC-1/G08-5: MCP best-effort failures should be visible."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest

from curator import config as cfg
from curator import db
from curator import ingest_raw
from curator import mcp_server
from curator import search


@pytest.fixture
def source_vault(tmp_path: Path) -> tuple[cfg.WikiPaths, int]:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    for raw_dir in paths.raw_dirs:
        raw_dir.mkdir(parents=True, exist_ok=True)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)

    source_file = vault / "04_Resources" / "paper.md"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "# Paper\n\nEnough content to register as a tracked source.\n",
        encoding="utf-8",
    )
    outcome = ingest_raw.add_file(paths, source_file)
    return paths, int(outcome.source_id)


@pytest.fixture
def register_source_tool(source_vault: tuple[cfg.WikiPaths, int]) -> Callable[..., dict]:
    paths, _source_id = source_vault
    old_vault_root = os.environ.get("VAULT_ROOT")
    old_disable_worker = os.environ.get("CURATOR_DISABLE_INGEST_WORKER")
    os.environ["VAULT_ROOT"] = str(paths.root)
    os.environ["CURATOR_DISABLE_INGEST_WORKER"] = "1"
    try:
        with patch("curator.ingest_worker.IngestWorker", autospec=True):
            server = mcp_server.build_server()
        yield getattr(server._tool_manager, "_tools", {})["curator_register_source"].fn
    finally:
        if old_vault_root is None:
            os.environ.pop("VAULT_ROOT", None)
        else:
            os.environ["VAULT_ROOT"] = old_vault_root
        if old_disable_worker is None:
            os.environ.pop("CURATOR_DISABLE_INGEST_WORKER", None)
        else:
            os.environ["CURATOR_DISABLE_INGEST_WORKER"] = old_disable_worker


def test_register_source_warns_when_index_refresh_fails(
    source_vault: tuple[cfg.WikiPaths, int],
    register_source_tool: Callable[..., dict],
) -> None:
    paths, source_id = source_vault
    with patch(
        "curator.ingest_raw.generate_l1_structural_context",
        return_value="CTX-warn0001",
    ), patch(
        "curator.search.update_index",
        side_effect=search.SearchBackendError("fts5 busy"),
    ):
        result = register_source_tool(source_id=source_id, build=False, force=True, workspace_path=str(paths.root))

    assert result["ok"] is True
    assert result["warnings"] == ["Search index refresh skipped: SearchBackendError: fts5 busy"]


def test_register_source_propagates_unexpected_index_refresh_error(
    source_vault: tuple[cfg.WikiPaths, int],
    register_source_tool: Callable[..., dict],
) -> None:
    paths, source_id = source_vault
    with patch(
        "curator.ingest_raw.generate_l1_structural_context",
        return_value="CTX-boom0001",
    ), patch(
        "curator.search.update_index",
        side_effect=RuntimeError("programmer error"),
    ):
        with pytest.raises(RuntimeError, match="programmer error"):
            register_source_tool(source_id=source_id, build=False, force=True, workspace_path=str(paths.root))
