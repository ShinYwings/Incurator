"""What makes two paths the same source.

`sources.relpath` is the UNIQUE key AND the column `db_sync` reconciles peers
through, so the question "is this the same file?" is answered by string equality
on a path. That is fine until the same path arrives in two Unicode normalisation
forms, which on macOS it routinely does.

Measured on the live vault 2026-08-31: **18 of 50 stored relpaths (36%) were in
NFD**, the form macOS `readdir` returns, while nearly all tooling and every typed
path produces NFC. One pair had already split — the same file registered twice,
both rows `curated`, both carrying the same `content_hash`, its knowledge divided
across two source ids.

The existing dedup could not catch it: registration looks up
`WHERE relpath = ?` and compares hashes only to decide whether the file at THAT
path changed. Hash equality is change-detection on a known path, never cross-path
identity.

And the consequence is not confined to one machine. `db_sync` handles a peer's
duplicate by looking the source up BY RELPATH to attach the peer's child rows to
the local id. Two devices holding the same file in different forms never collide,
so the peer's rows attach to a NEW duplicate instead. Normalising is what makes
two devices agree on what one file is.

This lives outside `db/` deliberately. The whole `db/` package — `__init__.py`
included — is pinned by content hash in
`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`, which freezes a retrieval
evaluation against specific code. Adding a helper there, or even a re-export,
silently invalidates that result for a reason unrelated to retrieval.
"""

from __future__ import annotations

import sqlite3
import unicodedata

__all__ = [
    "normalize_relpath",
    "find_source_by_relpath",
    "relpath_collisions",
    "source_child_tables",
    "normalize_stored_relpaths",
    "merge_relpath_collision",
    "ensure_canonical_relpaths",
]


def normalize_relpath(value: str) -> str:
    """The canonical stored form of a `sources.relpath`.

    NFC, because that is what nearly all tooling and every typed path produces;
    NFD is the macOS `readdir` artefact. ASCII is unaffected, so the
    overwhelmingly common path costs one no-op call.
    """
    return unicodedata.normalize("NFC", value) if value else value


def find_source_by_relpath(
    conn: sqlite3.Connection, relpath: str
) -> sqlite3.Row | None:
    """Look a source up by path, in whichever form the caller happens to hold."""
    return conn.execute(
        "SELECT * FROM sources WHERE relpath = ?", (normalize_relpath(relpath),)
    ).fetchone()


def relpath_collisions(conn: sqlite3.Connection) -> list[list[sqlite3.Row]]:
    """Groups of sources whose paths differ only by normalisation form.

    Returned oldest-id-first within each group, because that is the row a merge
    keeps: it is the first registration, so its id is the one downstream rows and
    peers are most likely already pointing at.
    """
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in conn.execute("SELECT * FROM sources ORDER BY id"):
        groups.setdefault(normalize_relpath(row["relpath"]), []).append(row)
    return [rows for rows in groups.values() if len(rows) > 1]


def source_child_tables(conn: sqlite3.Connection) -> list[str]:
    """Tables carrying a `source_id`, read from the schema rather than listed.

    A hardcoded list is a list that goes stale, and the row it forgets is an
    orphan nobody notices until a query returns less than it should. Asking the
    database means a table added later is covered on the day it appears.
    """
    names: list[str] = []
    for (table,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sources'"
        " ORDER BY name"
    ):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "source_id" in cols:
            names.append(table)
    return names


def normalize_stored_relpaths(conn: sqlite3.Connection) -> tuple[int, int]:
    """Rewrite stored paths into canonical form. Returns (rewritten, skipped).

    Idempotent and safe: the canonical string names the same file, so nothing is
    lost and running it twice changes nothing the second time.

    A row whose canonical form is ALREADY HELD BY ANOTHER ROW is left alone and
    counted as skipped. Rewriting it would violate the UNIQUE constraint, and
    resolving that means merging two sources and everything hanging off them —
    the user's data. That stays an explicit, rehearsed command; see
    `merge_relpath_collision`.
    """
    taken = {row["relpath"] for row in conn.execute("SELECT relpath FROM sources")}
    rewritten = skipped = 0
    for row in conn.execute("SELECT id, relpath FROM sources ORDER BY id").fetchall():
        canonical = normalize_relpath(row["relpath"])
        if canonical == row["relpath"]:
            continue
        if canonical in taken:
            skipped += 1
            continue
        conn.execute(
            "UPDATE sources SET relpath = ? WHERE id = ?", (canonical, row["id"])
        )
        taken.discard(row["relpath"])
        taken.add(canonical)
        rewritten += 1
    return rewritten, skipped


