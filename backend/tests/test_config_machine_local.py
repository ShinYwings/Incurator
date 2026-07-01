from pathlib import Path

import yaml

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
                "external": {"zotero": {"enabled": True, "roots": ["/machine/a/Zotero"]}},
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
    assert global_cfg["external"]["zotero"]["roots"] == []
    assert global_cfg["external"]["zotero"]["root_keys"] == ["zotero_data"]
    assert global_cfg["external"]["path_roots"]["zotero_data"] == "/machine/a/Zotero"
