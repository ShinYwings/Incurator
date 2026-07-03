"""Syncthing auto-sync (one-writer-per-file) — backend tests.

Covers the structural design locked in
`.agents/plans/syncthing_auto_sync.md`:
- P1: config block, device-local sync_state.json, _DEVICE_LOCAL_COLUMNS, .stignore.
- P2: export_for_device / import_all_peers / detect_conflict_files, the dry-run
  regression lock, offline edit/delete tie-breaks, reference-mode path preservation,
  no-self-import, incremental --since.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import config as cfg
from curator import db, db_sync


# ---------------------------------------------------------------------------
# P1 — config / state / constants / .stignore
# ---------------------------------------------------------------------------


class TestAutoSyncConfig:
    def test_default_config_has_auto_sync_block(self) -> None:
        block = cfg.DEFAULT_CONFIG.get("auto_sync")
        assert isinstance(block, dict)
        # Default-on since v0.30.0 (opt-out): every trigger being opt-in let a
        # CLI-primary device silently never export ("5 vs 31 sources" incident).
        assert block["enabled"] is True
        assert block["dir"] == "sync"
        assert "debounce_ms" in block
        assert "poll_ms" in block


class TestSyncState:
    def test_round_trip(self, tmp_path: Path) -> None:
        internal = tmp_path / ".curator"
        internal.mkdir()
        db_sync.write_sync_state(internal, {"device_id": "abc", "peers": {}})
        assert db_sync.read_sync_state(internal)["device_id"] == "abc"

    def test_read_missing_returns_empty(self, tmp_path: Path) -> None:
        assert db_sync.read_sync_state(tmp_path / ".curator") == {}

    def test_get_device_id_generates_and_persists(self, tmp_path: Path) -> None:
        internal = tmp_path / ".curator"
        internal.mkdir()
        first = db_sync.get_device_id(internal)
        assert first and len(first) == 12
        # Stable across calls (persisted).
        assert db_sync.get_device_id(internal) == first
        assert db_sync.read_sync_state(internal)["device_id"] == first


class TestConstantsAndIgnore:
    def test_source_locators_are_not_device_local_columns(self) -> None:
        assert "sources" not in db_sync._DEVICE_LOCAL_COLUMNS

    def test_stignore_template_excludes_sync_state(self) -> None:
        template = (
            Path(cfg.__file__).parent / "workspace" / "templates" / "stignore.template"
        )
        text = template.read_text(encoding="utf-8")
        assert "sync_state.json" in text
        # The synced knowledge files must NOT be excluded.
        assert ".curator/sync/\n" not in text and ".curator/sync/*" not in text


# ---------------------------------------------------------------------------
# Shared fixtures for P2
# ---------------------------------------------------------------------------


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A minimal initialized .curator dir with an empty state DB."""
    internal = tmp_path / ".curator"
    internal.mkdir()
    db.init_db(internal / "state.sqlite")
    return tmp_path


def _internal(vault: Path) -> Path:
    return vault / ".curator"


def _db(vault: Path) -> Path:
    return vault / ".curator" / "state.sqlite"


def _add_atom(db_path: Path, atom_id: str, name: str, ts: str) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO atoms"
            " (id, name, parent_source, claim_type, one_liner, last_updated)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (atom_id, name, "01_Contexts/CTX-1.md", "fact", name, ts),
        )


# ---------------------------------------------------------------------------
# P2 — export_for_device / import_all_peers / detect_conflict_files
# ---------------------------------------------------------------------------


class TestExportForDevice:
    def test_creates_dev_named_file(self, vault: Path) -> None:
        _add_atom(_db(vault), "ATM-00000001", "A", "2026-06-01T00:00:00Z")
        out = db_sync.export_for_device(_internal(vault), _db(vault))
        assert out.parent == _internal(vault) / "sync"
        did = db_sync.get_device_id(_internal(vault))
        assert out.name == f"dev-{did}.jsonl"
        assert out.exists()

    def test_records_last_export_ts(self, vault: Path) -> None:
        db_sync.export_for_device(_internal(vault), _db(vault))
        assert db_sync.read_sync_state(_internal(vault)).get("last_export_ts")


