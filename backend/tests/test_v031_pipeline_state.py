from pathlib import Path

from curator import config as cfg
from curator import db
from curator import ingest_raw


def test_reference_stub_resolves_emitted_zotero_attachment_key(
    tmp_path: Path, monkeypatch
) -> None:
    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)
    stub = tmp_path / "04_Resources" / "paper.md"
    stub.parent.mkdir(parents=True)
    stub.write_text(
        "---\n"
        "type: reference\n"
        "zotero_attachment_key: ATTKEY\n"
        "---\n"
        "External source reference.\n",
        encoding="utf-8",
    )
    pdf = tmp_path / "external.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def fake_resolve(key, _paths):
        assert key == "ATTKEY"
        return {"ok": True, "path": str(pdf)}

    monkeypatch.setattr("curator.zotero_tools.resolve_pdf", fake_resolve)

    assert ingest_raw._resolve_reference_source(paths, stub) == pdf


def test_recover_stale_job_resets_source_layer_to_pending(tmp_path: Path) -> None:
    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources "
            "(id, relpath, content_hash, file_type, bytes, added_at, l2_status) "
            "VALUES (1, '03_Notes/n.md', 'h', 'md', 1, datetime('now'), 'running')"
        )
        conn.execute(
            "INSERT INTO ingest_jobs "
            "(source_id, job_type, state, created_at) "
            "VALUES (1, 'l2_atoms', 'running', datetime('now'))"
        )

    assert db.recover_stale_jobs(paths.state_db) == 1

    with db.connect(paths.state_db) as conn:
        job_state = conn.execute(
            "SELECT state FROM ingest_jobs"
        ).fetchone()[0]
        l2_status = conn.execute(
            "SELECT l2_status FROM sources WHERE id=1"
        ).fetchone()[0]
    assert job_state == "queued"
    assert l2_status == "pending"
