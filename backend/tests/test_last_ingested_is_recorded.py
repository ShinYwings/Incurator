"""ROADMAP C3 (honesty half): the vault could not say when anything was ingested.

Measured on the reference vault before this change:

| | |
|---|---|
| sources | **44** |
| with a non-NULL `last_ingested` | **0** |
| with an authoritative `compiler_generations` row | **44** (newest 2026-08-22) |

So the fact existed; `sources.last_ingested` just never received it. The visible
symptom was in a file `wiki sync` rebuilds as of v0.69.1 — `ledger.md` reported
**"Last curated: never"** for a vault holding 37 contexts, 1,098 atoms and 233
concepts.

The cause is structural rather than historical: `run_l1_to_l3` selects only
sources with status `pending`/`force_pending`/`error`, so its
`_mark_source_status(..., "curated", last_ingested=...)` fires at most once in a
source's life — at the moment it first leaves the pending set. Every later
recompile publishes a new authoritative generation and touches nothing.

`publish_compiler_generation` IS that moment, and it already runs inside the
caller's transaction, so the stamp is atomic with the publish it describes.
"""

from __future__ import annotations

from pathlib import Path

from curator import config as cfg
from curator import db


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, status) "
            "VALUES ('04_Resources/a.md', 'h', 'md', 1, datetime('now'), 'curated')"
        )
    return paths


def _last_ingested(paths: cfg.WikiPaths, source_id: int) -> str | None:
    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            "SELECT last_ingested FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
    return row["last_ingested"] if row else None


def test_publishing_a_generation_stamps_the_source(tmp_path: Path) -> None:
    paths = _vault(tmp_path)
    assert _last_ingested(paths, 1) is None

    gen = db.create_compiler_generation(
        paths.state_db, source_id=1, prompt_contract_version="curator.x@v1"
    )
    db.publish_compiler_generation(paths.state_db, gen)

    stamped = _last_ingested(paths, 1)
    assert stamped, "publishing an authoritative generation left last_ingested NULL"
    assert stamped.endswith("Z")


def test_a_later_publish_moves_the_stamp_forward(tmp_path: Path) -> None:
    """The whole point: a source that is already `curated` is never re-selected
    by `run_l1_to_l3`, so without this it keeps whatever stamp it first got —
    or, as on the reference vault, none at all."""
    paths = _vault(tmp_path)
    first = db.create_compiler_generation(
        paths.state_db, source_id=1, prompt_contract_version="curator.x@v1"
    )
    db.publish_compiler_generation(paths.state_db, first)
    earlier = _last_ingested(paths, 1)

    with db.connect(paths.state_db) as conn:
        conn.execute("UPDATE sources SET last_ingested = '2020-01-01T00:00:00Z' WHERE id = 1")

    second = db.create_compiler_generation(
        paths.state_db, source_id=1, prompt_contract_version="curator.x@v1"
    )
    db.publish_compiler_generation(paths.state_db, second)

    assert _last_ingested(paths, 1) != "2020-01-01T00:00:00Z"
    assert earlier


def test_a_corpus_wide_generation_does_not_stamp_any_source(tmp_path: Path) -> None:
    """A generation with `source_id IS NULL` is the global L3/L4 scope. Stamping
    every source from it would claim each was individually re-ingested."""
    paths = _vault(tmp_path)
    gen = db.create_compiler_generation(
        paths.state_db, source_id=None, prompt_contract_version="curator.x@v1"
    )
    db.publish_compiler_generation(paths.state_db, gen)

    assert _last_ingested(paths, 1) is None


def test_the_ledger_reports_a_real_date_not_never(tmp_path: Path) -> None:
    """`ledger.md` said "Last curated: never" on a vault with 44 authoritative
    generations, because it read a column nothing populated."""
    from curator.ingest_llm import update_ledger

    paths = _vault(tmp_path)
    gen = db.create_compiler_generation(
        paths.state_db, source_id=1, prompt_contract_version="curator.x@v1"
    )
    db.publish_compiler_generation(paths.state_db, gen)

    update_ledger(paths)
    text = paths.ledger.read_text(encoding="utf-8")

    assert "Last curated: never" not in text, text
    assert "20" in text.split("Last curated:")[1][:8], text
