from pathlib import Path
import sqlite3

import pytest

pymupdf4llm = pytest.importorskip("pymupdf4llm", reason="pymupdf4llm not installed")

from curator import config as cfg
from curator import db, ingest_raw, plugin_api


def _make_zotero_attachment_db(db_path: Path, attachment_key: str, attachment_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, path TEXT)")
        conn.execute("INSERT INTO items (itemID, key) VALUES (1, ?)", (attachment_key,))
        conn.execute("INSERT INTO itemAttachments (itemID, path) VALUES (1, ?)", (attachment_path,))


def test_pdf_context_resolves_reference_source_id_to_external_pdf(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)

    external = tmp_path / "zotero" / "storage" / "ABC123" / "paper.pdf"
    external.parent.mkdir(parents=True)
    external.write_bytes((Path(__file__).parent / "fixtures" / "test.pdf").read_bytes())
    outcome = ingest_raw.import_source_file(paths, external, policy="reference")

    result = plugin_api.pdf_context(
        paths,
        source_id=outcome.source_id,
        page_num=1,
        radius=0,
        max_pages=1,
    )

    assert result["ok"] is True
    assert result["source_tracked"] is True
    assert result["source_id"] == outcome.source_id
    assert result["total_pages"] >= 1
    assert result["pages"][0]["page_num"] == 1


def test_pdf_context_resolves_by_file_hash(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)

    external = tmp_path / "outside" / "paper.pdf"
    external.parent.mkdir(parents=True)
    external.write_bytes((Path(__file__).parent / "fixtures" / "test.pdf").read_bytes())
    outcome = ingest_raw.import_source_file(paths, external, policy="reference")
    row = db.get_source_row(paths.state_db, paths.root, source_id=outcome.source_id)
    assert row is not None

    result = plugin_api.pdf_context(paths, file_hash=str(row["content_hash"]), max_pages=1)

    assert result["ok"] is True
    assert result["source_id"] == outcome.source_id


def test_import_source_resolves_zotero_attachment_key_as_reference(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)

    zotero_dir = tmp_path / "Zotero"
    pdf = zotero_dir / "storage" / "ATTKEY" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes((Path(__file__).parent / "fixtures" / "test.pdf").read_bytes())
    _make_zotero_attachment_db(zotero_dir / "zotero.sqlite", "ATTKEY", "storage:paper.pdf")

    imported = plugin_api.import_source(
        paths,
        zotero_attachment_key="ATTKEY",
        zotero_custom_paths=str(zotero_dir),
        policy="reference",
    )

    assert imported["ok"] is True
    assert imported["zotero_attachment_key"] == "ATTKEY"
    assert imported["relpath"] == "04_Resources/References/paper.md"
    stub_text = (vault / imported["relpath"]).read_text(encoding="utf-8")
    assert "reference_kind: zotero" in stub_text
    assert "zotero_attachment_key: ATTKEY" in stub_text
    assert "logical_source_id: zotero:ATTKEY" in stub_text
    assert "zotero://open-pdf/library/items/ATTKEY?viewer=obsidian" in stub_text
    assert "zotero://open-pdf/library/items/ATTKEY" in stub_text
    assert str(pdf.resolve()) not in stub_text
    row = db.get_source_row(paths.state_db, paths.root, source_id=imported["source_id"])
    assert row is not None
    assert row["external_path"] == str(pdf.resolve())
    assert row["logical_source_id"] == "zotero:ATTKEY"

    registered = plugin_api.register_source(paths, source_id=imported["source_id"], build=True)
    assert registered["ok"] is True
    assert registered["state"] == "queued"
    assert registered["l2_l3_queued"] is True
    assert registered["job_ids"]