class TestImportAllPeers:
    def test_dry_run_matches_real_delta(self, vault: Path) -> None:
        """REGRESSION LOCK for the reverted hash-guard bug: dry-run must report the
        exact same insert count that a real import then applies."""
        # Source device exports a full snapshot.
        src = tmp_src(vault, "ATM-00000001", "A", "2026-06-01T00:00:00Z")
        # Place it as a peer file in a fresh target vault.
        peer_name = "dev-peerAAAA.jsonl"
        (_internal(vault) / "sync").mkdir(parents=True, exist_ok=True)
        (_internal(vault) / "sync" / peer_name).write_text(
            src.read_text(encoding="utf-8"), encoding="utf-8"
        )

        dry = db_sync.import_all_peers(_internal(vault), _db(vault), dry_run=True)
        real = db_sync.import_all_peers(_internal(vault), _db(vault), dry_run=False)
        assert dry[peer_name].inserted == real[peer_name].inserted
        assert real[peer_name].inserted == 1

    def test_never_imports_own_file(self, vault: Path) -> None:
        _add_atom(_db(vault), "ATM-00000001", "A", "2026-06-01T00:00:00Z")
        own = db_sync.export_for_device(_internal(vault), _db(vault))
        assert own.exists()
        results = db_sync.import_all_peers(_internal(vault), _db(vault))
        assert own.name not in results  # own snapshot is never re-imported

    def test_skips_unchanged_peer_on_second_run(self, vault: Path) -> None:
        peer = _make_peer(vault, "dev-peerBBBB.jsonl", "ATM-00000002", "B", "2026-06-02T00:00:00Z")
        assert peer.name in db_sync.import_all_peers(_internal(vault), _db(vault))
        # No mtime change → skipped (not re-imported).
        assert peer.name not in db_sync.import_all_peers(_internal(vault), _db(vault))


class TestReferenceModePreservation:
    def test_portable_external_ref_merges_normally(self, vault: Path) -> None:
        dbp = _db(vault)
        # Local reference source with a device-specific path.
        with db.connect(dbp) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes,"
                " added_at, last_ingested, external_ref, is_reference)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                ("04_Resources/p.pdf", "h1", "pdf", 10, "2026-06-01T00:00:00Z",
                 "2026-06-01T00:00:00Z", "@papers/p.pdf"),
            )
            sid = conn.execute("SELECT id FROM sources").fetchone()[0]

        # Peer file: newer row, same id, portable locator + new domain.
        peer_dir = _internal(vault) / "sync"
        peer_dir.mkdir(parents=True, exist_ok=True)
        import json as _json
        peer = peer_dir / "dev-peerCCCC.jsonl"
        peer.write_text(
            _json.dumps({"type": "header", "schema_version": db_sync.SCHEMA_VERSION, "exported_at": "x"}) + "\n"
            + _json.dumps({"type": "row", "table": "sources", "row": {
                "id": sid, "relpath": "04_Resources/p.pdf", "content_hash": "h2",
                "file_type": "pdf", "bytes": 10, "added_at": "2026-06-01T00:00:00Z",
                "last_ingested": "2026-06-09T00:00:00Z", "status": "curated",
                "updated_at": "2026-08-09T00:00:00.000Z",
                "external_ref": "@papers/moved/p.pdf", "is_reference": 1,
                "domain": "peer-domain",
            }}) + "\n",
            encoding="utf-8",
        )

        db_sync.import_all_peers(_internal(vault), _db(vault))
        with db.connect(dbp) as conn:
            r = conn.execute("SELECT external_ref, domain FROM sources WHERE id=?", (sid,)).fetchone()
        assert r["external_ref"] == "@papers/moved/p.pdf"
        assert r["domain"] == "peer-domain"


class TestTombstoneTieBreak:
    def test_edit_newer_than_delete_survives(self, vault: Path) -> None:
        dbp = _db(vault)
        # Local: atom edited at T2.
        _add_atom(dbp, "ATM-X", "edited", "2026-06-02T00:00:00Z")
        # Peer: tombstone for same atom at T1 < T2.
        peer = _peer_with_tombstone(vault, "dev-peerDDDD.jsonl", "atoms", "ATM-X", "2026-06-01T00:00:00Z")
        assert peer.exists()
        db_sync.import_all_peers(_internal(vault), dbp)
        with db.connect(dbp) as conn:
            assert conn.execute("SELECT 1 FROM atoms WHERE id='ATM-X'").fetchone() is not None

    def test_delete_newer_than_edit_wins(self, vault: Path) -> None:
        dbp = _db(vault)
        _add_atom(dbp, "ATM-Y", "edited", "2026-06-01T00:00:00Z")
        peer = _peer_with_tombstone(vault, "dev-peerEEEE.jsonl", "atoms", "ATM-Y", "2026-06-02T00:00:00Z")
        assert peer.exists()
        db_sync.import_all_peers(_internal(vault), dbp)
        with db.connect(dbp) as conn:
            assert conn.execute("SELECT 1 FROM atoms WHERE id='ATM-Y'").fetchone() is None


