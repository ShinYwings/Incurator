"""An import that drops a row must never report it as inserted.

B2 / sync_db-1, the milestone's stated hard condition. `_do_insert` used
`INSERT OR IGNORE`, so a row that violated a constraint was silently discarded
while `_lw_upsert` still returned "inserted" and the caller incremented
`stats.inserted`. The user is then told a peer's data arrived when it did not,
and `wiki db import` reports a clean run over a silent loss.

`INSERT OR IGNORE` is load-bearing, though not for the obvious reason: callers
SELECT by transport key first, so an identical row never reaches the INSERT
twice. What it absorbs is a constraint the key lookup cannot see — concretely
`sources.relpath UNIQUE` when the transport key is `sync_key`, which is what two
devices registering the same file independently produces. The fix therefore
cannot drop OR IGNORE; it has to separate "the database took it" from "the
database refused it".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import db, db_sync

GOOD = {
    "id": "ATM-good",
    "name": "good",
    "parent_source": "01_Contexts/CTX-1.md",
    "claim_type": "fact",
    "one_liner": "good",
    "last_updated": "2099-01-01T00:00:00Z",
}
# NOT NULL on claim_type — what a truncated or malformed peer export looks like.
REJECTED = {**GOOD, "id": "ATM-bad", "claim_type": None}


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "state.sqlite"
    db.init_db(p)
    return p


def _count(db_path: Path) -> int:
    with db.connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0])


def test_a_rejected_row_is_not_reported_as_inserted(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        result = db_sync._lw_upsert(conn, "atoms", dict(REJECTED), primary_keys=["id"])

    assert _count(db_path) == 0, "fixture wrong: the row was actually stored"
    assert result != "inserted", (
        "a row the database refused was reported as inserted, so the import "
        "summary claims data arrived that was silently dropped"
    )


def test_a_genuine_insert_is_still_reported_as_inserted(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        result = db_sync._lw_upsert(conn, "atoms", dict(GOOD), primary_keys=["id"])
    assert result == "inserted"
    assert _count(db_path) == 1


def test_reinserting_an_identical_row_is_not_an_error(db_path: Path) -> None:
    """Re-importing the same snapshot must stay a no-op, not become a rejection.

    This exercises the LWW path, not `INSERT OR IGNORE`: the second call's
    SELECT finds the row and never reaches the INSERT. It matters because
    autosync re-imports full peer snapshots continuously, so a regression here
    would report `rejected` on every steady-state pass.
    """
    with db.connect(db_path) as conn:
        db_sync._lw_upsert(conn, "atoms", dict(GOOD), primary_keys=["id"])
    with db.connect(db_path) as conn:
        result = db_sync._lw_upsert(conn, "atoms", dict(GOOD), primary_keys=["id"])
    assert result in {"skipped", "updated"}
    assert _count(db_path) == 1


def test_one_rejected_row_does_not_abort_the_rest_of_the_import(
    tmp_path: Path, db_path: Path
) -> None:
    """B2: a bad peer file must not wedge the pass — the good rows still land."""
    # Build a real peer file, then append the malformed row a truncated or
    # partially-written export would contain.
    donor = tmp_path / "donor.sqlite"
    db.init_db(donor)
    export = tmp_path / "peer.jsonl"
    db_sync.export_knowledge(donor, export)
    with export.open("a", encoding="utf-8") as fh:
        for row in (REJECTED, GOOD):
            fh.write(
                db_sync.json.dumps(
                    {"type": "row", "table": "atoms", "row": row}, default=str
                )
                + "\n"
            )

    stats = db_sync.import_knowledge(db_path, export)

    assert _count(db_path) == 1, "the good row was lost along with the bad one"
    assert stats.inserted == 1, (
        f"import reported {stats.inserted} inserted but only 1 row landed"
    )


BAD_SOURCE = {
    "id": 1,
    "relpath": "04_Resources/a.md",
    "content_hash": None,  # NOT NULL — a truncated peer export
    "file_type": "pdf",
    "bytes": 0,
    "added_at": "2099-01-01T00:00:00Z",
    "sync_key": "k-bad",
    "updated_at": "2099-01-01T00:00:00Z",
}


def _peer_file(tmp_path: Path, *rows: tuple[str, dict]) -> Path:
    donor = tmp_path / "donor.sqlite"
    db.init_db(donor)
    export = tmp_path / "peer.jsonl"
    db_sync.export_knowledge(donor, export)
    with export.open("a", encoding="utf-8") as fh:
        for table, row in rows:
            fh.write(
                db_sync.json.dumps(
                    {"type": "row", "table": table, "row": row}, default=str
                )
                + "\n"
            )
    return export


def test_a_refused_source_row_does_not_abort_the_whole_import(
    tmp_path: Path, db_path: Path
) -> None:
    """`sources` took a different path and raised, wedging the entire pass.

    `_lw_upsert_source` discarded `_do_insert`'s result, then re-SELECTed, found
    nothing, and raised `ValueError("... conflicts with an existing local
    relpath")` — a message that also misnames the cause. Nothing catches it per
    row, so `import_knowledge` aborted and every later row in the file was lost.
    """
    export = _peer_file(tmp_path, ("sources", BAD_SOURCE), ("atoms", GOOD))

    stats = db_sync.import_knowledge(db_path, export)

    assert _count(db_path) == 1, (
        "a refused sources row aborted the import, so the valid atom after it "
        "was never stored"
    )
    assert stats.rejected == 1, f"the refused source was not counted: {stats}"
    assert stats.inserted == 1


def test_a_refused_source_row_is_not_counted_as_inserted(
    tmp_path: Path, db_path: Path
) -> None:
    export = _peer_file(tmp_path, ("sources", BAD_SOURCE))
    stats = db_sync.import_knowledge(db_path, export)

    with db.connect(db_path) as conn:
        stored = int(conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0])
    assert stored == 0
    assert stats.inserted == 0, "a source the database refused was counted as inserted"
    assert stats.rejected == 1


def test_a_valid_source_row_still_imports(tmp_path: Path, db_path: Path) -> None:
    """The ordinary path must be untouched."""
    good_source = {**BAD_SOURCE, "content_hash": "h1", "sync_key": "k-good"}
    export = _peer_file(tmp_path, ("sources", good_source))
    stats = db_sync.import_knowledge(db_path, export)

    with db.connect(db_path) as conn:
        stored = int(conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0])
    assert stored == 1
    assert stats.inserted == 1 and stats.rejected == 0


def test_autosync_console_output_names_rejected_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """autosync is the hands-off default — a silent loss there is the worst case.

    Only the --json branch reported `rejected`; the console branch printed a
    green success line, which is exactly the "clean import over a silent loss"
    this feature exists to prevent.
    """
    from curator.commands import db as db_cmd

    result = db_sync.AutosyncResult(
        imported={"dev-peer.jsonl": db_sync.ImportStats(inserted=3, rejected=2)},
    )
    # `db_autosync` imports `autosync` from the module at call time.
    monkeypatch.setattr(db_sync, "autosync", lambda *a, **k: result)
    monkeypatch.setattr(
        db_cmd, "_resolve_root_or_die", lambda *a, **k: _FakePaths(tmp_path)
    )
    monkeypatch.setattr(db_cmd, "_refresh_search_index", lambda *a, **k: None)

    try:
        db_cmd.db_autosync(dry_run=False, skip_reindex=True, json_output=False)
    except SystemExit:
        pass

    out = capsys.readouterr().out
    assert "rejected" in out, f"autosync hid the rejected rows: {out!r}"
    assert "NOT in this vault" in out, "no warning explained the loss"


class _FakePaths:
    def __init__(self, root: Path) -> None:
        self.internal = root / ".curator"
        self.internal.mkdir(parents=True, exist_ok=True)
        self.state_db = self.internal / "state.sqlite"
        db.init_db(self.state_db)
        self.base = root


TS = "2099-01-01T00:00:00Z"
ENTITY = {
    "id": "GEN-local",
    "canonical_name": "Bundle Adjustment",
    "entity_type": "concept",
    "created_at": TS,
    "updated_at": TS,
}


def _insert_entity(db_path: Path, row: dict) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO graph_entities ({','.join(row)}) "
            f"VALUES ({','.join('?' * len(row))})",
            list(row.values()),
        )


def test_the_same_entity_under_a_different_id_is_not_a_rejection(
    db_path: Path,
) -> None:
    """Cross-device convergence must not be reported as data loss.

    `graph_entities` is UNIQUE on (canonical_name, entity_type) but its
    transport key is the surrogate `id`. Two devices that independently extract
    the same entity mint different ids, so the peer's row looks new by key and
    collides on content. The entity IS present. Calling that `rejected` would
    fire on every sync forever — the ids never converge — and train the user to
    ignore the counter that exists to warn about real loss.
    """
    _insert_entity(db_path, ENTITY)
    with db.connect(db_path) as conn:
        result = db_sync._lw_upsert(
            conn, "graph_entities", {**ENTITY, "id": "GEN-peer"}, primary_keys=["id"]
        )
        stored = int(
            conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        )

    assert result == "skipped", (
        f"normal convergence reported as {result!r}; the entity is present and "
        f"nothing was lost"
    )
    assert stored == 1


def test_a_malformed_entity_is_still_a_rejection(db_path: Path) -> None:
    """The distinction must be real, not a blanket downgrade to skipped."""
    with db.connect(db_path) as conn:
        result = db_sync._lw_upsert(
            conn,
            "graph_entities",
            {**ENTITY, "id": "GEN-bad", "canonical_name": None},
            primary_keys=["id"],
        )
        stored = int(
            conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        )

    assert result == "rejected"
    assert stored == 0


def test_a_duplicate_source_relpath_reuses_the_local_id(
    tmp_path: Path, db_path: Path
) -> None:
    """Both devices added the same file: children must attach, not orphan."""
    first = {**BAD_SOURCE, "content_hash": "h1", "sync_key": "k-first"}
    export = _peer_file(tmp_path, ("sources", first))
    db_sync.import_knowledge(db_path, export)

    # A second device registered the SAME relpath under its own sync_key.
    second = {**first, "sync_key": "k-second", "id": 99}
    export2 = _peer_file(tmp_path / "b", ("sources", second))
    stats = db_sync.import_knowledge(db_path, export2)

    with db.connect(db_path) as conn:
        rows = int(conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0])
    assert rows == 1, "the same file was registered twice"
    assert stats.rejected == 0, (
        "two devices adding the same file is convergence, not a refusal"
    )
