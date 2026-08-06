"""Moving or deleting a vault file must not lose the knowledge built from it.

The reported symptom was a sidechat "File not found" after moving a
Zotero-imported note. The backend half is that the path is denormalized into
three columns and nothing reconciled them, so a move silently orphaned every
row that pointed at the old location.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import config as cfg
from curator import db


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path)
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.synthesis):
        layer_dir.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    return paths


def _seed(paths: cfg.WikiPaths, relpath: str, *, spans: int = 3) -> int:
    with db.connect(paths.state_db) as conn:
        cur = conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
            "status, context_id, l1_status, l2_status, l3_status, l4_status, "
            "is_reference, logical_source_id) "
            "VALUES (?, 'hash-abc', 'md', 100, '2026-08-06T00:00:00Z', 'curated', "
            "'CTX-abc12345', 'done', 'done', 'done', 'done', 1, 'zotero:YACIRUKK')",
            (relpath,),
        )
        source_id = int(cur.lastrowid)
        for i in range(spans):
            conn.execute(
                "INSERT INTO source_spans (id, source_id, relpath, span_type, "
                "content_hash, text_preview, created_at) "
                "VALUES (?, ?, ?, 'paragraph', ?, 'text', '2026-08-06T00:00:00Z')",
                (f"SPAN-{source_id:03d}{i:05d}", source_id, relpath, f"span-hash-{source_id}-{i}"),
            )
            conn.execute(
                "INSERT INTO search_documents (doc_id, record_type, record_id, "
                "source_id, projection_path, title, body, content_hash, "
                "dependency_hash, updated_at) "
                "VALUES (?, 'source_span', ?, ?, ?, 'T', 'B', ?, ?, "
                "'2026-08-06T00:00:00Z')",
                (f"DOC-SPAN-{source_id:03d}{i:05d}", f"SPAN-{source_id:03d}{i:05d}",
                 source_id, relpath, f"span-hash-{source_id}-{i}",
                 f"dep-hash-{source_id}-{i}"),
            )
    return source_id


def _source(paths: cfg.WikiPaths, source_id: int) -> dict:
    with db.connect(paths.state_db) as conn:
        return dict(
            conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        )


def test_relocate_moves_every_denormalized_copy_of_the_path(tmp_path: Path) -> None:
    paths = _vault(tmp_path)
    old = "03_Notes/Vision/3DRec/3D Line Mapping Revisited.md"
    new = "03_Notes/Papers/3DRec/3D Line Mapping Revisited.md"
    source_id = _seed(paths, old, spans=3)

    counts = db.relocate_source(paths.state_db, source_id, new)

    assert counts == {"sources": 1, "source_spans": 3, "search_documents": 3}
    with db.connect(paths.state_db) as conn:
        assert conn.execute(
            "SELECT relpath FROM sources WHERE id = ?", (source_id,)
        ).fetchone()["relpath"] == new
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM source_spans WHERE relpath = ?", (old,)
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM search_documents WHERE projection_path = ?",
            (old,),
        ).fetchone()["n"] == 0


def test_relocate_preserves_content_identity_and_the_derived_closure(
    tmp_path: Path,
) -> None:
    """A move changes location, not content. Nothing may be recompiled or lost."""
    paths = _vault(tmp_path)
    source_id = _seed(paths, "04_Resources/References/paper.md")
    before = _source(paths, source_id)

    db.relocate_source(paths.state_db, source_id, "03_Notes/Papers/paper.md")
    after = _source(paths, source_id)

    for field in (
        "content_hash", "context_id", "l1_status", "l2_status", "l3_status",
        "l4_status", "status", "is_reference", "logical_source_id",
    ):
        assert after[field] == before[field], f"{field} must survive a move"


def test_relocate_keeps_the_cross_device_sync_identity_stable(tmp_path: Path) -> None:
    """`sync_key` is identity, not location.

    It is minted once on INSERT and thereafter matched by equality only —
    nothing reverses it back into a path. Rewriting it on a move would make a
    peer replica see a delete plus an insert rather than one moved row.
    """
    paths = _vault(tmp_path)
    source_id = _seed(paths, "03_Notes/a.md")
    before = _source(paths, source_id)["sync_key"]
    assert before, "the insert trigger should have minted a sync_key"

    db.relocate_source(paths.state_db, source_id, "03_Notes/moved/a.md")

    assert _source(paths, source_id)["sync_key"] == before


def test_relocating_a_zotero_stub_is_allowed_and_keeps_its_logical_id(
    tmp_path: Path,
) -> None:
    """`logical_source_id` identifies the document; `relpath` is where the stub sits.

    `rebind_source` refuses `zotero:` sources because it re-points the EXTERNAL
    PDF, which really is Zotero-managed. Moving the vault-side stub is an
    ordinary vault operation and must not be blocked by that.
    """
    paths = _vault(tmp_path)
    source_id = _seed(paths, "04_Resources/References/zot - .md")

    db.relocate_source(paths.state_db, source_id, "03_Notes/Papers/zot - .md")

    row = _source(paths, source_id)
    assert row["relpath"] == "03_Notes/Papers/zot - .md"
    assert row["logical_source_id"] == "zotero:YACIRUKK"
    assert row["is_reference"] == 1


def test_relocate_is_a_no_op_when_the_path_is_unchanged(tmp_path: Path) -> None:
    paths = _vault(tmp_path)
    source_id = _seed(paths, "03_Notes/a.md")
    assert db.relocate_source(paths.state_db, source_id, "03_Notes/a.md") == {
        "sources": 0, "source_spans": 0, "search_documents": 0,
    }


def test_relocate_rejects_an_unknown_source_and_an_empty_path(tmp_path: Path) -> None:
    paths = _vault(tmp_path)
    source_id = _seed(paths, "03_Notes/a.md")
    with pytest.raises(ValueError, match="not found"):
        db.relocate_source(paths.state_db, 9999, "03_Notes/b.md")
    with pytest.raises(ValueError, match="required"):
        db.relocate_source(paths.state_db, source_id, "   ".strip())


def test_deleting_a_file_marks_the_source_and_keeps_its_knowledge(
    tmp_path: Path,
) -> None:
    """Locked decision D1: delete marks, never destroys.

    An accidental Obsidian delete, or a file moved out of the vault and back,
    must not silently retire the dependency closure. `wiki source rm` stays the
    explicit way to do that.
    """
    paths = _vault(tmp_path)
    source_id = _seed(paths, "03_Notes/a.md", spans=3)

    db.set_source_file_missing(paths.state_db, source_id, True)

    row = _source(paths, source_id)
    assert row["error_reason"] == db.FILE_MISSING_REASON
    for field in ("l1_status", "l2_status", "l3_status", "l4_status"):
        assert row[field] == "done", "knowledge must survive the file going missing"
    with db.connect(paths.state_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM source_spans WHERE source_id = ?", (source_id,)
        ).fetchone()["n"] == 3

    # Restoring the file clears the mark and nothing else.
    db.set_source_file_missing(paths.state_db, source_id, False)
    assert _source(paths, source_id)["error_reason"] is None


def test_clearing_the_missing_mark_does_not_erase_an_unrelated_reason(
    tmp_path: Path,
) -> None:
    """`error_reason` is shared with `empty_file`; clearing must be targeted."""
    paths = _vault(tmp_path)
    source_id = _seed(paths, "03_Notes/a.md")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET error_reason = 'empty_file' WHERE id = ?", (source_id,)
        )

    db.set_source_file_missing(paths.state_db, source_id, False)

    assert _source(paths, source_id)["error_reason"] == "empty_file"


def test_lint_reports_a_registered_source_whose_file_is_gone(tmp_path: Path) -> None:
    """The mark from D1 has to become visible somewhere, or it is not a signal.

    This is also what finally diagnoses the real defect behind a pile of
    `invalid_source_path` errors: on the user's vault, 48 Atom errors all traced
    to ONE source row registered at a path that no longer exists. Blaming the 48
    atoms was the wrong end of the problem.
    """
    from curator import lint

    paths = _vault(tmp_path)
    (tmp_path / "03_Notes").mkdir(parents=True, exist_ok=True)
    present = tmp_path / "03_Notes/present.md"
    present.write_text("# Here\n", encoding="utf-8")
    _seed(paths, "03_Notes/present.md", spans=1)
    gone_id = _seed(paths, "03_Notes/gone.md", spans=1)

    issues = lint.check_missing_source_files(paths)

    assert len(issues) == 1, [i.message for i in issues]
    issue = issues[0]
    assert issue.check == lint.CheckId.MISSING_SOURCE_FILE
    assert issue.context["source_id"] == gone_id
    assert issue.context["marked_missing"] is False
    assert issue.fixable is False, "only the user can decide restore vs retire"
    assert f"wiki source rm {gone_id}" in issue.suggestion

    # Once the delete has been recorded, the finding says so.
    db.set_source_file_missing(paths.state_db, gone_id, True)
    marked = lint.check_missing_source_files(paths)[0]
    assert marked.context["marked_missing"] is True
    assert "marked `file_missing`" in marked.message


def test_lint_does_not_report_a_file_stored_in_the_other_unicode_form(
    tmp_path: Path,
) -> None:
    """A decomposed filename on disk vs a precomposed one in the DB is one file.

    Same class as the v0.44.1 lint fix: declaring it missing here would mark a
    perfectly present source as gone.
    """
    import unicodedata

    from curator import lint

    paths = _vault(tmp_path)
    stem = "Camera Pose Estimation using Plücker Coordinates"
    (tmp_path / "03_Notes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "03_Notes" / f"{unicodedata.normalize('NFD', stem)}.md").write_text(
        "# Paper\n", encoding="utf-8"
    )
    _seed(paths, f"03_Notes/{unicodedata.normalize('NFC', stem)}.md", spans=1)

    assert lint.check_missing_source_files(paths) == []
