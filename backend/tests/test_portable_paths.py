from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from curator import db
from curator import config as cfg
from curator import source_tools
from curator.db import schema as db_schema
from curator.path_refs import (
    PortablePathRef,
    RootUnregisteredError,
    encode_path,
    resolve_ref,
)


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


def test_fresh_v12_sources_schema_has_portable_sync_identity(tmp_path: Path) -> None:
    state_db = tmp_path / "state.sqlite"
    db.init_db(state_db)

    with db.connect(state_db) as conn:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(sources)").fetchall()
        }

    assert db.SCHEMA_VERSION == 12
    assert {"external_ref", "import_origin_ref", "sync_key"} <= columns
    assert "external_path" not in columns
    assert "import_origin" not in columns


def test_portable_path_backward_compatibility_modules_are_removed() -> None:
    assert importlib.util.find_spec("curator.portable_migration") is None
    assert not hasattr(db_schema, "_migrate_v10_portable_sources")


def test_legacy_root_arrays_are_not_runtime_roots(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    config = {
        "external": {
            "roots": [str(legacy_root)],
            "zotero": {"enabled": True, "roots": [str(legacy_root)]},
        }
    }

    assert source_tools.external_resources(config) == []


def test_absolute_source_relpath_is_not_resolved(tmp_path: Path) -> None:
    paths = cfg.WikiPaths(tmp_path / "vault")

    assert source_tools._row_path(
        paths,
        {
            "relpath": str(tmp_path / "legacy.pdf"),
            "is_reference": 0,
        },
    ) is None
