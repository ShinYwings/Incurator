"""Tests for vault schema migration (migrate.py)."""
from __future__ import annotations

from pathlib import Path

import yaml

from curator import config as cfg
from curator import constants as consts
from curator.migrate import (
    get_vault_schema_version,
    run_migrations,
    scan_stale_collection_files,
    set_vault_schema_version,
)


def _make_vault(tmp_path: Path, monkeypatch, schema_version: int | None = None) -> cfg.WikiPaths:
    global_dir = tmp_path / "cache_config"
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    paths.internal.mkdir(parents=True)
    vault_cfg: dict = {"version": 2, "paths": {"raw_dirs": [], "collections_dir": ".curator/Collections"}}
    if schema_version is not None:
        vault_cfg["vault_schema_version"] = schema_version
    paths.config_file.write_text(
        yaml.safe_dump(vault_cfg, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return paths


def test_get_vault_schema_version_absent(tmp_path: Path, monkeypatch) -> None:
    paths = _make_vault(tmp_path, monkeypatch)
    assert get_vault_schema_version(paths) == 0


def test_get_vault_schema_version_present(tmp_path: Path, monkeypatch) -> None:
    paths = _make_vault(tmp_path, monkeypatch, schema_version=1)
    assert get_vault_schema_version(paths) == 1


def test_set_vault_schema_version(tmp_path: Path, monkeypatch) -> None:
    paths = _make_vault(tmp_path, monkeypatch)
    set_vault_schema_version(paths, 1)
    assert get_vault_schema_version(paths) == 1
    # other vault config keys preserved
    data = yaml.safe_load(paths.config_file.read_text(encoding="utf-8"))
    assert data["version"] == 2


def test_run_migrations_already_current(tmp_path: Path, monkeypatch) -> None:
    paths = _make_vault(tmp_path, monkeypatch, schema_version=consts.VAULT_SCHEMA_VERSION)
    result = run_migrations(paths)
    assert result.already_current
    assert result.ok
    assert not result.steps_run


def test_run_migrations_v0_to_v1(tmp_path: Path, monkeypatch) -> None:
    # Vault at v0 with machine-local keys in vault config
    global_dir = tmp_path / "cache_config"
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    paths.internal.mkdir(parents=True)
    paths.config_file.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "llm": {"primary": "ollama::qwen2.5:7b"},
                "persona": {"area": "STEM"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = run_migrations(paths)

    assert result.ok
    assert result.steps_run == ["v0→v1"]
    assert get_vault_schema_version(paths) == 1
    # Machine-local keys should no longer be in vault config
    vault_data = yaml.safe_load(paths.config_file.read_text(encoding="utf-8"))
    assert "llm" not in vault_data
    assert vault_data.get("persona", {}).get("area") == "STEM"


def test_run_migrations_dry_run(tmp_path: Path, monkeypatch) -> None:
    paths = _make_vault(tmp_path, monkeypatch, schema_version=0)
    result = run_migrations(paths, dry_run=True)
    assert result.steps_run  # would run something
    # dry_run must not write schema version
    assert get_vault_schema_version(paths) == 0


def test_scan_stale_collection_files_clean(tmp_path: Path, monkeypatch) -> None:
    paths = _make_vault(tmp_path, monkeypatch, schema_version=1)
    # Write a valid ATM file
    atm_dir = paths.collections / consts.LAYER_L2
    atm_dir.mkdir(parents=True)
    (atm_dir / "ATM-abc.md").write_text(
        "---\nid: ATM-abc\ntype: atom\nunit_type: claim\n---\n# content\n",
        encoding="utf-8",
    )
    stale = scan_stale_collection_files(paths)
    assert stale == []


def test_scan_stale_collection_files_detects_missing_fields(tmp_path: Path, monkeypatch) -> None:
    paths = _make_vault(tmp_path, monkeypatch, schema_version=1)
    # Write an ATM file missing required fields
    atm_dir = paths.collections / consts.LAYER_L2
    atm_dir.mkdir(parents=True)
    (atm_dir / "ATM-bad.md").write_text(
        "---\nid: ATM-bad\n---\n# content\n",  # missing type and unit_type
        encoding="utf-8",
    )
    stale = scan_stale_collection_files(paths)
    assert len(stale) == 1
    assert "type" in stale[0].missing_fields
    assert "unit_type" in stale[0].missing_fields


def test_wiki_init_writes_current_schema_version(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner
    from curator.cli import app

    global_dir = tmp_path / "cache_config"
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    runner = CliRunner()
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--no-interactive"])
    assert result.exit_code == 0, result.output

    paths = cfg.WikiPaths(vault)
    assert get_vault_schema_version(paths) == consts.VAULT_SCHEMA_VERSION
