"""ROADMAP B2: cap `prompt_runs`, and never delete one an artifact points at.

`prompt_runs` is the largest of the growing tables — 4,406 rows, 17.39 MB on the
reference vault, against 6.85 MB for the 48,896-row tombstone table. Deleting the
3,052 unreferenced rows frees roughly 11.9 MB and costs about 0.38 MB of
tombstones, so the "GC refills the table it is trimming" worry is real in row
counts and not in bytes: a run is ~31x larger than the tombstone it leaves.

**The guard is the point.** `community_reports.prompt_run_id` is what v0.69.5's
L3 resume reads — `generate_report_prose` compares the referenced run's
`input_hash` to decide whether prose needs regenerating. Delete a referenced run
and the lookup returns None, the skip fails, and finished reports are re-sent to
the provider silently. On the reference vault that is 238 live reports carrying
prose and a run, so 238 calls to rewrite them — undoing a fix from two releases
earlier. (1,381 is the LIFETIME report-write call count, not the re-bill cost.)

Seven tables carry `prompt_run_id`, and `query_traces.prompt_trace_ids` is a JSON
array a plain join would miss.
"""

from __future__ import annotations

import json
from pathlib import Path

from curator import db
from curator.gc import apply_prompt_run_cap, plan_prompt_run_cap, referenced_prompt_runs


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "state.sqlite"
    db.init_db(path)
    return path


def _run(path: Path, trace_id: str, created_at: str) -> None:
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO prompt_runs (trace_id, prompt_id, prompt_version, family, "
            "role, model_provider, input_hash, created_at) "
            "VALUES (?, 'curator.x', 'v1', 'query', 'writer', 'fake', ?, ?)",
            (trace_id, f"h-{trace_id}", created_at),
        )


def _ids(path: Path) -> set[str]:
    with db.connect(path) as conn:
        return {r[0] for r in conn.execute("SELECT trace_id FROM prompt_runs").fetchall()}


def test_keeps_the_newest_and_drops_the_rest(tmp_path: Path) -> None:
    path = _db(tmp_path)
    for i in range(5):
        _run(path, f"PTR-{i}", f"2026-08-0{i + 1}T00:00:00Z")

    assert plan_prompt_run_cap(path, 2) == 3
    assert apply_prompt_run_cap(path, 2) == 3
    assert _ids(path) == {"PTR-4", "PTR-3"}


def test_a_referenced_run_is_never_deleted(tmp_path: Path) -> None:
    """THE guard. This run is the oldest and far past any cap, and it is what
    the L3 resume reads to avoid re-billing a finished report."""
    path = _db(tmp_path)
    _run(path, "PTR-old", "2020-01-01T00:00:00Z")
    for i in range(5):
        _run(path, f"PTR-{i}", f"2026-08-0{i + 1}T00:00:00Z")
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO community_reports (id, community_key, title, summary, "
            "full_content, dependency_hash, prompt_run_id, created_at, updated_at) "
            "VALUES ('REP-1','c1','t','s','prose','d','PTR-old',datetime('now'),datetime('now'))"
        )

    apply_prompt_run_cap(path, 1)

    assert "PTR-old" in _ids(path), "deleted the run the L3 resume depends on"


def test_a_run_cited_only_by_a_query_trace_is_kept(tmp_path: Path) -> None:
    """`prompt_trace_ids` is a JSON array, so a plain column join misses it."""
    path = _db(tmp_path)
    _run(path, "PTR-cited", "2020-01-01T00:00:00Z")
    for i in range(3):
        _run(path, f"PTR-{i}", f"2026-08-0{i + 1}T00:00:00Z")
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO query_traces (trace_id, question_hash, route, "
            "prompt_trace_ids, created_at) VALUES ('QTR-1','h','local',?,datetime('now'))",
            (json.dumps(["PTR-cited"]),),
        )

    apply_prompt_run_cap(path, 1)

    assert "PTR-cited" in _ids(path)


