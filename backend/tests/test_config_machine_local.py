from pathlib import Path

import yaml

from curator import config as cfg
from curator import constants as consts


def test_load_config_ignores_machine_local_blocks_in_synced_vault_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    paths.internal.mkdir(parents=True)
    global_dir = tmp_path / "repo" / consts.DIR_GLOBAL_CACHE
    global_dir.mkdir(parents=True)
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)
    (global_dir / consts.FILE_GLOBAL_CONFIG_YML).write_text(
        yaml.safe_dump(
            {
                "llm": {"primary": "codex-cli::linux-local"},
                "search": {
                    "embedding": "llama-cpp::qwen3-embedding-0.6b",
                    "embedding_model_path": "/home/shin/.cache/embed.gguf",
                },
                "external": {
                    "path_roots": {"papers": "/home/shin/Papers"},
                    "zotero": {"enabled": True, "root_keys": ["papers"]},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    paths.config_file.write_text(
        yaml.safe_dump(
            {
                "paths": {"raw_dirs": ["03_Notes"]},
                "llm": {"primary": "codex-cli::mac-local"},
                "search": {"embedding_model_path": "/Users/shin/.cache/embed.gguf"},
                "external": {
                    "path_roots": {"papers": "/Users/shin/Papers"},
                    "zotero": {"enabled": True, "root_keys": ["papers"]},
                },
                "persona": {"area": "Physics"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    merged = cfg.load_config(paths)

    assert merged["paths"]["raw_dirs"] == ["03_Notes"]
    assert merged["persona"]["area"] == "Physics"
    assert merged["llm"]["primary"] == "codex-cli::linux-local"
    assert merged["search"]["embedding_model_path"] == "/home/shin/.cache/embed.gguf"
    assert merged["external"]["path_roots"]["papers"] == "/home/shin/Papers"


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
