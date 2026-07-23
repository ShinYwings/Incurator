"""Tests for pdf_context and import_source reference-policy identity resolution.

These tests verify DB registration and retrieval logic for external (reference)
PDF sources. PDF parsing is mocked so the tests run without pymupdf4llm.
"""

from __future__ import annotations

import hashlib
import sqlite3
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from curator import config as cfg
from curator import db, ingest_raw, page_writer, plugin_api
from curator.parsers.base import ParsedDocument

_MOCK_TEXT = "Page one content for reference source identity tests. " * 5
_MOCK_HASH = hashlib.sha256(_MOCK_TEXT.encode()).hexdigest()
_MOCK_PDF_PAGES = [{"page": 1, "text": "Page one"}]


def _configure_external_root(monkeypatch, root: Path) -> None:
    config = deepcopy(cfg.DEFAULT_CONFIG)
    config["external"]["path_roots"] = {"test_library": str(root)}
    monkeypatch.setattr(cfg, "load_config", lambda _paths: config)


def _mock_parsed_doc(path: Path) -> ParsedDocument:
    return ParsedDocument(
        source_path=path,
        file_type="pdf",
        title=path.stem,
        text=_MOCK_TEXT,
        content_hash=_MOCK_HASH,
        bytes=1463,
        metadata={"pdf_pages": _MOCK_PDF_PAGES},
    )


def _mock_page_window(path: Path, pages: set) -> dict:
    return {p: f"Page {p}" for p in pages}


def _make_zotero_attachment_db(db_path: Path, attachment_key: str, attachment_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, path TEXT)")
        conn.execute("INSERT INTO items (itemID, key) VALUES (1, ?)", (attachment_key,))
        conn.execute("INSERT INTO itemAttachments (itemID, path) VALUES (1, ?)", (attachment_path,))


def _write_inline_l1(paths: cfg.WikiPaths, source_id: int, context_id: str = "CTX-test") -> None:
    paths.contexts.mkdir(parents=True, exist_ok=True)
    page = page_writer.ParsedPage(
        frontmatter={
            "id": context_id,
            "source_text_policy": "inline",
            "source_page_count": 2,
            "toc": [
                {"id": "s1", "title": "Introduction", "level": 2, "page": 1},
                {"id": "s2", "title": "Method", "level": 2, "page": 2},
            ],
        },
        body=(
            "## Source Sections\n\n"
            "<!-- section:s1 page:1 -->\n"
            "## Introduction\n\n"
            "Durable introduction text.\n\n"
            "<!-- section:s2 page:2 -->\n"
            "## Method\n\n"
            "Durable method text.\n"
        ),
    )
    (paths.contexts / f"{context_id}.md").write_text(page.to_markdown(), encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET context_id = ?, l1_status = 'done' WHERE id = ?",
            (context_id, source_id),
        )


@patch("curator.parsers.pdf.parse_page_window", side_effect=_mock_page_window)
@patch("curator.parsers.pdf.get_page_count", return_value=3)
@patch("curator.parsers.parse", side_effect=_mock_parsed_doc)
def test_pdf_context_resolves_reference_source_id_to_external_pdf(
    _mock_parse, _mock_count, _mock_window, tmp_path: Path, monkeypatch
) -> None:
    _configure_external_root(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)

    external = tmp_path / "zotero" / "storage" / "ABC123" / "paper.pdf"
    external.parent.mkdir(parents=True)
    external.write_bytes(b"%PDF-1.4 mock")
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


@patch("curator.parsers.pdf.parse_page_window", side_effect=AssertionError("must not reparse durable L1"))
@patch("curator.parsers.pdf._extract_pdf_toc", side_effect=AssertionError("must not reparse durable L1"))
@patch("curator.parsers.parse", side_effect=_mock_parsed_doc)
def test_pdf_context_uses_inline_l1_projection_without_reparsing_pdf(
    _mock_parse, _mock_toc, _mock_window, tmp_path: Path, monkeypatch
) -> None:
    _configure_external_root(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)

    external = tmp_path / "outside" / "paper.pdf"
    external.parent.mkdir(parents=True)
    external.write_bytes(b"%PDF-1.4 mock")
    outcome = ingest_raw.import_source_file(paths, external, policy="reference")
    _write_inline_l1(paths, outcome.source_id)
    external.unlink()

    result = plugin_api.pdf_context(paths, source_id=outcome.source_id, page_num=2, radius=0)

    assert result["ok"] is True
    assert result["context_source"] == "durable_l1_projection"
    assert result.get("degraded_reason") is None
    assert result["outline"][1]["title"] == "Method"
    assert result["pages"] == [{"page_num": 2, "text": "## Method\n\nDurable method text.", "score": 0.0}]


