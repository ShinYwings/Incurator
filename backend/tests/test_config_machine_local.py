from pathlib import Path

import pytest
import yaml

from curator import db
from curator import config as cfg
from curator import constants as consts


def test_load_config_migrates_machine_local_blocks_to_global_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    paths.internal.mkdir(parents=True)
    global_dir = tmp_path / "repo" / consts.DIR_GLOBAL_CACHE
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)

    paths.config_file.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "paths": {"raw_dirs": ["03_Notes"], "collections_dir": ".curator/Collections"},
                "llm": {"primary": "codex-cli::gpt-5.5"},
                "search": {"embedding_model_path": "/machine/a/embed.gguf"},
                "external": {
                    "path_roots": {"zotero_data": "/machine/a/Zotero"},
                    "zotero": {"enabled": True, "root_keys": ["zotero_data"]},
                },
                "persona": {"area": "STEM"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    merged = cfg.load_config(paths)

    assert merged["llm"]["primary"] == "codex-cli::gpt-5.5"
    assert merged["search"]["embedding_model_path"] == "/machine/a/embed.gguf"
    assert merged["external"]["zotero"]["root_keys"] == ["zotero_data"]
    assert merged["external"]["path_roots"]["zotero_data"] == "/machine/a/Zotero"

    local = yaml.safe_load(paths.config_file.read_text(encoding="utf-8"))
    assert "llm" not in local
    assert "search" not in local
    assert "external" not in local
    assert local["persona"]["area"] == "STEM"

    global_cfg = yaml.safe_load((global_dir / consts.FILE_GLOBAL_CONFIG_YML).read_text(encoding="utf-8"))
    assert global_cfg["llm"]["primary"] == "codex-cli::gpt-5.5"
    assert global_cfg["search"]["embedding_model_path"] == "/machine/a/embed.gguf"
    assert global_cfg["external"]["zotero"]["root_keys"] == ["zotero_data"]
    assert global_cfg["external"]["path_roots"]["zotero_data"] == "/machine/a/Zotero"


def test_load_config_does_not_convert_legacy_external_root_arrays(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = cfg.WikiPaths(tmp_path / "vault")
    global_dir = tmp_path / "repo" / consts.DIR_GLOBAL_CACHE
    global_dir.mkdir(parents=True)
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    (global_dir / consts.FILE_GLOBAL_CONFIG_YML).write_text(
        yaml.safe_dump(
            {
                "external": {
                    "roots": ["/legacy/library"],
                    "zotero": {
                        "enabled": True,
                        "roots": ["/legacy/Zotero"],
                    },
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    merged = cfg.load_config(paths)

    assert merged["external"]["path_roots"] == {}
    assert merged["external"]["zotero"].get("root_keys", []) == []


def test_wiki_paths_put_all_machine_state_under_repo_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault = tmp_path / "vault"
    global_dir = tmp_path / "repo" / consts.DIR_GLOBAL_CACHE
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)

    paths = cfg.WikiPaths(vault)
    machine_root = cfg.get_vault_cache_dir(vault)

    assert paths.state_db == machine_root / "state.sqlite"
    assert paths.runtime == machine_root / "runtime"
    assert paths.staging == machine_root / "staging"
    assert paths.dashboard == machine_root / "dashboard.md"
    assert paths.sync_report == machine_root / "sync-report.json"
    assert paths.event_log == machine_root / "log.md"
    assert paths.pdf_pages == machine_root / "pdf_pages"
    for path in (
        paths.state_db,
        paths.runtime,
        paths.staging,
        paths.dashboard,
        paths.sync_report,
        paths.event_log,
        paths.pdf_pages,
    ):
        assert path.is_relative_to(global_dir.parent)
        assert not path.is_relative_to(vault)


def test_prepare_machine_state_relocates_vault_db_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault = tmp_path / "vault"
    old_db = vault / ".curator" / "state.sqlite"
    old_db.parent.mkdir(parents=True)
    db.init_db(old_db)
    global_dir = tmp_path / "repo" / consts.DIR_GLOBAL_CACHE
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    paths = cfg.WikiPaths(vault)

    cfg.prepare_machine_state(paths)

    assert not old_db.exists()
    assert paths.state_db.exists()
    assert (paths.machine_cache / "vault_root").read_text(encoding="utf-8") == str(
        vault.resolve()
    )
    backups = list(
        (global_dir.parent / "migrations" / "v0.32.1").glob(
            "*/state.sqlite"
        )
    )
    assert len(backups) == 1


def test_prepare_machine_state_refuses_two_databases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault = tmp_path / "vault"
    old_db = vault / ".curator" / "state.sqlite"
    old_db.parent.mkdir(parents=True)
    global_dir = tmp_path / "repo" / consts.DIR_GLOBAL_CACHE
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    paths = cfg.WikiPaths(vault)
    db.init_db(old_db)
    db.init_db(paths.state_db)

    with pytest.raises(RuntimeError, match="Both vault-local and repo-cache"):
        cfg.prepare_machine_state(paths)
