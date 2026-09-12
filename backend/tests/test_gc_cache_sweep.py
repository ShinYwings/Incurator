"""ROADMAP B2: reclaim only what carries no cross-device meaning.

The sweep's obvious rule — "the recorded `vault_root` no longer exists, so this
cache is dead" — is a **mount test, not a liveness test**.
`config.get_vault_cache_dir` resolves with `strict=False`, so an unmounted
external drive or a disconnected network share hashes to the same directory name
and reads as missing. That directory holds `state.sqlite`, the single source of
truth — 287 MB on the reference vault. Deleting it because a drive was unplugged
would destroy the user's knowledge base.

Every one of the 25 dead directories measured on the reference machine was test
debris under a temp root, so requiring a temp prefix costs nothing real and
protects disconnected production paths. A source-less database can still hold
durable history, so collection additionally requires a recognized empty schema
and a namespace containing only the marker and optional database.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from curator import db
from curator.gc import dead_vault_caches, sweep


def _cache_dir(cache_root: Path, vault_root: str, *, sources: int = 0) -> Path:
    key = hashlib.sha256(vault_root.encode("utf-8")).hexdigest()[:16]
    entry = cache_root / "vaults" / key
    entry.mkdir(parents=True, exist_ok=True)
    (entry / "vault_root").write_text(vault_root, encoding="utf-8")
    state = entry / "state.sqlite"
    db.init_db(state)
    if sources:
        with db.connect(state) as conn:
            for i in range(sources):
                conn.execute(
                    "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                    "VALUES (?, ?, 'md', 1, datetime('now'))",
                    (f"04_Resources/a{i}.md", f"h{i}"),
                )
    return entry


def test_sweeps_temp_debris(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, "/private/var/folders/gc/T/tmpabc123/vault")

    found = dead_vault_caches(cache)

    assert [f.path for f in found] == [entry]
    assert found[0].bytes > 0


def test_never_sweeps_a_real_path_that_is_merely_absent(tmp_path: Path) -> None:
    """THE catastrophic case. `/Volumes/Ext/vault` is absent while the drive is
    unplugged and hashes exactly the same — and this directory would hold the
    user's entire knowledge base."""
    cache = tmp_path / "cache"
    _cache_dir(cache, "/Volumes/Ext/second_brain")
    _cache_dir(cache, "/Users/someone/Dropbox/vault")
    _cache_dir(cache, "//nas/share/vault")

    assert dead_vault_caches(cache) == []


def test_never_sweeps_a_cache_holding_ingested_work(tmp_path: Path) -> None:
    """Even under a temp root: a database with sources is not debris, whatever
    its path says. Test fixtures and a real vault can share a prefix."""
    cache = tmp_path / "cache"
    _cache_dir(cache, "/private/tmp/tmpxyz/vault", sources=3)

    assert dead_vault_caches(cache) == []


def test_never_sweeps_a_cache_whose_vault_still_exists(tmp_path: Path) -> None:
    live = tmp_path / "live-vault"
    live.mkdir()
    cache = tmp_path / "cache"
    _cache_dir(cache, str(live))

    assert dead_vault_caches(cache) == []


def test_a_directory_with_no_marker_is_left_alone(tmp_path: Path) -> None:
    """No `vault_root` file means we cannot prove anything about it. Silence is
    the safe answer; deleting on absence of evidence is how a GC eats data."""
    cache = tmp_path / "cache"
    orphan = cache / "vaults" / "deadbeefdeadbeef"
    orphan.mkdir(parents=True)
    (orphan / "state.sqlite").write_bytes(b"")

    assert dead_vault_caches(cache) == []


def test_an_unreadable_database_is_not_provably_empty(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, "/private/tmp/tmpqrs/vault")
    (entry / "state.sqlite").write_bytes(b"this is not a database")

    assert dead_vault_caches(cache) == []


