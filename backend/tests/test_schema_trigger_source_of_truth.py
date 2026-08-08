r"""Trigger bodies have ONE definition, and drift is detectable.

B2 / sync_db-2. `sources_set_sync_key` was written twice — once inside
`SCHEMA_SQL`, once inside `_refresh_current_triggers` — and the two disagreed:
the `SCHEMA_SQL` copy used `'\'` in a non-raw Python string, so the escape ate
the backslash and the body became `replace(NEW.relpath, '', '/')`. Replacing an
empty string is a no-op, so Windows-style paths were never normalized.

`_triggers_need_refresh` could not catch it either, because it matched a
substring (`NEW.sync_key IS NULL OR NEW.sync_key = ''`) that the BROKEN body
also contains — so a database carrying the no-op kept it forever.

Why it matters: `sync_key` is the cross-device transport identity. A source
registered under the broken trigger gets `vault:04_Resources\win\a.md` instead
of `.../win/a.md`, so the same file becomes two sources that never converge —
and only the trigger self-heals on reopen, never the rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from curator import db
from curator.db import schema

SEPARATOR_NORMALIZER = "replace(NEW.relpath, '" + chr(92) + "', '/')"


def _installed(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name = ?", (name,)
    ).fetchone()
    return str(row[0]) if row else ""


def test_schema_sql_carries_the_real_separator(tmp_path: Path) -> None:
    """The canonical schema must not ship the no-op body."""
    assert SEPARATOR_NORMALIZER in schema.SCHEMA_SQL, (
        "SCHEMA_SQL's sources_set_sync_key does not normalize the path "
        "separator; a Python escape most likely ate the backslash"
    )
    assert "replace(NEW.relpath, '', '/')" not in schema.SCHEMA_SQL


def test_raw_schema_install_matches_a_refreshed_one(tmp_path: Path) -> None:
    """Both renderings must produce byte-identical triggers."""
    raw_path = tmp_path / "raw.sqlite"
    raw = sqlite3.connect(raw_path)
    raw.executescript(schema.SCHEMA_SQL)
    raw.commit()

    refreshed_path = tmp_path / "refreshed.sqlite"
    ref = sqlite3.connect(refreshed_path)
    ref.executescript(schema.SCHEMA_SQL)
    schema._refresh_current_triggers(ref)
    ref.commit()

    for name in (
        "sources_set_sync_key",
        "sources_touch_updated_at",
        "compiler_generations_touch_updated_at",
    ):
        a = " ".join(_installed(raw, name).split())
        b = " ".join(_installed(ref, name).split())
        assert a == b, f"{name} differs between SCHEMA_SQL and the refresh path"


def test_a_stale_trigger_is_detected_and_repaired(tmp_path: Path) -> None:
    """The detector must catch a body that differs, not just a missing one."""
    p = tmp_path / "legacy.sqlite"
    raw = sqlite3.connect(p)
    raw.executescript(schema.SCHEMA_SQL)
    # Install the historical no-op body by hand.
    raw.executescript(
        """
        DROP TRIGGER IF EXISTS sources_set_sync_key;
        CREATE TRIGGER sources_set_sync_key
        AFTER INSERT ON sources
        FOR EACH ROW
        WHEN NEW.sync_key IS NULL OR NEW.sync_key = ''
        BEGIN
            UPDATE sources SET sync_key = 'vault:' || replace(NEW.relpath, '', '/')
            WHERE id = NEW.id;
        END;
        """
    )
    raw.commit()
    raw.close()

    assert schema._triggers_need_refresh(sqlite3.connect(p)), (
        "the detector did not notice a trigger whose BODY is wrong; it only "
        "checks a substring the broken body also contains"
    )

    with db.connect(p) as conn:
        assert SEPARATOR_NORMALIZER in _installed(conn, "sources_set_sync_key"), (
            "opening the database did not repair the stale trigger"
        )


def test_backslash_paths_normalize_through_a_normal_open(tmp_path: Path) -> None:
    """The behavior the trigger exists for, end to end."""
    p = tmp_path / "state.sqlite"
    db.init_db(p)
    with db.connect(p) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES (?, ?, 'pdf', 0, '2099-01-01T00:00:00Z')",
            (r"04_Resources\win\a.md", "h1"),
        )
        key = conn.execute("SELECT sync_key FROM sources").fetchone()[0]
    assert key == "vault:04_Resources/win/a.md", key


def test_an_explicit_sync_key_is_never_rewritten(tmp_path: Path) -> None:
    p = tmp_path / "state.sqlite"
    db.init_db(p)
    with db.connect(p) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, sync_key) "
            "VALUES (?, ?, 'pdf', 0, '2099-01-01T00:00:00Z', ?)",
            ("04_Resources/a.md", "h1", "zotero:ABC123"),
        )
        key = conn.execute("SELECT sync_key FROM sources").fetchone()[0]
    assert key == "zotero:ABC123"