def test_every_deletion_leaves_a_tombstone(tmp_path: Path) -> None:
    """`prompt_runs` is synced and exports are full snapshots, so a delete
    without a tombstone is undone by the next import."""
    path = _db(tmp_path)
    for i in range(3):
        _run(path, f"PTR-{i}", f"2026-08-0{i + 1}T00:00:00Z")

    apply_prompt_run_cap(path, 1)

    with db.connect(path) as conn:
        stones = {
            r[0]
            for r in conn.execute(
                "SELECT record_id FROM deleted_records WHERE table_name = 'prompt_runs'"
            ).fetchall()
        }
    assert stones == {"PTR-0", "PTR-1"}


def test_the_cap_is_off_by_default(tmp_path: Path) -> None:
    """Deleting reaches every synced device, so it never happens unasked."""
    path = _db(tmp_path)
    for i in range(5):
        _run(path, f"PTR-{i}", f"2026-08-0{i + 1}T00:00:00Z")

    assert plan_prompt_run_cap(path, 0) == 0
    assert apply_prompt_run_cap(path, 0) == 0
    assert len(_ids(path)) == 5


def test_reference_scan_covers_every_column_that_holds_a_run_id(tmp_path: Path) -> None:
    """Keyed on the RELATIONSHIP, not the column name.

    The first version of this test looked only for columns literally named
    `prompt_run_id` — and so was structurally incapable of noticing
    `graph_batch_results.trace_id`, which holds the same value under a different
    name. That table is the graph-extraction resume cache: a batch stages its
    trace id there the moment it validates, while the matching
    `graph_entities`/`graph_relations` rows are not written until the whole
    source finishes. Between a mid-run capacity refusal and the resume, the run
    is referenced by that table ALONE, and the cap would have deleted it.

    A test that cannot fail for the bug it is named after is worse than no test,
    because it is read as coverage.
    """
    path = _db(tmp_path)
    with db.connect(path) as conn:
        tables = [
            t
            for (t,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        holders = set()
        for table in tables:
            if table in ("prompt_runs", "deleted_records"):
                continue
            for row in conn.execute(f"SELECT name FROM pragma_table_info('{table}')"):
                name = str(row[0])
                if "prompt_run" in name or name.endswith("trace_id"):
                    holders.add((table, name))

    from curator.gc import _PROMPT_RUN_REFERENCES

    scanned = set(_PROMPT_RUN_REFERENCES)
    # `query_traces` is scanned separately: its ids live in a JSON array, and its
    # own `trace_id` is the QTR- identity rather than a run reference.
    holders = {(t, c) for (t, c) in holders if t != "query_traces"}

    missing = holders - scanned
    assert not missing, (
        f"columns that can hold a prompt-run id but are not scanned: {sorted(missing)}"
    )


def test_referenced_set_is_empty_on_a_fresh_db(tmp_path: Path) -> None:
    with db.connect(_db(tmp_path)) as conn:
        assert referenced_prompt_runs(conn) == set()


def test_a_missing_reference_table_is_tolerated(tmp_path: Path) -> None:
    """An older schema simply lacks a table; that is not an error."""
    import sqlite3 as _sqlite3

    from curator.gc import referenced_prompt_runs

    path = _db(tmp_path)

    class _NoTable:
        def execute(self, sql, *args):
            if "insight_candidates" in sql:
                raise _sqlite3.OperationalError("no such table: insight_candidates")
            return conn.execute(sql, *args)

    with db.connect(path) as conn:
        assert referenced_prompt_runs(_NoTable()) == set()


def test_a_real_query_failure_is_never_swallowed(tmp_path: Path) -> None:
    """The load-bearing guard on the guard.

    A broad `except` here reports zero references for the failing table, and the
    caller then deletes prompt runs that ARE referenced — the exact silent
    breakage this scan exists to prevent. A locked or damaged database must fail
    the GC loudly, not quietly widen what it deletes.
    """
    import sqlite3 as _sqlite3

    import pytest

    from curator.gc import referenced_prompt_runs

    path = _db(tmp_path)

    class _Locked:
        def execute(self, sql, *args):
            if "community_reports" in sql:
                raise _sqlite3.OperationalError("database is locked")
            return conn.execute(sql, *args)

    with db.connect(path) as conn:
        with pytest.raises(_sqlite3.OperationalError, match="locked"):
            referenced_prompt_runs(_Locked())