class TestConflictFiles:
    def test_detect_and_excluded_from_peers(self, vault: Path) -> None:
        sync_dir = _internal(vault) / "sync"
        sync_dir.mkdir(parents=True, exist_ok=True)
        # A normal peer file + a Syncthing conflict file.
        _make_peer(vault, "dev-peerFFFF.jsonl", "ATM-00000009", "Z", "2026-06-01T00:00:00Z")
        conflict = sync_dir / "dev-peerFFFF.sync-conflict-20260607-120000-ABCDEFG.jsonl"
        conflict.write_text("{}\n", encoding="utf-8")

        found = db_sync.detect_conflict_files(_internal(vault))
        assert conflict in found
        # Conflict files are NOT imported by import_all_peers (handled separately).
        results = db_sync.import_all_peers(_internal(vault), _db(vault))
        assert conflict.name not in results


# --- small builders -------------------------------------------------------


def tmp_src(vault: Path, atom_id: str, name: str, ts: str) -> Path:
    """Build a standalone source DB with one atom, return its full export file."""
    src_db = vault / "src.sqlite"
    db.init_db(src_db)
    _add_atom(src_db, atom_id, name, ts)
    out = vault / "src-export.jsonl"
    db_sync.export_knowledge(src_db, out)
    return out


def _make_peer(vault: Path, filename: str, atom_id: str, name: str, ts: str) -> Path:
    """Create a peer export file under .curator/sync/ containing one atom."""
    out = tmp_src(vault, atom_id, name, ts)
    sync_dir = _internal(vault) / "sync"
    sync_dir.mkdir(parents=True, exist_ok=True)
    peer = sync_dir / filename
    peer.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    return peer


def _peer_with_tombstone(vault: Path, filename: str, table: str, rid: str, ts: str) -> Path:
    import json as _json
    sync_dir = _internal(vault) / "sync"
    sync_dir.mkdir(parents=True, exist_ok=True)
    peer = sync_dir / filename
    peer.write_text(
        _json.dumps({"type": "header", "schema_version": db_sync.SCHEMA_VERSION, "exported_at": "x"}) + "\n"
        + _json.dumps({"type": "row", "table": "deleted_records", "row": {
            "table_name": table, "record_id": rid, "deleted_at": ts,
        }}) + "\n",
        encoding="utf-8",
    )
    return peer


# ---------------------------------------------------------------------------
# P3 — autosync orchestrator
# ---------------------------------------------------------------------------


class TestAutosync:
    def test_imports_peer_and_exports_self(self, vault: Path) -> None:
        _make_peer(vault, "dev-peerGGGG.jsonl", "ATM-0001", "P", "2026-06-03T00:00:00Z")
        res = db_sync.autosync(_internal(vault), _db(vault))
        assert res.imported["dev-peerGGGG.jsonl"].inserted == 1
        # Exported self because the import changed the local DB.
        did = db_sync.get_device_id(_internal(vault))
        assert res.exported == f"dev-{did}.jsonl"
        assert (_internal(vault) / "sync" / res.exported).exists()

    def test_noop_when_nothing_changed(self, vault: Path) -> None:
        # First pass exports baseline.
        db_sync.export_for_device(_internal(vault), _db(vault))
        # No peers, no local change → no re-export.
        res = db_sync.autosync(_internal(vault), _db(vault))
        assert res.exported is None
        assert res.imported == {}

    def test_dry_run_writes_nothing(self, vault: Path) -> None:
        _make_peer(vault, "dev-peerHHHH.jsonl", "ATM-0002", "Q", "2026-06-03T00:00:00Z")
        res = db_sync.autosync(_internal(vault), _db(vault), dry_run=True)
        assert res.dry_run is True
        with db.connect(_db(vault)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0] == 0

    def test_conflict_file_merged_and_archived(self, vault: Path) -> None:
        # A conflict file carrying one atom.
        sync_dir = _internal(vault) / "sync"
        sync_dir.mkdir(parents=True, exist_ok=True)
        src = tmp_src(vault, "ATM-0003", "C", "2026-06-04T00:00:00Z")
        conflict = sync_dir / "dev-peerIIII.sync-conflict-20260607-120000-ABCDEFG.jsonl"
        conflict.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        res = db_sync.autosync(_internal(vault), _db(vault))
        assert conflict.name in res.conflicts
        # Atom merged in.
        with db.connect(_db(vault)) as conn:
            assert conn.execute("SELECT 1 FROM atoms WHERE id='ATM-0003'").fetchone() is not None
        # Conflict file moved out of the synced dir.
        assert not conflict.exists()
        assert (_internal(vault) / "runtime" / "sync_conflicts" / conflict.name).exists()


