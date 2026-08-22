"""v0.64.0 (ROADMAP A2–A4): the vault stops reporting healthy while it is not.

Three gaps were found by hand-querying the DB, which is not a thing a user does:
every non-skipped source sat at `l3_status='error'`, `synthesis_nodes` was empty
and had never held a row, and 977 knowledge units had never reached the search
index. `wiki status` reported none of it.

Nothing here repairs a pipeline. It makes the pipeline's state legible, which is
the precondition for judging anything else.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from curator import config as cfg
from curator import db
from curator.cli import app


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    paths = cfg.WikiPaths(root)
    paths.internal.mkdir(parents=True)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)
    return root


def _add_source(state_db: Path, relpath: str, *, l3: str, l4: str) -> int:
    with db.connect(state_db) as conn:
        cur = conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
            " l1_status, l2_status, l3_status, l4_status) "
            "VALUES (?, ?, 'md', 10, datetime('now'), 'done', 'done', ?, ?)",
            (relpath, relpath, l3, l4),
        )
        return int(cur.lastrowid)


def _add_unit(
    state_db: Path,
    source_id: int,
    unit_id: str,
    *,
    indexed: bool,
    published: bool = True,
) -> None:
    """`published=False` mimics an interrupted extraction's staged rows, which
    have been durable since v0.62.0."""
    now = "2026-08-23T00:00:00Z"
    with db.connect(state_db) as conn:
        conn.execute(
            "INSERT INTO knowledge_units (id, source_id, unit_type, canonical_name, "
            " statement, source_span_ids, support_status, generation_id, "
            " created_at, updated_at) "
            "VALUES (?, ?, 'claim', ?, 'x', '[]', 'verified', ?, ?, ?)",
            (unit_id, source_id, unit_id, "GEN-published" if published else None,
             now, now),
        )
        if indexed:
            conn.execute(
                "INSERT INTO search_documents (doc_id, record_type, record_id, "
                " source_id, body, content_hash, dependency_hash, updated_at) "
                "VALUES (?, 'knowledge_unit', ?, ?, 'x', 'h', 'h', ?)",
                (f"DOC-knowledge_unit-{unit_id}", unit_id, source_id, now),
            )


# --- A4: get_stats carries layer health -------------------------------------

def test_stats_report_each_layer_status_count(vault: Path) -> None:
    paths = cfg.WikiPaths(vault)
    _add_source(paths.state_db, "a.md", l3="error", l4="error")
    _add_source(paths.state_db, "b.md", l3="error", l4="error")
    _add_source(paths.state_db, "c.md", l3="skipped", l4="skipped")

    stats = db.get_stats(paths.state_db)
    assert stats["layer_status"]["l3"]["error"] == 2
    assert stats["layer_status"]["l3"]["skipped"] == 1
    assert stats["layer_status"]["l4"]["done"] == 0


def test_stats_report_the_search_index_gap(vault: Path) -> None:
    """The gap that had to be hand-queried: units the vault holds but cannot find."""
    paths = cfg.WikiPaths(vault)
    sid = _add_source(paths.state_db, "a.md", l3="done", l4="done")
    _add_unit(paths.state_db, sid, "KNU-aaaa1111", indexed=True)
    _add_unit(paths.state_db, sid, "KNU-bbbb2222", indexed=False)
    _add_unit(paths.state_db, sid, "KNU-cccc3333", indexed=False)

    stats = db.get_stats(paths.state_db)
    assert stats["units_live"] == 3
    assert stats["units_indexed"] == 1
    assert stats["units_unindexed"] == 2


def test_stats_on_a_missing_db_still_carry_the_keys(tmp_path: Path) -> None:
    """`wiki status` renders these unconditionally, so the empty shape must match."""
    stats = db.get_stats(tmp_path / "absent.sqlite")
    assert stats["units_unindexed"] == 0
    assert stats["layer_status"]["l4"]["done"] == 0


# --- A4: wiki status says so ------------------------------------------------

def test_status_does_not_duplicate_the_pipeline_layer_table(vault: Path, monkeypatch) -> None:
    """`wiki status` already prints a **Pipeline Layer Status** table with
    per-layer done/pending/error/skipped, and `Collections` already prints
    `L4 Synthesis/ 0`. The first version of A4 restated both, which made the
    output longer and less legible. Report the gap nothing showed, not the ones
    already covered."""
    paths = cfg.WikiPaths(vault)
    _add_source(paths.state_db, "a.md", l3="error", l4="error")
    monkeypatch.setenv("VAULT_ROOT", str(vault))

    out = CliRunner().invoke(app, ["status"]).output
    assert "Pipeline Layer Status" in out, "the existing table is the layer report"
    assert "Layer health" not in out


def test_status_reports_the_search_index_gap(vault: Path, monkeypatch) -> None:
    """The one signal nothing showed — 61% of the corpus when it was measured."""
    paths = cfg.WikiPaths(vault)
    sid = _add_source(paths.state_db, "a.md", l3="done", l4="done")
    _add_unit(paths.state_db, sid, "KNU-aaaa1111", indexed=False)
    _add_unit(paths.state_db, sid, "KNU-bbbb2222", indexed=True)
    monkeypatch.setenv("VAULT_ROOT", str(vault))

    out = CliRunner().invoke(app, ["status"]).output
    assert "search cannot find" in out
    assert "1" in out


def test_status_is_quiet_when_the_index_is_complete(vault: Path, monkeypatch) -> None:
    """The warning has to mean something. A vault whose index is whole is not
    scolded."""
    paths = cfg.WikiPaths(vault)
    sid = _add_source(paths.state_db, "a.md", l3="done", l4="done")
    _add_unit(paths.state_db, sid, "KNU-aaaa1111", indexed=True)
    monkeypatch.setenv("VAULT_ROOT", str(vault))

    out = CliRunner().invoke(app, ["status"]).output
    assert "search cannot find" not in out


# --- A2: query expansion stops failing silently ------------------------------

def test_a_failing_expander_is_logged_not_swallowed(caplog) -> None:
    """RC-5(a), the one survivor of the defect audit. Three sites returned `{}` on
    any exception with no logging at all, so a dead expansion model degraded
    search silently — recall drops and nothing anywhere says why."""
    from curator.retrieval import expansion

    def boom(_raw: str) -> dict:
        raise RuntimeError("expander model is not loaded")

    with caplog.at_level(logging.WARNING, logger="curator.retrieval.expansion"):
        exp = expansion.expand("plücker coordinates", expander=boom)

    assert exp is not None, "a failed expansion must degrade, never raise"
    assert "expander" in caplog.text.lower() or "expansion" in caplog.text.lower()


def test_staged_units_from_an_interrupted_run_are_not_counted_as_a_gap(vault: Path) -> None:
    """`test_knowledge_unit_reader_hygiene` caught this in the first version.

    Since v0.62.0 an interrupted extraction leaves DURABLE unpublished rows —
    measured, one source held 5,358 of them. They are not in the search index
    *because they are not published yet*, so counting them inflates the gap and
    makes the warning fire through every long ingest. A warning that cries wolf
    is one the user learns to skip."""
    paths = cfg.WikiPaths(vault)
    sid = _add_source(paths.state_db, "a.md", l3="done", l4="done")
    _add_unit(paths.state_db, sid, "KNU-aaaa1111", indexed=True, published=True)
    _add_unit(paths.state_db, sid, "KNU-bbbb2222", indexed=False, published=False)

    stats = db.get_stats(paths.state_db)
    assert stats["units_live"] == 1
    assert stats["units_unindexed"] == 0, "a staged row is not a search-index gap"