@patch("curator.parsers.pdf.parse_page_window", side_effect=_mock_page_window)
@patch("curator.parsers.pdf.get_page_count", return_value=3)
@patch("curator.parsers.pdf._extract_pdf_toc", return_value=[])
@patch("curator.parsers.parse", side_effect=_mock_parsed_doc)
def test_pdf_context_missing_l1_projection_degrades_to_read_only_parse(
    _mock_parse, _mock_toc, _mock_count, _mock_window, tmp_path: Path, monkeypatch
) -> None:
    _configure_external_root(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)

    external = tmp_path / "outside" / "paper.pdf"
    external.parent.mkdir(parents=True)
    external.write_bytes(b"%PDF-1.4 mock")
    outcome = ingest_raw.import_source_file(paths, external, policy="reference")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET context_id = 'CTX-missing', l1_status = 'done' WHERE id = ?",
            (outcome.source_id,),
        )
        before = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]

    result = plugin_api.pdf_context(paths, source_id=outcome.source_id, page_num=1, radius=0)

    with db.connect(paths.state_db) as conn:
        after = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    assert result["ok"] is True
    assert result["context_source"] == "ephemeral_parse"
    assert result["degraded_reason"] == "missing_l1_projection"
    assert after == before


@patch("curator.parsers.pdf.parse_page_window", side_effect=_mock_page_window)
@patch("curator.parsers.pdf.get_page_count", return_value=3)
@patch("curator.parsers.pdf._extract_pdf_toc", return_value=[])
@patch("curator.parsers.parse", side_effect=_mock_parsed_doc)
def test_pdf_context_uses_content_hash_page_cache_for_repeated_page_fetch(
    _mock_parse, _mock_toc, _mock_count, _mock_window, tmp_path: Path, monkeypatch
) -> None:
    _configure_external_root(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)

    external = tmp_path / "outside" / "paper.pdf"
    external.parent.mkdir(parents=True)
    external.write_bytes(b"%PDF-1.4 mock")
    outcome = ingest_raw.import_source_file(paths, external, policy="reference")
    row = db.get_source_row(paths.state_db, paths.root, source_id=outcome.source_id)
    assert row is not None
    content_hash = str(row["content_hash"])

    first = plugin_api.pdf_context(paths, source_id=outcome.source_id, page_num=1, radius=0)
    assert first["ok"] is True
    cache_file = paths.pdf_pages / content_hash / "1.txt"
    assert cache_file.read_text(encoding="utf-8") == "Page 1"

    _mock_window.side_effect = AssertionError("must use page cache")
    second = plugin_api.pdf_context(paths, source_id=outcome.source_id, page_num=1, radius=0)
    assert second["ok"] is True
    assert second["pages"][0]["text"] == "Page 1"


def test_pdf_page_cache_key_tolerates_missing_or_non_string_hash(tmp_path: Path) -> None:
    paths = cfg.WikiPaths(tmp_path / "vault")
    pdf = tmp_path / "outside" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 mock")

    assert plugin_api._safe_pdf_page_cache_key(None) == ""
    non_string_hash = 123
    assert plugin_api._safe_pdf_page_cache_key(non_string_hash) == ""
    assert plugin_api._safe_pdf_page_cache_key(f"  {_MOCK_HASH.upper()}  ") == _MOCK_HASH.upper()

    with patch("curator.parsers.pdf.parse_page_window", return_value={2: "Page 2"}) as mock_window:
        out = plugin_api._parse_pdf_pages_cached(paths, pdf, {2}, None)

    assert out == {2: "Page 2"}
    mock_window.assert_called_once_with(pdf, {2})
    assert not (paths.root / ".cache" / "pdf_pages").exists()


