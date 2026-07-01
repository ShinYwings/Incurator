from __future__ import annotations

from pathlib import Path

import pytest

from curator import db
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


def test_fresh_v10_sources_schema_has_only_portable_locator_columns(tmp_path: Path) -> None:
    state_db = tmp_path / "state.sqlite"
    db.init_db(state_db)

    with db.connect(state_db) as conn:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(sources)").fetchall()
        }

    assert db.SCHEMA_VERSION == 10
    assert {"external_ref", "import_origin_ref"} <= columns
    assert "external_path" not in columns
    assert "import_origin" not in columns
