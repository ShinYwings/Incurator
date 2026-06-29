from pathlib import Path
import sqlite3

from curator import config as cfg
from curator import zotero_tools


def _make_zotero_attachment_db(db_path: Path, attachment_key: str, attachment_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, path TEXT)")
        conn.execute("INSERT INTO items (itemID, key) VALUES (1, ?)", (attachment_key,))
        conn.execute("INSERT INTO itemAttachments (itemID, path) VALUES (1, ?)", (attachment_path,))


def test_zotero_db_candidates_accepts_direct_sqlite_path(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "zotero.sqlite"
    assert zotero_tools.zotero_db_candidates(str(sqlite_path)) == [str(sqlite_path)]


def test_zotero_root_candidates_normalizes_sqlite_to_parent(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "zotero.sqlite"
    roots = zotero_tools.zotero_root_candidates(str(sqlite_path), {"external": {"zotero": {"roots": []}}})
    assert str(tmp_path) in roots


def test_zotero_status_ready_for_readable_sqlite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    global_dir = tmp_path / "cache_config"
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    paths = cfg.WikiPaths(tmp_path / "vault")
    cfg.save_global_config({"external": {"zotero": {"enabled": True, "roots": []}}})
    zotero_dir = tmp_path / "Zotero"
    zotero_dir.mkdir()
    sqlite_path = zotero_dir / "zotero.sqlite"
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY)")

    status = zotero_tools.zotero_status(paths, str(zotero_dir))

    assert status["ok"] is True
    assert status["state"] == "ready"
    assert status["data_dir"] == str(zotero_dir)
    assert status["db_path"] == str(sqlite_path)


def test_zotero_status_reports_db_missing_for_existing_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    global_dir = tmp_path / "cache_config"
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    paths = cfg.WikiPaths(tmp_path / "vault")
    cfg.save_global_config({"external": {"zotero": {"enabled": True, "roots": []}}})
    zotero_dir = tmp_path / "Zotero"
    zotero_dir.mkdir()

    status = zotero_tools.zotero_status(paths, str(zotero_dir))

    assert status["ok"] is False
    assert status["state"] == "db_missing"
    assert status["data_dir"] == str(zotero_dir)


def test_zotero_init_saves_local_roots(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    global_dir = tmp_path / "repo" / "cache_config"
    zotero_dir = tmp_path / "Zotero"
    linked_dir = tmp_path / "ZoteroLinked"
    zotero_dir.mkdir()
    linked_dir.mkdir()
    with sqlite3.connect(zotero_dir / "zotero.sqlite") as conn:
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY)")

    from unittest.mock import patch

    with patch.object(cfg, "get_global_config_dir", return_value=global_dir):
        status = zotero_tools.zotero_init(
            paths,
            data_dir=str(zotero_dir),
            linked_base_dir=str(linked_dir),
        )
        saved = cfg.load_config(paths)
        global_cfg = (global_dir / "config.yml").read_text(encoding="utf-8")

    assert status["state"] == "ready"
    assert str(zotero_dir) in saved["external"]["zotero"]["roots"]
    assert str(linked_dir) in saved["external"]["zotero"]["roots"]
    assert str(zotero_dir) in global_cfg
    assert not paths.config_file.exists() or "external:" not in paths.config_file.read_text(encoding="utf-8")


def test_zotero_root_candidates_reads_base_attachment_path_from_prefs(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(zotero_tools.platform, "system", lambda: "Darwin")
    profile = home / "Library" / "Application Support" / "Zotero" / "Profiles" / "abc.default"
    profile.mkdir(parents=True)
    linked = tmp_path / "Linked Attachments"
    profile.joinpath("prefs.js").write_text(
        f'user_pref("extensions.zotero.baseAttachmentPath", "{linked}");\n',
        encoding="utf-8",
    )

    roots = zotero_tools.zotero_root_candidates("", {"external": {"zotero": {"roots": []}}})

    assert str(linked) in roots


def test_zotero_root_candidates_reads_zotmoov_path_from_prefs(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(zotero_tools.platform, "system", lambda: "Linux")
    profile = home / ".zotero" / "zotero" / "abc.default"
    profile.mkdir(parents=True)
    linked = tmp_path / "ZotMoov"
    escaped = str(linked).replace("\\", "\\\\")
    profile.joinpath("prefs.js").write_text(
        f'user_pref("extensions.zotmoov.dst_dir", "{escaped}");\n',
        encoding="utf-8",
    )

    roots = zotero_tools.zotero_root_candidates("", {"external": {"zotero": {"roots": []}}})

    assert str(linked) in roots


def test_resolve_pdf_uses_storage_path_from_zotero_db(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    paths = cfg.WikiPaths(tmp_path / "vault")
    zotero_dir = tmp_path / "Zotero"
    storage_dir = zotero_dir / "storage" / "ATTACH1"
    storage_dir.mkdir(parents=True)
    pdf = storage_dir / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    _make_zotero_attachment_db(zotero_dir / "zotero.sqlite", "ATTACH1", "storage:paper.pdf")

    result = zotero_tools.resolve_pdf("ATTACH1", paths, str(zotero_dir))

    assert result["ok"] is True
    assert result["path"] == str(pdf)


def test_resolve_pdf_uses_linked_attachment_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    global_dir = tmp_path / "cache_config"
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    paths = cfg.WikiPaths(tmp_path / "vault")
    zotero_dir = tmp_path / "Zotero"
    zotero_dir.mkdir()
    linked_dir = tmp_path / "ZoteroLinked"
    linked_dir.mkdir(parents=True)
    pdf = linked_dir / "papers" / "paper.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4\n")
    _make_zotero_attachment_db(zotero_dir / "zotero.sqlite", "ATTACH2", "attachments:papers/paper.pdf")
    cfg.save_global_config({"external": {"zotero": {"enabled": True, "roots": [str(linked_dir)]}}})

    result = zotero_tools.resolve_pdf("ATTACH2", paths, str(zotero_dir))

    assert result["ok"] is True
    assert result["path"] == str(pdf)


def test_resolve_pdf_reports_attachment_file_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    paths = cfg.WikiPaths(tmp_path / "vault")
    zotero_dir = tmp_path / "Zotero"
    zotero_dir.mkdir()
    _make_zotero_attachment_db(zotero_dir / "zotero.sqlite", "ATTACH3", "storage:missing.pdf")

    result = zotero_tools.resolve_pdf("ATTACH3", paths, str(zotero_dir))

    assert result["ok"] is False
    assert result["state"] == "attachment_file_missing"
    assert "storage/ATTACH3/missing.pdf" in result["paths_checked"][0]


def test_resolve_pdf_reports_attachment_key_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    paths = cfg.WikiPaths(tmp_path / "vault")
    zotero_dir = tmp_path / "Zotero"
    zotero_dir.mkdir()
    _make_zotero_attachment_db(zotero_dir / "zotero.sqlite", "OTHER", "storage:paper.pdf")

    result = zotero_tools.resolve_pdf("UNKNOWN", paths, str(zotero_dir))

    assert result["ok"] is False
    assert result["state"] == "attachment_key_missing"


def _make_zotero_parent_child_db(
    db_path: Path, parent_key: str, child_key: str, attachment_path: str
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute(
            "CREATE TABLE itemAttachments "
            "(itemID INTEGER PRIMARY KEY, parentItemID INTEGER, path TEXT, contentType TEXT)"
        )
        conn.execute("INSERT INTO items (itemID, key) VALUES (1, ?)", (parent_key,))
        conn.execute("INSERT INTO items (itemID, key) VALUES (2, ?)", (child_key,))
        conn.execute(
            "INSERT INTO itemAttachments (itemID, parentItemID, path, contentType) "
            "VALUES (2, 1, ?, 'application/pdf')",
            (attachment_path,),
        )


def test_resolve_pdf_resolves_parent_item_key_to_child_attachment(
    tmp_path: Path, monkeypatch
) -> None:
    # zotero_app_url carries the PARENT item key; the PDF lives on a child
    # attachment. Resolution must find the child and use the child's key for the
    # storage subdir (the "attachment key not found" reload bug).
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    paths = cfg.WikiPaths(tmp_path / "vault")
    zotero_dir = tmp_path / "Zotero"
    storage_dir = zotero_dir / "storage" / "CHILD1"
    storage_dir.mkdir(parents=True)
    pdf = storage_dir / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    _make_zotero_parent_child_db(
        zotero_dir / "zotero.sqlite", "PARENT1", "CHILD1", "storage:paper.pdf"
    )

    result = zotero_tools.resolve_pdf("PARENT1", paths, str(zotero_dir))

    assert result["ok"] is True
    assert result["path"] == str(pdf)
    assert result["attachment_key"] == "CHILD1"
    assert result["zotero_db"] == str(zotero_dir / "zotero.sqlite")


def test_copy_db_to_repo_temp_cleans_up_on_copy_failure(tmp_path, monkeypatch) -> None:
    """A failed copy must not leave an empty placeholder in .cache/zotero_sqlite/.

    Callers fall back to the original db_path when the helper raises and only
    unlink temp paths that differ from db_path, so a leaked placeholder would
    never be cleaned up.
    """
    from curator import config as cfg
    from curator import zotero

    cache_parent = tmp_path / "config"
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: cache_parent / "global")

    src_db = tmp_path / "zotero.sqlite"
    src_db.write_text("not-really-a-db", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(zotero.shutil, "copy2", _boom)

    import pytest

    with pytest.raises(OSError):
        zotero._copy_db_to_repo_temp(src_db)

    temp_dir = cache_parent / "zotero_sqlite"
    leftovers = list(temp_dir.glob("*.sqlite")) if temp_dir.exists() else []
    assert leftovers == [], f"copy failure leaked temp files: {leftovers}"