@patch("curator.parsers.pdf.parse_page_window", side_effect=_mock_page_window)
@patch("curator.parsers.pdf.get_page_count", return_value=1)
@patch("curator.parsers.pdf._extract_pdf_toc", return_value=[])
def test_untracked_pdf_context_does_not_create_source_row(
    _mock_toc, _mock_count, _mock_window, tmp_path: Path
) -> None:
    paths = cfg.WikiPaths(tmp_path / "vault")
    db.init_db(paths.state_db)
    external = tmp_path / "outside" / "untracked.pdf"
    external.parent.mkdir(parents=True)
    external.write_bytes(b"%PDF-1.4 mock")

    result = plugin_api.pdf_context(paths, file_path=str(external), max_pages=1)

    with db.connect(paths.state_db) as conn:
        source_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    assert result["ok"] is True
    assert result["source_tracked"] is False
    assert result["context_source"] == "ephemeral_parse"
    assert source_count == 0


@patch("curator.parsers.pdf.parse_page_window", side_effect=_mock_page_window)
@patch("curator.parsers.pdf.get_page_count", return_value=3)
@patch("curator.parsers.parse", side_effect=_mock_parsed_doc)
def test_pdf_context_resolves_by_file_hash(
    _mock_parse, _mock_count, _mock_window, tmp_path: Path, monkeypatch
) -> None:
    _configure_external_root(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)

    external = tmp_path / "outside" / "paper.pdf"
    external.parent.mkdir(parents=True)
    external.write_bytes(b"%PDF-1.4 mock")
    outcome = ingest_raw.import_source_file(paths, external, policy="reference")
    row = db.get_source_row(paths.state_db, paths.root, source_id=outcome.source_id)
    assert row is not None

    result = plugin_api.pdf_context(paths, file_hash=str(row["content_hash"]), max_pages=1)

    assert result["ok"] is True
    assert result["source_id"] == outcome.source_id


@patch("curator.parsers.parse", side_effect=_mock_parsed_doc)
def test_import_source_resolves_zotero_attachment_key_as_reference(
    _mock_parse, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)

    zotero_dir = tmp_path / "Zotero"
    pdf = zotero_dir / "storage" / "ATTKEY" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 mock")
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
    assert row["relpath"] == "04_Resources/References/paper.md"
    assert row["external_ref"] is None
    assert row["import_origin_ref"] is None
    assert row["logical_source_id"] == "zotero:ATTKEY"

    registered = plugin_api.register_source(paths, source_id=imported["source_id"], build=True)
    assert registered["ok"] is True
    assert registered["state"] == "queued"
    assert registered["l2_l3_queued"] is True
    assert registered["job_ids"]


@patch("curator.parsers.parse", side_effect=_mock_parsed_doc)
def test_import_source_uses_zotero_identity_when_path_and_key_are_supplied(
    _mock_parse, tmp_path: Path, monkeypatch
) -> None:
    config = deepcopy(cfg.DEFAULT_CONFIG)
    config["external"]["path_roots"] = {}
    monkeypatch.setattr(cfg, "load_config", lambda _paths: config)
    paths = cfg.WikiPaths(tmp_path / "vault")
    db.init_db(paths.state_db)

    pdf = tmp_path / "unregistered-zotero-root" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 mock")

    imported = plugin_api.import_source(
        paths,
        file_path=str(pdf),
        zotero_attachment_key="ATTKEY",
        policy="reference",
    )

    assert imported["ok"] is True
    assert imported["zotero_attachment_key"] == "ATTKEY"
    row = db.get_source_row(paths.state_db, paths.root, source_id=imported["source_id"])
    assert row is not None
    assert row["logical_source_id"] == "zotero:ATTKEY"
    assert row["external_ref"] is None
    assert row["import_origin_ref"] is None


@patch("curator.parsers.parse", side_effect=_mock_parsed_doc)
def test_import_source_still_rejects_unregistered_generic_reference_path(
    _mock_parse, tmp_path: Path, monkeypatch
) -> None:
    config = deepcopy(cfg.DEFAULT_CONFIG)
    config["external"]["path_roots"] = {}
    monkeypatch.setattr(cfg, "load_config", lambda _paths: config)
    paths = cfg.WikiPaths(tmp_path / "vault")
    db.init_db(paths.state_db)

    pdf = tmp_path / "unregistered-generic-root" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 mock")

    imported = plugin_api.import_source(
        paths,
        file_path=str(pdf),
        policy="reference",
    )

    assert imported["ok"] is False
    assert imported["message"].startswith("root_unregistered:")