def test_sweep_removes_only_what_was_planned(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    doomed = _cache_dir(cache, "/private/tmp/tmpgone/vault")
    kept = _cache_dir(cache, "/Volumes/Ext/vault")

    removed, freed = sweep(dead_vault_caches(cache))

    assert removed == 1
    assert freed > 0
    assert not doomed.exists()
    assert kept.exists()


def test_the_plan_reports_what_it_refuses_to_delete(tmp_path: Path, monkeypatch) -> None:
    """The point of the report. Every retained item is something a naive
    retention policy would delete, shown with the reason it must not — so the
    user sees the growth AND the refusal, instead of concluding nothing is wrong.
    """
    from curator import config as cfg
    from curator.gc import build_plan

    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO deleted_records (table_name, record_id, deleted_at) "
            "VALUES ('source_spans', 'SPAN-1', '2026-08-01T00:00:00Z')"
        )
    (paths.internal / "sessions.json").write_text("{}" * 200, encoding="utf-8")

    plan = build_plan(paths, tmp_path / "cache")
    labels = {r.label for r in plan.retained}

    assert "deleted_records" in labels
    assert ".curator/sessions.json" in labels
    tomb = next(r for r in plan.retained if r.label == "deleted_records")
    assert "resurrect" in tomb.reason
    assert "acknowledgement" in tomb.reason


def test_wiki_gc_run_deletes_nothing_when_there_is_nothing(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from curator import config as cfg
    from curator.cli import app

    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)
    monkeypatch.setenv("VAULT_ROOT", str(paths.root))

    result = CliRunner().invoke(app, ["gc", "run", "--yes"])
    assert result.exit_code == 0, result.stdout
    assert "Nothing to reclaim" in result.stdout


def test_wiki_gc_run_refuses_without_confirmation(tmp_path: Path, monkeypatch) -> None:
    """It deletes files. The default must be to ask."""
    from typer.testing import CliRunner

    from curator import config as cfg
    from curator.cli import app
    from curator import gc as gc_mod

    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)
    cache = tmp_path / "cache"
    doomed = _cache_dir(cache, "/private/tmp/tmpgone/vault")
    monkeypatch.setattr("curator.commands.gc._repo_cache_root", lambda: cache)
    monkeypatch.setenv("VAULT_ROOT", str(paths.root))

    result = CliRunner().invoke(app, ["gc", "run"], input="n\n")

    assert doomed.exists(), "declining the prompt still deleted the directory"
    assert result.exit_code == 1
    assert gc_mod.dead_vault_caches(cache)


def _cli_vault(tmp_path: Path):
    from curator import config as cfg

    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)
    return paths


def test_wiki_gc_run_reports_an_unreadable_chat_store_instead_of_crashing(
    tmp_path: Path, monkeypatch
) -> None:
    """The CLI boundary, which the module-level tests do not exercise.

    `gc_run` wraps the prune in `except UnreadableSessionStore`. Nothing asserted
    that the wrapper works, so the behaviour the changelog claims as fixed was
    untested at the surface a user actually touches.
    """
    from typer.testing import CliRunner

    from curator.cli import app

    paths = _cli_vault(tmp_path)
    store = paths.internal / "sessions.json"
    store.write_text("{ not json", encoding="utf-8")
    before = store.read_bytes()
    monkeypatch.setattr("curator.commands.gc._repo_cache_root", lambda: tmp_path / "cache")
    monkeypatch.setenv("VAULT_ROOT", str(paths.root))

    result = CliRunner().invoke(
        app, ["config", "set", "gc.sessions_retention_days", "30"]
    )
    assert result.exit_code == 0, result.stdout

    result = CliRunner().invoke(app, ["gc", "run", "--yes"])

    assert result.exit_code == 0, result.stdout
    assert "unreadable" in " ".join(result.stdout.split()).lower(), result.stdout
    assert store.read_bytes() == before, "an unreadable store was rewritten"


