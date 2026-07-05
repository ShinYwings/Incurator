"""Regression tests for Phase A S1 backend fixes.

G01-1: remove_source cascade deletes dag_edges/ingest_jobs/job_events
G03-1: sources LWW uses COALESCE(last_ingested, added_at) for pending rows
G04-1: _find_changed_nodes uses DB page hashes instead of never-written frontmatter field
G06-1: dead code after unconditional return in run_query removed
G06-3: insert_query_trace created_at preserved across action appends
"""

from __future__ import annotations

from pathlib import Path

from curator import db
from curator.db_sync import export_knowledge, import_knowledge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_source(state_db: Path, relpath: str = "04_Resources/a.md") -> int:
    db.init_db(state_db)
    with db.connect(state_db) as conn:
        sid = conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, context_id,"
            " l1_status, l2_status, l3_status)"
            " VALUES (?, 'h', 'md', 10, '2026-01-01T00:00:00Z', 'CTX-001',"
            " 'done', 'done', 'done')",
            (relpath,),
        ).lastrowid
    assert sid is not None
    return sid


def _add_dag_edge(state_db: Path, source_id: int) -> None:
    with db.connect(state_db) as conn:
        conn.execute(
            "INSERT INTO dag_edges (id, from_id, to_id, edge_type, source_id, created_at)"
            " VALUES ('CTX-001:ATM-001', 'CTX-001', 'ATM-001', 'extracted_from', ?, '2026-01-01T00:00:00Z')",
            (source_id,),
        )


def _add_ingest_job(state_db: Path, source_id: int) -> int:
    with db.connect(state_db) as conn:
        jid = conn.execute(
            "INSERT INTO ingest_jobs (source_id, state, created_at)"
            " VALUES (?, 'done', '2026-01-01T00:00:00Z')",
            (source_id,),
        ).lastrowid
    assert jid is not None
    return jid


def _add_job_event(state_db: Path, job_id: int) -> None:
    with db.connect(state_db) as conn:
        conn.execute(
            "INSERT INTO job_events (job_id, seq, kind, data, at)"
            " VALUES (?, 1, 'status', '{}', '2026-01-01T00:00:00Z')",
            (job_id,),
        )


# ---------------------------------------------------------------------------
# G01-1: remove_source cascade
# ---------------------------------------------------------------------------

class TestRemoveSourceCascade:
    def test_removes_dag_edges_before_deleting_source(self, tmp_path: Path) -> None:
        """remove_source must delete dag_edges referencing the source to avoid FK error."""
        from curator.ingest_raw import remove_source
        from curator import config as cfg

        paths = cfg.WikiPaths(tmp_path)
        state_db = paths.state_db
        sid = _init_source(state_db)
        _add_dag_edge(state_db, sid)

        ok, _ = remove_source(paths, sid)
        assert ok

        with db.connect(state_db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM dag_edges WHERE source_id=?", (sid,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM sources WHERE id=?", (sid,)).fetchone()[0] == 0
            tombstone = conn.execute(
                "SELECT record_id FROM deleted_records "
                "WHERE table_name = 'sources'"
            ).fetchone()
        assert tombstone is not None
        assert tombstone[0] == "vault:04_Resources/a.md"

    def test_removes_ingest_jobs_and_events_before_deleting_source(self, tmp_path: Path) -> None:
        from curator.ingest_raw import remove_source
        from curator import config as cfg

        paths = cfg.WikiPaths(tmp_path)
        state_db = paths.state_db
        sid = _init_source(state_db)
        jid = _add_ingest_job(state_db, sid)
        _add_job_event(state_db, jid)

        ok, _ = remove_source(paths, sid)
        assert ok

        with db.connect(state_db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM job_events WHERE job_id=?", (jid,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM ingest_jobs WHERE source_id=?", (sid,)).fetchone()[0] == 0

    def test_no_integrity_error_on_compiled_source(self, tmp_path: Path) -> None:
        """The old code raised IntegrityError; this test would have caught the regression."""
        from curator.ingest_raw import remove_source
        from curator import config as cfg

        paths = cfg.WikiPaths(tmp_path)
        state_db = paths.state_db
        sid = _init_source(state_db)
        _add_dag_edge(state_db, sid)
        jid = _add_ingest_job(state_db, sid)
        _add_job_event(state_db, jid)

        # Must not raise sqlite3.IntegrityError
        ok, msg = remove_source(paths, sid)
        assert ok
        assert str(sid) in msg


