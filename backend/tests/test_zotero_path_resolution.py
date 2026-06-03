from __future__ import annotations

from pathlib import Path

from curator import mcp_server


def test_zotero_root_candidates_accepts_sqlite_file_path(tmp_path: Path) -> None:
    zotero_dir = tmp_path / "Zotero"
    zotero_dir.mkdir()
    sqlite_path = zotero_dir / "zotero.sqlite"
    sqlite_path.touch()

    candidates = mcp_server._zotero_root_candidates(str(sqlite_path), {})

    assert str(zotero_dir) in candidates
    assert str(sqlite_path) not in candidates


def test_zotero_root_candidates_includes_external_roots(tmp_path: Path) -> None:
    custom_dir = tmp_path / "Zotero"
    external_dir = tmp_path / "ZoteroLinked"

    candidates = mcp_server._zotero_root_candidates(
        str(custom_dir),
        {"external": {"zotero": {"roots": [str(external_dir)]}}},
    )

    assert str(custom_dir) in candidates
    assert str(external_dir) in candidates
