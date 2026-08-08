"""`last_export_ts` must describe when the snapshot was READ, not when it finished.

B2 / sync_db-3. `export_for_device` wrote the stamp AFTER `export_knowledge`
returned. A row mutated while the export was running is not in the snapshot, but
its `created_at` is earlier than that stamp — so `local_has_unexported_changes`
concludes everything is exported and the row is never offered to a peer until an
unrelated later mutation happens to move the clock.

The window is the export's own duration, which grows with the vault: it is
widest exactly when there is most to lose.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from curator import db, db_sync


def _vault(tmp_path: Path) -> tuple[Path, Path]:
    internal = tmp_path / ".curator"
    internal.mkdir(parents=True, exist_ok=True)
    db_path = internal / "state.sqlite"
    db.init_db(db_path)
    return internal, db_path


def _now() -> str:
    return (
        db_sync.datetime.now(db_sync.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _add_atom(db_path: Path, atom_id: str) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO atoms"
            " (id, name, parent_source, claim_type, one_liner, last_updated)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (atom_id, atom_id, "01_Contexts/CTX-1.md", "fact", atom_id, _now()),
        )


def test_stamp_is_not_later_than_the_snapshot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invariant, stated directly."""
    internal, db_path = _vault(tmp_path)
    _add_atom(db_path, "ATM-first")

    real_export = db_sync.export_knowledge
    read_at: list[str] = []

    def slow_export(src, out, **kwargs):
        read_at.append(_now())
        result = real_export(src, out, **kwargs)
        time.sleep(1.1)  # push the completion into the next second
        return result

    monkeypatch.setattr(db_sync, "export_knowledge", slow_export)
    db_sync.export_for_device(internal, db_path)

    stamp = db_sync.read_sync_state(internal)["last_export_ts"]
    assert db_sync._timestamp_key(stamp) <= db_sync._timestamp_key(read_at[0]), (
        f"last_export_ts ({stamp}) is later than the moment the snapshot was "
        f"read ({read_at[0]}), so anything written during the export is treated "
        f"as already exported"
    )


def test_a_row_written_during_the_export_is_still_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The consequence a user would actually hit."""
    internal, db_path = _vault(tmp_path)
    _add_atom(db_path, "ATM-before")

    real_export = db_sync.export_knowledge

    def export_then_concurrent_write(src, out, **kwargs):
        result = real_export(src, out, **kwargs)
        # A mutation lands after the snapshot was read but before the stamp.
        _add_atom(db_path, "ATM-during")
        time.sleep(1.1)
        return result

    monkeypatch.setattr(db_sync, "export_knowledge", export_then_concurrent_write)
    db_sync.export_for_device(internal, db_path)

    assert db_sync.local_has_unexported_changes(internal, db_path), (
        "a row written during the export was recorded as already exported, so "
        "no peer will ever be offered it"
    )


def test_a_quiet_vault_still_reports_nothing_to_export(tmp_path: Path) -> None:
    """The fix must not make the gate fire constantly."""
    internal, db_path = _vault(tmp_path)
    _add_atom(db_path, "ATM-only")
    time.sleep(1.1)  # leave the mutation's second behind
    db_sync.export_for_device(internal, db_path)

    assert not db_sync.local_has_unexported_changes(internal, db_path), (
        "an idle vault reports unexported changes, which would re-export forever"
    )
