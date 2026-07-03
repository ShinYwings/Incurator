from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from curator import db
from curator.path_refs import (
    PortablePathRef,
    RootUnregisteredError,
    encode_path,
    resolve_ref,
)
from curator import config as cfg
from curator.portable_migration import migrate_portable_paths


def test_encode_uses_longest_named_root(tmp_path: Path) -> None:
    library = tmp_path / "library"
    linked = library / "linked"
    pdf = linked / "project" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"pdf")

    ref = encode_path(
        pdf,
        {"library": library, "linked_papers": linked},
    )

    assert ref == "@linked_papers/project/paper.pdf"


def test_encode_rejects_path_outside_registered_roots(tmp_path: Path) -> None:
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"pdf")

    with pytest.raises(RootUnregisteredError):
        encode_path(outside, {"library": tmp_path / "library"})


@pytest.mark.parametrize(
    "raw",
    [
        "/home/user/paper.pdf",
        "C:\\Users\\user\\paper.pdf",
        "\\\\server\\share\\paper.pdf",
        "file:///home/user/paper.pdf",
        "@library/../paper.pdf",
        "@library//absolute.pdf",
        "@Missing/paper.pdf",
    ],
)
def test_portable_ref_rejects_absolute_traversal_and_invalid_keys(raw: str) -> None:
    with pytest.raises(ValueError):
        PortablePathRef.parse(raw)


def test_resolve_ref_uses_machine_local_root(tmp_path: Path) -> None:
    library = tmp_path / "zotero"
    pdf = library / "storage" / "KEY" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"pdf")

    assert resolve_ref("@zotero_library/storage/KEY/paper.pdf", {"zotero_library": library}) == pdf


def test_fresh_v11_sources_schema_has_only_portable_locator_columns(tmp_path: Path) -> None:
    state_db = tmp_path / "state.sqlite"
    db.init_db(state_db)

    with db.connect(state_db) as conn:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(sources)").fetchall()
        }

    assert db.SCHEMA_VERSION == 11
    assert {"external_ref", "import_origin_ref"} <= columns
    assert "external_path" not in columns
    assert "import_origin" not in columns


def test_legacy_absolute_reference_migrates_to_stub_and_portable_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    db.init_db(paths.state_db)
    external_root = tmp_path / "papers"
    source = external_root / "project" / "paper.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF")

    with sqlite3.connect(paths.state_db) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE sources")
        conn.executescript(
            """
            CREATE TABLE sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relpath TEXT NOT NULL UNIQUE, content_hash TEXT NOT NULL,
                file_type TEXT NOT NULL, bytes INTEGER NOT NULL,
                added_at TEXT NOT NULL, last_ingested TEXT,
                status TEXT NOT NULL DEFAULT 'pending', context_id TEXT,
                l1_status TEXT NOT NULL DEFAULT 'pending',
                l2_status TEXT NOT NULL DEFAULT 'pending',
                l3_status TEXT NOT NULL DEFAULT 'pending',
                l4_status TEXT NOT NULL DEFAULT 'pending',
                layer_error TEXT, domain TEXT, tags TEXT,
                import_origin TEXT, import_policy TEXT, external_path TEXT,
                is_reference INTEGER NOT NULL DEFAULT 0,
                logical_source_id TEXT, error_reason TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sources (
                id, relpath, content_hash, file_type, bytes, added_at,
                import_origin, import_policy, external_path, is_reference,
                logical_source_id
            ) VALUES (5, ?, 'hash', 'pdf', 4, '2026-01-01T00:00:00Z',
                      ?, 'reference', ?, 1, 'ref-legacy')
            """,
            (str(source), str(source), str(source)),
        )
        conn.execute(
            """
            INSERT INTO source_pdf_pages (
                source_id, relpath, page_number, content_hash, extracted_at
            ) VALUES (5, ?, 1, 'page-hash', '2026-01-01T00:00:00Z')
            """,
            (str(source),),
        )
        conn.execute("UPDATE schema_version SET version = 9")

    config = {
        "external": {
            "path_roots": {"papers": str(external_root)},
            "zotero": {"enabled": True, "roots": [], "root_keys": []},
        }
    }
    monkeypatch.setattr(cfg, "load_config", lambda _paths: config)
    monkeypatch.setattr(
        cfg,
        "get_global_config_dir",
        lambda: tmp_path / "repo-cache" / "config",
    )
    monkeypatch.setattr(
        "curator.zotero_tools.attachment_key_for_path",
        lambda *_args, **_kwargs: "",
    )

    preview = migrate_portable_paths(paths)
    assert preview.ok and preview.dry_run
    assert preview.rows[0]["external_ref"] == "@papers/project/paper.pdf"

    result = migrate_portable_paths(paths, apply=True)
    assert result.ok and not result.dry_run
    with db.connect(paths.state_db) as conn:
        row = dict(conn.execute("SELECT * FROM sources WHERE id = 5").fetchone())
        page_relpath = conn.execute(
            "SELECT relpath FROM source_pdf_pages WHERE source_id = 5"
        ).fetchone()[0]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert row["external_ref"] == "@papers/project/paper.pdf"
    assert row["import_origin_ref"] == "@papers/project/paper.pdf"
    assert not Path(row["relpath"]).is_absolute()
    assert page_relpath == row["relpath"]
    assert (vault / row["relpath"]).exists()
    assert db.SCHEMA_VERSION == 11