class TestTwoDeviceE2E:
    """Full Syncthing-style round trip across two independent vaults."""

    def _vault(self, base: Path, name: str) -> Path:
        v = base / name
        (v / ".curator").mkdir(parents=True)
        db.init_db(v / ".curator" / "state.sqlite")
        return v

    def _sync_from_to(self, src: Path, dst: Path) -> None:
        """Simulate Syncthing copying every dev-*.jsonl from src into dst."""
        src_sync = src / ".curator" / "sync"
        dst_sync = dst / ".curator" / "sync"
        dst_sync.mkdir(parents=True, exist_ok=True)
        if not src_sync.is_dir():
            return
        for f in src_sync.glob("dev-*.jsonl"):
            (dst_sync / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    def test_bidirectional_merge_no_loss(self, tmp_path: Path) -> None:
        A = self._vault(tmp_path, "A")
        B = self._vault(tmp_path, "B")
        dbA, dbB = A / ".curator" / "state.sqlite", B / ".curator" / "state.sqlite"
        intA, intB = A / ".curator", B / ".curator"

        # Each device creates a distinct atom offline.
        _add_atom(dbA, "ATM-A1", "from-A", "2026-06-01T00:00:00Z")
        _add_atom(dbB, "ATM-B1", "from-B", "2026-06-01T00:00:00Z")

        # A exports, Syncthing carries A's file to B, B autosyncs.
        db_sync.autosync(intA, dbA)
        self._sync_from_to(A, B)
        db_sync.autosync(intB, dbB)

        # Syncthing carries B's (now updated) file back to A, A autosyncs.
        self._sync_from_to(B, A)
        db_sync.autosync(intA, dbA)

        for dbp in (dbA, dbB):
            with db.connect(dbp) as conn:
                ids = {r[0] for r in conn.execute("SELECT id FROM atoms")}
            assert {"ATM-A1", "ATM-B1"} <= ids  # neither device lost data

    def test_concurrent_edit_newer_wins(self, tmp_path: Path) -> None:
        A = self._vault(tmp_path, "A")
        B = self._vault(tmp_path, "B")
        dbA, dbB = A / ".curator" / "state.sqlite", B / ".curator" / "state.sqlite"
        intA, intB = A / ".curator", B / ".curator"

        # Same atom edited on both devices; B's edit is newer.
        _add_atom(dbA, "ATM-X", "A-version", "2026-06-01T00:00:00Z")
        _add_atom(dbB, "ATM-X", "B-version", "2026-06-05T00:00:00Z")

        db_sync.autosync(intB, dbB)
        self._sync_from_to(B, A)
        db_sync.autosync(intA, dbA)

        with db.connect(dbA) as conn:
            name = conn.execute("SELECT name FROM atoms WHERE id='ATM-X'").fetchone()[0]
        assert name == "B-version"  # newer edit won on A

    def test_reimport_is_stable_noop(self, tmp_path: Path) -> None:
        """Repeated autosync with no new data must not loop or rewrite endlessly."""
        A = self._vault(tmp_path, "A")
        B = self._vault(tmp_path, "B")
        dbA, dbB = A / ".curator" / "state.sqlite", B / ".curator" / "state.sqlite"
        intA, intB = A / ".curator", B / ".curator"

        _add_atom(dbA, "ATM-A1", "from-A", "2026-06-01T00:00:00Z")
        db_sync.autosync(intA, dbA)
        self._sync_from_to(A, B)
        db_sync.autosync(intB, dbB)
        # Second pass on B with the same peer file: nothing imported, nothing exported.
        res2 = db_sync.autosync(intB, dbB)
        assert all(s.inserted == 0 and s.updated == 0 for s in res2.imported.values())
        assert res2.exported is None


class TestCompositePkTombstone:
    def test_composite_pk_tombstone_warns_not_silent(self, vault: Path, caplog) -> None:
        """A tombstone for a composite-PK table cannot delete by single record_id;
        it must log a warning rather than fail silently (review #3)."""
        peer = _peer_with_tombstone(
            vault, "dev-peerJJJJ.jsonl", "source_pages", "some-id", "2026-06-02T00:00:00Z"
        )
        assert peer.exists()
        import logging
        with caplog.at_level(logging.WARNING, logger="curator.db_sync"):
            db_sync.import_all_peers(_internal(vault), _db(vault))
        assert any("composite-PK" in r.message for r in caplog.records)


class TestLocalUnexported:
    def test_true_when_never_exported(self, vault: Path) -> None:
        _add_atom(_db(vault), "ATM-Z", "z", "2026-06-01T00:00:00Z")
        assert db_sync.local_has_unexported_changes(_internal(vault), _db(vault)) is True

    def test_false_after_export(self, vault: Path) -> None:
        _add_atom(_db(vault), "ATM-Z", "z", "2026-06-01T00:00:00Z")
        db_sync.export_for_device(_internal(vault), _db(vault))
        assert db_sync.local_has_unexported_changes(_internal(vault), _db(vault)) is False
