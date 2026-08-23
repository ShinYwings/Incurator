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
removes the whole class of catastrophic misfire. The zero-sources check is the
third independent guard.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

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