def test_wiki_gc_plan_does_not_report_a_corrupt_store_as_clean(
    tmp_path: Path, monkeypatch
) -> None:
    """SYSTEM_BEHAVIOR §32: false success is forbidden."""
    from typer.testing import CliRunner

    from curator.cli import app

    paths = _cli_vault(tmp_path)
    (paths.internal / "sessions.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr("curator.commands.gc._repo_cache_root", lambda: tmp_path / "cache")
    monkeypatch.setenv("VAULT_ROOT", str(paths.root))
    CliRunner().invoke(app, ["config", "set", "gc.sessions_retention_days", "30"])

    out = " ".join(CliRunner().invoke(app, ["gc", "plan"]).stdout.split())

    assert "UNREADABLE" in out.upper(), out
    assert "0 session(s) past the window" not in out, out


def test_wiki_gc_json_exposes_the_prompt_run_cap(tmp_path: Path, monkeypatch) -> None:
    """The dashboard reads `--json`; a number only humans can see is not surfaced."""
    import json as _json

    from typer.testing import CliRunner

    from curator.cli import app

    paths = _cli_vault(tmp_path)
    with db.connect(paths.state_db) as conn:
        for i in range(4):
            conn.execute(
                "INSERT INTO prompt_runs (trace_id, prompt_id, prompt_version, family, "
                "role, model_provider, input_hash, created_at) "
                "VALUES (?, 'curator.x', 'v1', 'query', 'w', 'fake', ?, ?)",
                (f"PTR-{i}", f"h{i}", f"2026-08-0{i + 1}T00:00:00Z"),
            )
    monkeypatch.setattr("curator.commands.gc._repo_cache_root", lambda: tmp_path / "cache")
    monkeypatch.setenv("VAULT_ROOT", str(paths.root))
    CliRunner().invoke(app, ["config", "set", "gc.prompt_runs_keep", "1"])

    payload = _json.loads(CliRunner().invoke(app, ["gc", "plan", "--json"]).stdout)

    assert payload["prompt_runs_prunable"] == 3


@pytest.mark.parametrize("kind", ["tombstone", "prompt_run", "job_event"])
def test_source_less_durable_history_is_retained(tmp_path: Path, kind: str) -> None:
    # Deleted sources need not erase provenance: exercise both fleet deletion
    # markers and local operational history independently of source occupancy.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    state = entry / "state.sqlite"
    with db.connect(state) as conn:
        if kind == "tombstone":
            conn.execute(
                "INSERT INTO deleted_records(table_name, record_id, deleted_at) "
                "VALUES ('sources', 'retained-source', '2026-09-01')"
            )
        elif kind == "prompt_run":
            conn.execute(
                "INSERT INTO prompt_runs(trace_id, prompt_id, prompt_version, family, "
                "input_hash, created_at) VALUES ('PTR-keep', 'test', 'v1', 'query', 'h', '2026-09-01')"
            )
        else:
            conn.execute("INSERT INTO ingest_jobs(id, created_at) VALUES (1, '2026-09-01')")
            conn.execute(
                "INSERT INTO job_events(job_id, seq, kind, data, at) "
                "VALUES (1, 1, 'done', '{}', '2026-09-01')"
            )
    before = state.read_bytes()

    assert dead_vault_caches(cache) == []
    assert state.read_bytes() == before


@pytest.mark.parametrize("layout", ["partial", "unknown", "old_version", "changed_table", "view"])
def test_unrecognized_schema_is_retained_without_repair(tmp_path: Path, layout: str) -> None:
    # Discovery must never manufacture the empty sources table used to justify
    # deletion, stamp an old version, or silently accept changed table contracts.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    state = entry / "state.sqlite"
    if layout == "partial":
        state.unlink()
    with closing(sqlite3.connect(state)) as conn:
        if layout in {"partial", "unknown"}:
            conn.execute('CREATE TABLE "retained history" (payload TEXT)')
            conn.execute('INSERT INTO "retained history" VALUES (\'must survive\')')
        elif layout == "old_version":
            conn.execute("UPDATE schema_version SET version = 1")
        elif layout == "view":
            conn.execute("CREATE VIEW retained_query AS SELECT * FROM prompt_runs")
        else:
            conn.execute("ALTER TABLE prompt_runs ADD COLUMN retained_payload TEXT")
        conn.commit()
        schema_before = conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
    before = state.read_bytes()

    found = dead_vault_caches(cache)

    assert state.read_bytes() == before, "inspection changed a candidate database"
    with closing(sqlite3.connect(f"{state.as_uri()}?mode=ro", uri=True)) as conn:
        assert conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall() == schema_before
    assert found == []


def test_repeated_inspection_leaves_empty_cache_files_unchanged(tmp_path: Path) -> None:
    # A read-only WAL connection still creates sidecars. A preview must not
    # turn its own empty candidate into unresolved activity on the next scan.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    before = {p.name: p.read_bytes() for p in entry.iterdir()}

    assert [item.path for item in dead_vault_caches(cache)] == [entry]
    assert {p.name: p.read_bytes() for p in entry.iterdir()} == before
    assert [item.path for item in dead_vault_caches(cache)] == [entry]


def test_logical_fts_content_is_retained(tmp_path: Path) -> None:
    # Only infrastructure of an empty logical FTS table is disposable. Index
    # rows must not disappear just because they live through shadow tables.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    with db.connect(entry / "state.sqlite") as conn:
        conn.execute("INSERT INTO search_documents_fts(title, body) VALUES ('keep', 'history')")

    assert dead_vault_caches(cache) == []


@pytest.mark.parametrize("change", ["sidecar", "checkpoint"])
def test_source_change_during_snapshot_inspection_is_retained(tmp_path: Path, monkeypatch, change: str) -> None:
    # The private copy can already be stale by the time it is queried. Exercise
    # both visible WAL activity and a completed/checkpointed write with no WAL
    # left behind; neither may authorize deleting the now-populated original.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    state = entry / "state.sqlite"
    copyfile = shutil.copyfile

    def copy_then_change(source, destination):
        result = copyfile(source, destination)
        if Path(source) == state:
            if change == "sidecar":
                (entry / "state.sqlite-wal").write_bytes(b"")
            else:
                with closing(sqlite3.connect(state)) as conn:
                    conn.execute(
                        "INSERT INTO deleted_records(table_name, record_id, deleted_at) "
                        "VALUES ('sources', 'late-commit', '2026-09-12')"
                    )
                    conn.commit()
                assert not (entry / "state.sqlite-wal").exists()
        return result

    monkeypatch.setattr("curator.gc.shutil.copyfile", copy_then_change)

    assert dead_vault_caches(cache) == []
    assert state.exists()


@pytest.mark.parametrize("has_database", [False, True])
@pytest.mark.parametrize("payload", ["log.md", "state.sqlite.bak-old", "runtime"])
def test_unowned_namespace_content_is_retained(
    tmp_path: Path, has_database: bool, payload: str
) -> None:
    # Recursive removal owns the whole namespace, not only state.sqlite. A
    # missing or empty DB cannot authorize deleting unrelated history or files.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    if not has_database:
        (entry / "state.sqlite").unlink()
    target = entry / payload
    if payload == "runtime":
        target.mkdir()
        target = target / "pending-work.json"
    target.write_text("retained", encoding="utf-8")

    assert dead_vault_caches(cache) == []
    assert target.read_text(encoding="utf-8") == "retained"


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_preexisting_sqlite_sidecars_are_retained(tmp_path: Path, suffix: str) -> None:
    # Even empty sidecars carry an unresolved activity/recovery question. Do not
    # open SQLite first: its connection cleanup can erase that evidence.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    sidecar = entry / f"state.sqlite{suffix}"
    sidecar.write_bytes(b"")

    assert dead_vault_caches(cache) == []
    assert sidecar.exists()


def test_committed_wal_history_is_retained(tmp_path: Path) -> None:
    # Keep the writing connection open so committed history resides in WAL.
    # Looking only at immutable main-file bytes would miss this durable row.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    with closing(sqlite3.connect(entry / "state.sqlite")) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute(
            "INSERT INTO deleted_records(table_name, record_id, deleted_at) "
            "VALUES ('sources', 'wal-source', '2026-09-01')"
        )
        writer.commit()
        assert (entry / "state.sqlite-wal").exists()
        assert dead_vault_caches(cache) == []