def merge_relpath_collision(
    conn: sqlite3.Connection, rows: list[sqlite3.Row], *, apply: bool = False
) -> dict[str, object]:
    """Fold every row of one collision group into the oldest, or report the plan.

    The survivor is the LOWEST id — the first registration, so it is the row
    downstream tables and peers are most likely already pointing at, and its
    `sync_key` is the transport identity other devices know.

    Refuses to merge rows that disagree on `content_hash`. Two paths that
    normalise together but hold different bytes are not the same file, and
    merging them would destroy one of them. That is the stop condition, not a
    warning.

    With `apply=False` nothing is written; the returned plan is what `--apply`
    would do.
    """
    survivor, *losers = rows
    hashes = {row["content_hash"] for row in rows}
    if len(hashes) > 1:
        return {
            "refused": True,
            "reason": (
                "these rows normalise to one path but hold different content "
                "hashes, so they are not the same file"
            ),
            "relpath": normalize_relpath(survivor["relpath"]),
            "ids": [row["id"] for row in rows],
        }

    # A child row cannot always be repointed. `source_pdf_pages` is UNIQUE on
    # (source_id, page_number), and both sources hold the same pages — the
    # rehearsal on a copy of the live database hit exactly that and refused to
    # proceed, which is what the rehearsal is for.
    #
    # So: move what fits, drop what the survivor already has. The two rows share
    # a content_hash (a mismatch is refused above), so their derived rows are the
    # same rows twice, and the copy attached to the row being deleted is the one
    # to lose. Counted separately, because "moved 82" and "dropped 12 the
    # survivor already had" are different facts and the reader deserves both.
    moved: dict[str, int] = {}
    duplicate: dict[str, int] = {}
    for table in source_child_tables(conn):
        for loser in losers:
            count = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE source_id = ?",
                    (loser["id"],),
                ).fetchone()[0]
            )
            if not count:
                continue
            if not apply:
                moved[table] = moved.get(table, 0) + count
                continue
            conn.execute(
                f"UPDATE OR IGNORE {table} SET source_id = ? WHERE source_id = ?",
                (survivor["id"], loser["id"]),
            )
            left = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE source_id = ?",
                    (loser["id"],),
                ).fetchone()[0]
            )
            if left:
                conn.execute(
                    f"DELETE FROM {table} WHERE source_id = ?", (loser["id"],)
                )
                duplicate[table] = duplicate.get(table, 0) + left
            if count - left:
                moved[table] = moved.get(table, 0) + (count - left)
    if apply:
        for loser in losers:
            conn.execute("DELETE FROM sources WHERE id = ?", (loser["id"],))
        conn.execute(
            "UPDATE sources SET relpath = ? WHERE id = ?",
            (normalize_relpath(survivor["relpath"]), survivor["id"]),
        )
    return {
        "refused": False,
        "relpath": normalize_relpath(survivor["relpath"]),
        "keep": survivor["id"],
        "remove": [loser["id"] for loser in losers],
        "rows_moved": moved,
        "rows_dropped_as_duplicate": duplicate,
        "applied": apply,
    }


def ensure_canonical_relpaths(db_path) -> tuple[int, int]:
    """Fold stored paths into canonical form. Call right after `db.init_db`.

    This is not optional housekeeping. Lookups normalise now, so a row still
    stored in the macOS form is no longer reachable by its own path — and the
    next ingest of that file would not find it and would register a SECOND row.
    Normalising the reads without normalising what is already stored would have
    manufactured exactly the duplicates this release exists to remove.

    Lives here rather than inside `db.init_db` because `db/schema.py` is pinned by
    content hash in the D2 holdout record. `test_relpath_guard` requires every
    `db.init_db(` call to be followed by this one, so the four call sites cannot
    drift to three.

    Returns (rewritten, skipped). Skipped rows are collisions, which
    `wiki sources dedupe-paths` resolves under an explicit `--apply`.
    """
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    try:
        rewritten, skipped = normalize_stored_relpaths(conn)
        conn.commit()
        return rewritten, skipped
    finally:
        conn.close()