# ---------------------------------------------------------------------------
# G03-1: sources LWW uses COALESCE(last_ingested, added_at)
# ---------------------------------------------------------------------------

class TestSourcesLWWCoalesce:
    def test_pending_source_included_in_since_export(self, tmp_path: Path) -> None:
        """A pending source (last_ingested=NULL) must appear in since-filtered export."""
        src_db = tmp_path / "src.sqlite"
        dst_db = tmp_path / "dst.sqlite"
        db.init_db(src_db)
        db.init_db(dst_db)

        with db.connect(src_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at,"
                " context_id, l1_status, l2_status, l3_status)"
                " VALUES ('04_Resources/p.md', 'h', 'md', 10, '2026-06-01T10:00:00Z',"
                " 'CTX-001', 'pending', 'pending', 'pending')",
            )

        out = tmp_path / "export.jsonl"
        # Export with since=2026-06-01 — pending source has added_at after this
        export_knowledge(src_db, out, since="2026-06-01T00:00:00Z")
        import_knowledge(dst_db, out)

        with db.connect(dst_db) as conn:
            row = conn.execute("SELECT relpath FROM sources WHERE relpath=?", ("04_Resources/p.md",)).fetchone()
        assert row is not None, "pending source must be included in since-filtered export"

    def test_pending_source_lww_upserts_newer_metadata(self, tmp_path: Path) -> None:
        """On import, a peer's newer pending source metadata must win the LWW comparison."""
        src_db = tmp_path / "src.sqlite"
        dst_db = tmp_path / "dst.sqlite"
        db.init_db(src_db)
        db.init_db(dst_db)

        # dst has a pending source with added_at=earlier
        with db.connect(dst_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at,"
                " context_id, l1_status, l2_status, l3_status, domain)"
                " VALUES ('04_Resources/p.md', 'h', 'md', 10, '2026-06-01T08:00:00Z',"
                " 'CTX-001', 'pending', 'pending', 'pending', 'old-domain')",
            )

        # src has same source with added_at=later + updated domain
        with db.connect(src_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at,"
                " context_id, l1_status, l2_status, l3_status, domain)"
                " VALUES ('04_Resources/p.md', 'h', 'md', 10, '2026-06-01T12:00:00Z',"
                " 'CTX-001', 'pending', 'pending', 'pending', 'new-domain')",
            )

        out = tmp_path / "export.jsonl"
        export_knowledge(src_db, out)
        import_knowledge(dst_db, out)

        with db.connect(dst_db) as conn:
            row = conn.execute("SELECT domain FROM sources WHERE relpath=?", ("04_Resources/p.md",)).fetchone()
        assert row is not None
        assert row["domain"] == "new-domain", "LWW must prefer the source with the newer added_at"


# ---------------------------------------------------------------------------
# G04-1: _find_changed_nodes uses DB page hashes
# ---------------------------------------------------------------------------