def test_temp_prefix_is_checked_after_root_resolution(tmp_path: Path) -> None:
    # A lexical /tmp/ prefix is not authority when traversal resolves outside
    # the temporary tree. No path under this marker is created by the test.
    cache = tmp_path / "cache"
    _cache_dir(cache, "/tmp/../incurator-gc-non-temp-vault")

    assert dead_vault_caches(cache) == []


@pytest.mark.parametrize("component", ["namespace", "marker", "database"])
def test_symlinked_cache_components_are_retained(tmp_path: Path, component: str) -> None:
    # A symlink can retarget the namespace proof to a different owner's file.
    # Both the indirection and its destination must survive discovery unchanged.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    original = {
        "namespace": entry,
        "marker": entry / "vault_root",
        "database": entry / "state.sqlite",
    }[component]
    destination = tmp_path / f"real-{component}"
    original.rename(destination)
    original.symlink_to(destination, target_is_directory=component == "namespace")

    assert dead_vault_caches(cache) == []
    assert original.is_symlink()
    assert destination.exists()


@pytest.mark.parametrize(
    "change", ["source", "tombstone", "root", "marker", "namespace", "database", "unknown_file"]
)
def test_changed_candidate_is_not_deleted_from_old_plan(tmp_path: Path, change: str) -> None:
    # Confirmation can suspend execution while another owner changes the cache.
    # Identical-looking replacement objects must not inherit the old authority.
    cache = tmp_path / "cache"
    root = tmp_path / "gone-vault"
    entry = _cache_dir(cache, str(root))
    found = dead_vault_caches(cache)
    assert [item.path for item in found] == [entry]
    if change in {"source", "tombstone"}:
        with db.connect(entry / "state.sqlite") as conn:
            if change == "source":
                conn.execute(
                    "INSERT INTO sources(relpath, content_hash, file_type, bytes, added_at) "
                    "VALUES ('retained.md', 'h', 'md', 1, '2026-09-01')"
                )
            else:
                conn.execute(
                    "INSERT INTO deleted_records(table_name, record_id, deleted_at) "
                    "VALUES ('sources', 'keep', '2026-09-01')"
                )
    elif change == "root":
        root.mkdir()
    elif change == "marker":
        (entry / "vault_root").write_text(str(tmp_path / "different-gone-vault"), encoding="utf-8")
    elif change == "namespace":
        original = tmp_path / "original-cache"
        entry.rename(original)
        shutil.copytree(original, entry)
    elif change == "database":
        original = tmp_path / "original.sqlite"
        (entry / "state.sqlite").rename(original)
        shutil.copyfile(original, entry / "state.sqlite")
    else:
        (entry / "new-history.md").write_text("keep", encoding="utf-8")

    assert sweep(found) == (0, 0)
    assert entry.is_dir()


