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

__all__ = ["normalize_relpath", "find_source_by_relpath", "relpath_collisions"]


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