class TestFindChangedNodesDbHash:
    def test_unchanged_page_not_reported_when_db_hash_matches(self, tmp_path: Path) -> None:
        """A page whose file hash matches the DB store must not appear in changed list."""
        from curator.sync import _find_changed_nodes, update_all_page_hashes
        from curator import config as cfg

        paths = cfg.WikiPaths(tmp_path)
        state_db = paths.state_db
        db.init_db(state_db)

        ctx_dir = tmp_path / ".curator" / "Collections" / "01_Contexts"
        ctx_dir.mkdir(parents=True)
        md = ctx_dir / "CTX-00000001.md"
        md.write_text("---\nid: CTX-00000001\n---\nbody\n", encoding="utf-8")

        update_all_page_hashes(paths)  # stamp the current hash into DB

        changed = _find_changed_nodes(paths)
        assert "CTX-00000001" not in changed

    def test_modified_page_reported_changed(self, tmp_path: Path) -> None:
        """A page modified after the DB hash was stamped must appear in changed list."""
        from curator.sync import _find_changed_nodes, update_all_page_hashes
        from curator import config as cfg

        paths = cfg.WikiPaths(tmp_path)
        state_db = paths.state_db
        db.init_db(state_db)

        ctx_dir = tmp_path / ".curator" / "Collections" / "01_Contexts"
        ctx_dir.mkdir(parents=True)
        md = ctx_dir / "CTX-00000002.md"
        md.write_text("---\nid: CTX-00000002\n---\nbody v1\n", encoding="utf-8")

        update_all_page_hashes(paths)  # stamp v1 hash

        md.write_text("---\nid: CTX-00000002\n---\nbody v2 modified\n", encoding="utf-8")

        changed = _find_changed_nodes(paths)
        assert "CTX-00000002" in changed

    def test_new_page_with_no_db_hash_reported_changed(self, tmp_path: Path) -> None:
        """A page with no DB hash entry (new file) must be reported as changed."""
        from curator.sync import _find_changed_nodes
        from curator import config as cfg

        paths = cfg.WikiPaths(tmp_path)
        state_db = paths.state_db
        db.init_db(state_db)

        ctx_dir = tmp_path / ".curator" / "Collections" / "01_Contexts"
        ctx_dir.mkdir(parents=True)
        md = ctx_dir / "CTX-00000003.md"
        md.write_text("---\nid: CTX-00000003\n---\nnew\n", encoding="utf-8")

        # No update_all_page_hashes — DB has no entry for this file

        changed = _find_changed_nodes(paths)
        assert "CTX-00000003" in changed


# ---------------------------------------------------------------------------
# G06-1: dead code in run_query removed
# ---------------------------------------------------------------------------

class TestRunQueryDeadCodeRemoved:
    def test_dead_symbols_not_exported_from_query_module(self) -> None:
        """The dead synthesis prompt and legacy search block symbols must be gone."""
        import curator.query as qm
        assert not hasattr(qm, "_build_synthesis_user_prompt"), \
            "_build_synthesis_user_prompt must be removed (dead code)"
        assert not hasattr(qm, "SYNTHESIS_SYSTEM_PROMPT"), \
            "SYNTHESIS_SYSTEM_PROMPT must be removed (dead code)"
        assert not hasattr(qm, "MAX_SYNTHESIS_SOURCE_CHARS"), \
            "MAX_SYNTHESIS_SOURCE_CHARS must be removed (dead code)"


# ---------------------------------------------------------------------------
# G06-3: insert_query_trace preserves created_at
# ---------------------------------------------------------------------------

class TestInsertQueryTraceCreatedAt:
    def test_created_at_preserved_on_re_insert(self, tmp_path: Path) -> None:
        """Re-persisting an existing trace with created_at= must not clobber the timestamp."""
        state_db = tmp_path / "state.sqlite"
        db.init_db(state_db)

        original_ts = "2026-01-01T10:00:00Z"
        tid = db.insert_query_trace(
            state_db,
            route="local",
            question_hash="qh-001",
            created_at=original_ts,
        )

        # Simulate _append_context_action re-persisting with the original timestamp
        db.insert_query_trace(
            state_db,
            trace_id=tid,
            route="local",
            question_hash="qh-001",
            retrieval_trace={"actions": [{"type": "expand"}]},
            created_at=original_ts,
        )

        with db.connect(state_db) as conn:
            row = conn.execute(
                "SELECT created_at FROM query_traces WHERE trace_id=?", (tid,)
            ).fetchone()
        assert row is not None
        assert row["created_at"] == original_ts, \
            "created_at must be preserved when re-persisting an existing trace"

    def test_new_trace_gets_current_timestamp_when_none_passed(self, tmp_path: Path) -> None:
        """A new trace with no created_at arg must get a current timestamp (not None/empty)."""
        state_db = tmp_path / "state.sqlite"
        db.init_db(state_db)

        tid = db.insert_query_trace(state_db, route="auto", question_hash="qh-002")

        with db.connect(state_db) as conn:
            row = conn.execute(
                "SELECT created_at FROM query_traces WHERE trace_id=?", (tid,)
            ).fetchone()
        assert row is not None
        assert row["created_at"] and row["created_at"] != ""