def test_marker_only_empty_namespace_remains_collectible(tmp_path: Path) -> None:
    # No database and no other payload is still exactly the supported debris
    # case; preservation guards must not disable collection altogether.
    cache = tmp_path / "cache"
    entry = _cache_dir(cache, str(tmp_path / "gone-vault"))
    (entry / "state.sqlite").unlink()

    found = dead_vault_caches(cache)
    assert [item.path for item in found] == [entry]
    removed, freed = sweep(found)
    assert removed == 1
    assert freed > 0
    assert not entry.exists()


def test_cli_rechecks_candidate_changed_during_confirmation(tmp_path: Path, monkeypatch) -> None:
    # The real CLI boundary must report zero actual removals when a valid plan
    # becomes stale while the user is deciding, even if they answer yes.
    from typer.testing import CliRunner

    from curator.cli import app

    paths = _cli_vault(tmp_path)
    cache = tmp_path / "cache"
    root = tmp_path / "gone-vault"
    entry = _cache_dir(cache, str(root))
    monkeypatch.setattr("curator.commands.gc._repo_cache_root", lambda: cache)
    monkeypatch.setenv("VAULT_ROOT", str(paths.root))

    def confirm_after_recreation(*args, **kwargs):
        root.mkdir()
        return True

    monkeypatch.setattr("curator.commands.gc.typer.confirm", confirm_after_recreation)
    result = CliRunner().invoke(app, ["gc", "run"])

    assert result.exit_code == 0, result.stdout
    assert entry.exists()
    assert "Nothing to reclaim" in result.stdout
