"""`wiki sync` records and clears layer state truthfully (SYSTEM_BEHAVIOR §26.3).

Two functions in `commands/common.py` write layer state during sync, and until
v0.45.0 neither had a test — which is how both defects below survived.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import config as cfg
from curator import constants as consts
from curator import db
from curator.commands import common as common_mod
from curator.sync import VerificationGap


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path)
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.synthesis):
        layer_dir.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    return paths


def _add_source(
    paths: cfg.WikiPaths,
    relpath: str,
    *,
    l2: str = "done",
    l3: str = "done",
    l4: str = "done",
    layer_error: str | None = None,
) -> int:
    with db.connect(paths.state_db) as conn:
        cur = conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
            "status, l1_status, l2_status, l3_status, l4_status, layer_error) "
            "VALUES (?, ?, 'md', 0, '2026-08-06T00:00:00Z', 'curated', 'done', ?, ?, ?, ?)",
            (relpath, f"hash-{relpath}", l2, l3, l4, layer_error),
        )
        return int(cur.lastrowid)


def _row(paths: cfg.WikiPaths, source_id: int) -> dict:
    with db.connect(paths.state_db) as conn:
        r = conn.execute(
            "SELECT l2_status, l3_status, l4_status, layer_error FROM sources WHERE id = ?",
            (source_id,),
        ).fetchone()
    return dict(r)


def test_sync_gap_reason_survives_the_following_l4_status_write(tmp_path: Path) -> None:
    """The L4 write must not clear the reason the L3 write just recorded.

    `layer_error` is one column shared by all four layers. The L4 `pending`
    write passed no `error=`, so it defaulted to None and cleared the
    `sync_logical_gap:` text written one line earlier — leaving `l3_status`
    stuck at `error` with no explanation of why, permanently.
    """
    paths = _vault(tmp_path)
    sid = _add_source(paths, "03_Notes/a.md", l2="done", l3="done", l4="done")

    common_mod._mark_layer_status_from_sync_gaps(
        paths,
        [VerificationGap(layer=consts.TYPE_L3, node_id="CON-abc12345", message="gap")],
    )

    row = _row(paths, sid)
    assert row["l3_status"] == "error"
    assert row["l4_status"] == "pending"
    assert row["layer_error"] == "sync_logical_gap:CON-abc12345", (
        "the L4 status write must not clobber the L3 reason"
    )


def test_clean_sync_clears_stale_errors_without_advancing_any_status(
    tmp_path: Path,
) -> None:
    """§26.3: sync clears stale error text and never promotes a status.

    The deleted behaviour set `l3_status='done'` for EVERY `l2_status='done'`
    source whenever any `CON-*.md` existed anywhere on disk. Here a concept page
    exists and a source is legitimately `skipped`; it must stay `skipped`.
    """
    paths = _vault(tmp_path)
    (paths.concepts / "CON-abc12345.md").write_text("# Concept\n", encoding="utf-8")
    (paths.synthesis / "SYN-abc12345.md").write_text("# Synthesis\n", encoding="utf-8")

    stale = _add_source(
        paths, "03_Notes/stale.md", l3="skipped", l4="skipped",
        layer_error="provider timed out",
    )
    errored = _add_source(
        paths, "03_Notes/errored.md", l3="error", l4="skipped",
        layer_error="l3: clustering failed",
    )

    common_mod._mark_clean_sync_status(paths)

    cleared = _row(paths, stale)
    assert cleared["layer_error"] is None, "stale error text should be cleared"
    assert cleared["l3_status"] == "skipped", "a skipped layer must not be promoted"
    assert cleared["l4_status"] == "skipped"

    kept = _row(paths, errored)
    assert kept["layer_error"] == "l3: clustering failed", (
        "an unresolved error must keep its explanation"
    )
    assert kept["l3_status"] == "error"


def test_read_only_commands_no_longer_promote_l3_from_a_glob(tmp_path: Path) -> None:
    """`wiki sources ls` and `wiki status --refresh` used to mutate status.

    Both called `_mark_existing_l3_done_if_present`, the twin of the promotion
    deleted from `_mark_clean_sync_status` — same filesystem glob, same
    every-source promotion, reached from two read-only surfaces. It is gone.
    """
    from curator import ingest_llm

    assert not hasattr(ingest_llm, "_mark_existing_l3_done_if_present")


def test_bulk_layer_writes_are_chunked_and_correct_over_a_large_id_list(
    tmp_path: Path,
) -> None:
    """`_mark_clean_sync_status` feeds an unfiltered `SELECT id FROM sources`
    straight into the bulk writer, so the `IN` list is bounded only by vault
    size and must be chunked like every other bulk id predicate in the module.

    This does NOT reproduce a crash: SQLite 3.40 on this machine accepts far
    more than 999 host variables, so a failing case is not constructible here.
    What it pins is (a) the writers stay correct across chunk boundaries, and
    (b) the chunk size remains at or below the conservative 999 that older
    SQLite builds default to — which is the portability contract PR #79
    established and `_chunks()` exists to honour.
    """
    from curator.db import sources as sources_mod

    assert sources_mod._chunks.__defaults__[0] <= 999, (
        "chunk size must stay within the oldest supported SQLite variable limit"
    )

    count = 1200  # spans several chunks at the default size
    paths = _vault(tmp_path)
    ids = [
        _add_source(paths, f"03_Notes/n{i}.md", l3="skipped", l4="skipped",
                    layer_error="stale")
        for i in range(count)
    ]
    assert len(ids) > sources_mod._chunks.__defaults__[0], "must cross a chunk boundary"

    common_mod._mark_clean_sync_status(paths)

    with db.connect(paths.state_db) as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM sources WHERE layer_error IS NOT NULL"
        ).fetchone()["n"]
    assert remaining == 0, "every stale error must be cleared, not just the first chunk"

    # The status writer's UNSET path chunks too, and must leave errors alone.
    db.set_sources_layer_status(paths.state_db, ids, "l4", "pending", error=db.UNSET)
    with db.connect(paths.state_db) as conn:
        rows = conn.execute("SELECT l4_status, layer_error FROM sources").fetchall()
    assert {r["l4_status"] for r in rows} == {"pending"}
    assert all(r["layer_error"] is None for r in rows)
