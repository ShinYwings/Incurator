"""D1d: `prompt_runs.source_ids` names another device's integer source ids.

`sources.id` is an AUTOINCREMENT integer and deliberately replica-local — the
portable identity is `sources.sync_key`. Import already knows this: it resolves a
peer's source by `sync_key`, keeps the receiving device's own integer, and
remaps every synchronized child's `source_id` column onto it.

`prompt_runs.source_ids` is a JSON ARRAY of those integers, and a column remap
cannot reach inside a JSON string. So the array arrives holding the peer's
numbering, where each entry now points at whatever unrelated source happens to
occupy that row number locally — or at nothing.

This is not a gap in D1's entity/span work; it is a pre-existing hole in the
`sources` transport itself, which `SCHEMA.md` describes as remapping "every
synchronized child `source_id`". 2,984 rows carry one on the reference vault.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from curator import db
from curator.db_sync import export_knowledge, import_knowledge


@pytest.fixture()
def device(tmp_path: Path):
    def _make(name: str, sources: list[str]) -> Path:
        p = tmp_path / name / "state.sqlite"
        p.parent.mkdir(parents=True, exist_ok=True)
        db.init_db(p)
        with db.connect(p) as conn:
            for relpath in sources:
                conn.execute(
                    "INSERT INTO sources (relpath, content_hash, file_type, bytes,"
                    " added_at, last_ingested) VALUES (?, ?, 'md', 1, ?, ?)",
                    (relpath, f"hash-{relpath}", "2026-01-01T00:00:00Z",
                     "2026-01-01T00:00:00Z"),
                )
        return p

    return _make


def _local_id(path: Path, relpath: str) -> int:
    with db.connect(path) as conn:
        return int(
            conn.execute("SELECT id FROM sources WHERE relpath = ?", (relpath,))
            .fetchone()["id"]
        )


def test_a_prompt_runs_source_array_is_remapped_to_local_ids(
    device, tmp_path: Path
) -> None:
    """The two devices registered the same file in a different order, so it holds
    a different integer id on each. The array must arrive naming ours."""
    # A registered paper.md first (id 1); B registered it second (id 2).
    a = device("a", ["03_Notes/paper.md", "03_Notes/other.md"])
    b = device("b", ["03_Notes/other.md", "03_Notes/paper.md"])
    a_paper, b_paper = _local_id(a, "03_Notes/paper.md"), _local_id(b, "03_Notes/paper.md")
    assert a_paper != b_paper, "the fixture must give the same file different ids"

    with db.connect(a) as conn:
        conn.execute(
            "INSERT INTO prompt_runs (trace_id, prompt_id, prompt_version, family,"
            " input_hash, source_ids, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("PTR-11111111", "extract", "v1", "extract", "h",
             json.dumps([a_paper]), "2026-01-01T00:00:00Z"),
        )

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    with db.connect(b) as conn:
        row = conn.execute(
            "SELECT source_ids FROM prompt_runs WHERE trace_id = 'PTR-11111111'"
        ).fetchone()
    assert row is not None, "the prompt run did not arrive"
    got = json.loads(row["source_ids"])
    assert got == [b_paper], (
        f"the array still names the peer's numbering: {got} (this device uses "
        f"{b_paper} for that file, and {a_paper} is a different source here)"
    )


def test_an_id_for_a_source_this_device_lacks_is_dropped_not_left_dangling(
    device, tmp_path: Path
) -> None:
    """A peer id with no local counterpart must not be kept verbatim — kept, it
    silently names an unrelated local source rather than nothing."""
    a = device("a", ["03_Notes/paper.md"])
    b = device("b", ["03_Notes/other.md"])
    with db.connect(a) as conn:
        conn.execute(
            "INSERT INTO prompt_runs (trace_id, prompt_id, prompt_version, family,"
            " input_hash, source_ids, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("PTR-22222222", "extract", "v1", "extract", "h",
             json.dumps([_local_id(a, "03_Notes/paper.md"), 99]),
             "2026-01-01T00:00:00Z"),
        )

    export_path = tmp_path / "a.json"
    export_knowledge(a, export_path)
    import_knowledge(b, export_path)

    with db.connect(b) as conn:
        row = conn.execute(
            "SELECT source_ids FROM prompt_runs WHERE trace_id = 'PTR-22222222'"
        ).fetchone()
        live = {int(r["id"]) for r in conn.execute("SELECT id FROM sources")}
    got = json.loads(row["source_ids"])
    assert all(i in live for i in got), (
        f"the array names source ids this device does not have: {got}, live={live}"
    )
